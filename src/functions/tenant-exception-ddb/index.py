import json
import os
import boto3
import logging
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.data_classes import S3Event
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key
from datetime import datetime

# Configure logging and tracing
logger = Logger()
tracer = Tracer()

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
ssm_client = boto3.client("ssm")

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize DynamoDB client
table_name = os.environ.get('TABLE_NAME')
table = dynamodb.Table(table_name) if table_name else None

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """
    Process exception policy updates from S3 and update DynamoDB.
    
    Args:
        event: S3 event that triggered the function or direct invocation event
        context: Lambda context
        
    Returns:
        Response dictionary with status information
    """
    try:
        logger.info(f"Processing event: {json.dumps(event)}")
        
        # Validate table is available
        if not table:
            logger.error("TABLE_NAME environment variable not set")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Table name not configured'})
            }
        
        # Determine the type of event (S3 notification or direct invocation)
        if 'Records' in event and event['Records'] and event['Records'][0].get('eventSource') == 'aws:s3':
            # S3 event notification case
            try:
                s3_event = S3Event(event)
                bucket_name = s3_event.bucket_name
                object_key = s3_event.object_key
                
                # For S3 notifications, use configured table name from environment variable
                table_name = os.environ["TABLE_NAME"]
                
                # Register table in SSM for cross-account access
                register_table_in_ssm(table_name, "exception")
                
                logger.info(f"Processing new exception policy: {object_key} from {bucket_name}")
                return process_exception_policy(table_name, bucket_name, object_key)
            except (KeyError, AttributeError, IndexError) as e:
                logger.error(f"Malformed S3 event structure: {str(e)}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Malformed S3 event structure'})
                }
        else:
            # Direct invocation case for batch processing
            parameters = event.get('parameters', {})
            table_name = parameters.get('TABLE_NAME') or os.environ.get("TABLE_NAME")
            bucket_name = parameters.get('BUCKET_NAME')
            
            # Register/update SSM parameter
            register_table_in_ssm(table_name, "exception")
            
            # Validate parameters
            if not table_name or not bucket_name:
                logger.error("Missing required parameters in event payload")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'message': 'Missing required parameters TABLE_NAME or BUCKET_NAME'
                    })
                }
            
            logger.info(f"Direct invocation with table: {table_name}, bucket: {bucket_name}")
            return process_exception_policies(table_name, bucket_name)
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

@tracer.capture_method
def process_exception_policy(table_name: str, bucket_name: str, object_key: str) -> dict:
    """Process a single exception policy file from S3 and update DynamoDB."""
    logger.info(f"Processing exception policy file: {object_key} from bucket: {bucket_name}")
    
    try:
        # Read policy file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        policy_content = response["Body"].read().decode("utf-8")
        policy_data = json.loads(policy_content)
        
        # Get DynamoDB table
        table = dynamodb.Table(table_name)
        
        # Extract exception ID from filename or policy content
        exception_id = extract_exception_id(policy_data, object_key)
        
        # Extract service name from policy actions or filename
        service_name = extract_service_from_actions(policy_data, object_key)
        
        # Extract account ID from S3 key (policies/exception/123456789012/policy.json)
        key_parts = object_key.split('/')
        account_id_str = key_parts[2] if len(key_parts) > 2 else 'unknown'
        
        # Convert account ID to integer for DynamoDB (table schema expects Number)
        try:
            account_id = int(account_id_str) if account_id_str != 'unknown' else 0
        except ValueError:
            logger.warning(f"Could not parse account ID '{account_id_str}' as integer, using 0")
            account_id = 0
        
        # Generate hash value for the policy to use as primary key
        hash_value = generate_policy_hash(policy_data)
        
        # Create composite key for exception policy (for logging/display purposes)
        if exception_id and service_name:
            policy_key = f"{exception_id}:{service_name}"
        elif exception_id:
            policy_key = exception_id
        elif service_name:
            policy_key = service_name
        else:
            logger.warning(f"Could not extract exception ID or service name from {object_key}, skipping")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'Could not extract exception ID or service name from policy',
                    'policy': object_key
                })
            }
        
        # Get current item from DynamoDB if it exists
        response = table.get_item(Key={'HashValue': hash_value, 'AccountID': account_id})
        item = response.get('Item', {})
        item_exists = 'Item' in response
        
        # Ensure version is always an integer, default to 0 if not present
        try:
            current_version = int(item.get('Version', 0))
        except (ValueError, TypeError):
            current_version = 0
        
        # Get current policy JSON if it exists
        current_policy = item.get('PolicyJSON', '')
        
        # Serialize new policy to JSON string
        policy_json = json.dumps({
            'Version': policy_data.get('Version', '2012-10-17'),
            'Statement': policy_data.get('Statement', [])
        }, sort_keys=True)
        
        # Normalize current policy for comparison
        if current_policy:
            try:
                normalized_current = json.dumps(json.loads(current_policy), sort_keys=True)
            except json.JSONDecodeError:
                logger.warning(f"Current policy for {policy_key} is not valid JSON, treating as empty")
                normalized_current = ''
        else:
            normalized_current = ''
        
        # Compare new policy with current policy
        if policy_json == normalized_current:
            logger.info(f"No changes in policy for {policy_key}, skipping update")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No changes in policy',
                    'exception': policy_key
                })
            }
        
        # Set version - start at 1 for new policies, increment for updates
        if item_exists:
            # Policy exists in DB, so increment version
            version_num = current_version + 1
        else:
            # New policy, start at version 1
            version_num = 1
        
        # Update DynamoDB
        action = 'Creating' if not item_exists else 'Updating'
        logger.info(f"{action} exception policy for {policy_key} to version {version_num}")
        
        # Prepare item for DynamoDB using correct schema (HashValue + AccountID)
        new_item = {
            'HashValue': hash_value,
            'AccountID': account_id,
            'ExceptionID': exception_id,
            'Service': service_name,
            'Version': version_num,
            'PolicyJSON': policy_json,
            'PolicyKey': policy_key,  # Keep for reference
            'Timestamp': datetime.utcnow().isoformat(),
            'Source': f's3://{bucket_name}/{object_key}',
            'S3Bucket': bucket_name,
            'S3Key': object_key
        }
        
        # Add policy to DynamoDB
        table.put_item(Item=new_item)
        
        logger.info(f"Successfully {action.lower()}d exception policy: {policy_key}")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Policy {action.lower()}d successfully",
                "exception": policy_key,
                "version": version_num
            })
        }
    
    except Exception as e:
        logger.error(f"Error processing exception policy {object_key}: {str(e)}")
        raise

@tracer.capture_method
def process_exception_policies(table_name: str, bucket_name: str) -> dict:
    """Process all exception policies from S3 bucket and update DynamoDB."""
    logger.info(f"Processing exception policies from bucket: {bucket_name} to table: {table_name}")
    
    try:
        # List policy files in S3 bucket
        logger.info(f"Listing objects in s3://{bucket_name}/policies/")
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix='policies/')
        
        if 'Contents' not in response or not response['Contents']:
            logger.info(f"No policy files found in s3://{bucket_name}/policies/")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No policy files found',
                    'results': {
                        'updated': 0,
                        'created': 0,
                        'skipped': 0,
                        'error': 0,
                        'details': []
                    }
                })
            }

        # Process each S3 object
        updated_policies = 0
        created_policies = 0
        skipped_policies = 0
        error_policies = 0
        result_details = []
        
        for obj in response['Contents']:
            key = obj['Key']
            
            # Skip directory markers or non-JSON files
            if key.endswith('/') or not key.endswith('.json'):
                logger.info(f"Skipping non-JSON file or directory: {key}")
                continue
            
            try:
                # Process each policy file individually
                result = process_exception_policy(table_name, bucket_name, key)
                result_body = json.loads(result.get('body', '{}'))
                
                if result.get('statusCode') == 200:
                    if "No changes in policy" in result_body.get('message', ''):
                        skipped_policies += 1
                        result_details.append({
                            "file": key,
                            "exception": result_body.get('exception'),
                            "status": "skipped",
                            "reason": "no changes"
                        })
                    elif "created" in result_body.get('message', ''):
                        created_policies += 1
                        result_details.append({
                            "file": key,
                            "exception": result_body.get('exception'),
                            "status": "created",
                            "version": result_body.get('version')
                        })
                    elif "updated" in result_body.get('message', ''):
                        updated_policies += 1
                        result_details.append({
                            "file": key,
                            "exception": result_body.get('exception'),
                            "status": "updated",
                            "version": result_body.get('version')
                        })
                else:
                    error_policies += 1
                    result_details.append({
                        "file": key,
                        "status": "error",
                        "reason": result_body.get('message', 'Unknown error')
                    })
            except Exception as e:
                logger.error(f"Error processing {key}: {str(e)}")
                error_policies += 1
                result_details.append({
                    "file": key,
                    "status": "error",
                    "reason": str(e)
                })
                # Continue processing other files
    
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Processed exception policies in DynamoDB',
                'results': {
                    'updated': updated_policies,
                    'created': created_policies,
                    'skipped': skipped_policies,
                    'error': error_policies,
                    'details': result_details
                }
            })
        }
        
    except Exception as e:
        logger.error(f"Error in exception policy processing: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f"Error updating exception policies: {str(e)}"
            })
        }

@tracer.capture_method
def process_s3_event(record):
    """Process S3 event for exception policy file uploads"""
    try:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        logger.info(f"Processing S3 object: s3://{bucket}/{key}")
        
        # Extract policy information from S3 object
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=bucket, Key=key)
        policy_content = response['Body'].read().decode('utf-8')
        
        # Process the policy content
        policy_data = json.loads(policy_content)
        store_exception_policy(policy_data, bucket, key)
        
    except Exception as e:
        logger.error(f"Error processing S3 event: {str(e)}")
        raise

@tracer.capture_method
def store_exception_policy(policy_data, bucket, key):
    """Store exception policy in DynamoDB"""
    try:
        # Extract metadata from S3 key
        key_parts = key.split('/')
        account_id_str = key_parts[2] if len(key_parts) > 2 else 'unknown'
        
        # Convert account ID to integer for DynamoDB (table schema expects Number)
        try:
            account_id = int(account_id_str) if account_id_str != 'unknown' else 0
        except ValueError:
            logger.warning(f"Could not parse account ID '{account_id_str}' as integer, using 0")
            account_id = 0
        
        # Generate hash value
        hash_value = generate_policy_hash(policy_data)
        
        # Store in DynamoDB
        table.put_item(
            Item={
                'HashValue': hash_value,
                'AccountID': account_id,
                'CommitID': extract_commit_id(key),
                'PolicyData': policy_data,
                'Timestamp': datetime.utcnow().isoformat(),
                'Source': f's3://{bucket}/{key}',
                'S3Bucket': bucket,
                'S3Key': key
            }
        )
        
        logger.info(f"Exception policy stored from S3: {hash_value}")
        
    except Exception as e:
        logger.error(f"Error storing exception policy: {str(e)}")
        raise

@tracer.capture_method
def generate_policy_hash(policy_data):
    """Generate a hash value for the policy"""
    import hashlib
    policy_string = json.dumps(policy_data, sort_keys=True)
    return hashlib.sha256(policy_string.encode()).hexdigest()[:16]

@tracer.capture_method
def extract_commit_id(s3_key):
    """Extract commit ID from S3 key"""
    # Assuming key format: policies/tenant/account-id/commit-id/policy.json
    key_parts = s3_key.split('/')
    return key_parts[3] if len(key_parts) > 3 else 'unknown'

@tracer.capture_method
def extract_service_from_actions(policy_data: dict, key: str = None) -> str:
    """Extract the AWS service name from policy actions or filename."""
    logger.info("Extracting service from policy actions")
    
    # Handle explicit ServiceName if available
    if 'ServiceName' in policy_data:
        service = policy_data['ServiceName'].lower()
        logger.info(f"Found explicit ServiceName in policy: {service}")
        return service
        
    statements = policy_data.get('Statement', [])
    if not statements:
        logger.warning("Policy has no 'Statement' field")
    else:
        # Ensure statements is a list
        if isinstance(statements, dict):
            statements = [statements]
            
        for statement in statements:
            actions = statement.get('Action', [])
            
            # Handle different action formats
            if isinstance(actions, str):
                actions = [actions]  # Convert single action to list
          
            if not isinstance(actions, list):
                continue
                
            for action in actions:
                if isinstance(action, str) and ':' in action and action != '*':
                    service = action.split(':')[0].lower()
                    if service:
                        logger.info(f"Extracted service: {service}")
                        return service
    
    # Fall back to filename if service couldn't be extracted from actions
    if key and key.endswith('.json'):
        filename = key.split('/')[-1].replace('.json', '').lower()
        logger.info(f"Using filename as service name fallback: {filename}")
        return filename
                    
    logger.warning("Could not extract service name from policy actions")
    return None

@tracer.capture_method
def extract_exception_id(policy_data: dict, key: str = None) -> str:
    """Extract the exception ID from policy data or filename."""
    # Try to get from policy data first
    if 'ExceptionID' in policy_data:
        exception_id = policy_data['ExceptionID'].lower()
        logger.info(f"Found explicit ExceptionID in policy: {exception_id}")
        return exception_id
    
    # Try to extract from metadata
    if 'Metadata' in policy_data and 'ExceptionID' in policy_data['Metadata']:
        exception_id = policy_data['Metadata']['ExceptionID'].lower()
        logger.info(f"Found ExceptionID in policy metadata: {exception_id}")
        return exception_id
    
    # Try to extract from path
    if key:
        path_parts = key.split('/')
        for part in path_parts:
            if part.startswith('exc-') or part.startswith('exception-'):
                logger.info(f"Found ExceptionID in path: {part}")
                return part
    
    # Default case - use a portion of the filename
    if key and key.endswith('.json'):
        filename = key.split('/')[-1].replace('.json', '')
        logger.info(f"Using filename as exception ID fallback: {filename}")
        return filename
    
    logger.warning("Could not extract exception ID")
    return None

@tracer.capture_method
def extract_account_id(policy_data: dict, key: str = None) -> str:
    """Extract AWS account ID from policy data or filename path."""
    # Try to get from policy data first
    if 'AccountID' in policy_data:
        account_id = policy_data['AccountID']
        logger.info(f"Found explicit AccountID in policy: {account_id}")
        return account_id
    
    # Try to extract from metadata
    if 'Metadata' in policy_data and 'AccountID' in policy_data['Metadata']:
        account_id = policy_data['Metadata']['AccountID']
        logger.info(f"Found AccountID in policy metadata: {account_id}")
        return account_id
    
    # Try to extract from path
    if key:
        path_parts = key.split('/')
        for part in path_parts:
            if part.isdigit() and len(part) == 12:  # AWS account IDs are 12 digits
                logger.info(f"Found AccountID in path: {part}")
                return part
    
    logger.info("No AccountID found")
    return None

def register_table_in_ssm(table_name, policy_type):
    """
    Registers the DynamoDB table ARN in SSM Parameter Store for cross-account access.
    
    Args:
        table_name: Name of the DynamoDB table
        policy_type: Type of policy (org, tenant, exception)
    """
    try:
        # Extract environment suffix from table name
        parts = table_name.split('-')
        if len(parts) >= 4:
            env_suffix = parts[-1]
        else:
            env_suffix = "preview"  # default
        
        # Get table ARN
        table = dynamodb.Table(table_name)
        table_arn = table.table_arn
        
        # Parameter name format: /prp/{policy_type}/table-arn-{env_suffix}
        param_name = f"/prp/{policy_type}/table-arn-{env_suffix}"
        
        # Store the ARN in SSM Parameter Store
        ssm_client.put_parameter(
            Name=param_name,
            Value=table_arn,
            Type='String',
            Overwrite=True,
            Description=f"ARN of the {policy_type} policy table for {env_suffix} environment"
        )
        
        logger.info(f"Registered table ARN in SSM: {param_name} = {table_arn}")
    
    except Exception as e:
        logger.error(f"Error registering table in SSM: {str(e)}")
