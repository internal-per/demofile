import json
import os
import boto3
import logging
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.data_classes import S3Event
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key
from datetime import datetime

logger = Logger()
tracer = Tracer()

# Initialize AWS client
dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
ssm_client = boto3.client("ssm")

# Set up logging
logging.basicConfig(level=logging.INFO)

def process_s3_event(record, table):
    """Process S3 event for tenant policy file uploads"""
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
        store_tenant_policy(policy_data, bucket, key, table)
        
    except Exception as e:
        logger.error(f"Error processing S3 event: {str(e)}")
        raise

def process_tenant_policy(event, table):
    """Process tenant policy data directly"""
    try:
        # Extract policy data from event
        policy_data = event.get('policy_data', {})
        account_id = event.get('account_id', 'unknown')
        
        # Generate hash value for the policy
        hash_value = generate_policy_hash(policy_data)
        
        # Store in DynamoDB
        response = table.put_item(
            Item={
                'HashValue': hash_value,
                'AccountID': account_id,
                'CommitID': event.get('commit_id', 'manual'),
                'PolicyData': policy_data,
                'Timestamp': datetime.utcnow().isoformat(),
                'Source': event.get('source', 'direct'),
                'Environment': event.get('environment', 'unknown'),
                'PolicyType': 'tenant-guardrails'
            }
        )
        
        logger.info(f"Tenant guardrails policy stored with HashValue: {hash_value}")
        return {'hash_value': hash_value, 'account_id': account_id}
        
    except Exception as e:
        logger.error(f"Error processing tenant policy: {str(e)}")
        raise

def store_tenant_policy(policy_data, bucket, key, table):
    """Store tenant policy in DynamoDB"""
    try:
        # Extract metadata from S3 key
        key_parts = key.split('/')
        account_id = key_parts[2] if len(key_parts) > 2 else 'unknown'
        
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
                'S3Key': key,
                'PolicyType': 'tenant-guardrails'
            }
        )
        
        logger.info(f"Tenant guardrails policy stored from S3: {hash_value}")
        
    except Exception as e:
        logger.error(f"Error storing tenant policy: {str(e)}")
        raise

def generate_policy_hash(policy_data):
    """Generate a hash value for the policy"""
    import hashlib
    policy_string = json.dumps(policy_data, sort_keys=True)
    return hashlib.sha256(policy_string.encode()).hexdigest()[:16]

def extract_commit_id(s3_key):
    """Extract commit ID from S3 key"""
    # Assuming key format: policies/tenant/account-id/commit-id/policy.json
    key_parts = s3_key.split('/')
    return key_parts[3] if len(key_parts) > 3 else 'unknown'

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """
    Process tenant policy updates from S3 and update DynamoDB with the specific schema required for tenant policies.
    
    Args:
        event: S3 event that triggered the function or direct invocation event
        context: Lambda context
        
    Returns:
        Response dictionary with status information
    """
    try:
        # Determine the type of event (S3 notification or direct invocation)
        if 'Records' in event and event['Records'] and event['Records'][0].get('eventSource') == 'aws:s3':
            # S3 event notification case
            s3_event = S3Event(event)
            bucket_name = s3_event.bucket_name
            object_key = s3_event.object_key
            
            # For S3 notifications, use configured table name from environment variable
            table_name = os.environ["TABLE_NAME"]
            
            # Register table in SSM for cross-account access
            register_table_in_ssm(table_name, "tenant")
            
            logger.info(f"Processing new tenant policy: {object_key} from {bucket_name}")
            return process_tenant_policy(table_name, bucket_name, object_key)
        else:
            # Direct invocation case for batch processing
            parameters = event.get('parameters', {})
            table_name = parameters.get('TABLE_NAME') or os.environ.get("TABLE_NAME")
            bucket_name = parameters.get('BUCKET_NAME')
            
            # Register/update SSM parameter
            register_table_in_ssm(table_name, "tenant")
            
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
            return process_tenant_policies(table_name, bucket_name)
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise

@tracer.capture_method
def process_tenant_policy(table_name: str, bucket_name: str, object_key: str) -> dict:
    """Process a tenant policy file from S3 and update DynamoDB with the tenant-specific table structure."""
    logger.info(f"Processing tenant policy file: {object_key} from bucket: {bucket_name}")
    
    try:
        # Read policy file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        policy_content = response["Body"].read().decode("utf-8")
        policy_data = json.loads(policy_content)
        
        # Get DynamoDB table
        table = dynamodb.Table(table_name)

        # Extract policy metadata
        path_parts = object_key.split('/')
        file_name = path_parts[-1]
        
        # Extract account ID
        account_id = None
        for part in path_parts:
            if part.isdigit() and len(part) == 12:  # AWS account IDs are 12 digits
                account_id = part
                break
        
        # If account ID not in path, try to get it from policy content
        if not account_id and 'AccountID' in policy_data:
            account_id = policy_data['AccountID']
        
        # If still no account ID, use policy metadata or default
        if not account_id:
            account_id = policy_data.get('Metadata', {}).get('AccountID', 'unknown')
        
        # Extract service prefixes from policy actions
        service_prefixes = extract_service_prefixes_from_actions(policy_data)
        if not service_prefixes:
            logger.warning(f"No service prefixes found in policy {object_key}, using default")
            service_prefixes = ['unknown']
        
        # Get policy name and commit ID
        policy_name = file_name.replace('.json', '')
        commit_id = policy_data.get('CommitID', '')
            
        # Create the primary key: AccountIDServicePrefix
        account_id_service_prefix = f"{account_id}:{':'.join(service_prefixes)}"
        
        # Check if the item already exists
        response = table.get_item(Key={
            'AccountIDServicePrefix': account_id_service_prefix,
            'PolicyName': policy_name
        })
        
        item_exists = 'Item' in response
        if item_exists:
            current_item = response['Item']
            current_version = int(current_item.get('Version', 0))
            current_policy_json = current_item.get('PolicyJSON', {})
        else:
            current_version = 0
            current_policy_json = {}
        
        # Extract the policy JSON object
        policy_json = {
            'Version': policy_data.get('Version', '2012-10-17'),
            'Statement': policy_data.get('Statement', [])
        }
        
        # Check if policy has changed
        if json.dumps(policy_json, sort_keys=True) == json.dumps(current_policy_json, sort_keys=True):
            logger.info(f"No changes in tenant policy {policy_name}, skipping update")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No changes in policy',
                    'policyName': policy_name,
                    'accountIdServicePrefix': account_id_service_prefix
                })
            }
        
        # Increment version for existing items
        version_num = current_version + 1 if item_exists else 1
        
        # Create the new item with the tenant-specific schema
        new_item = {
            'AccountIDServicePrefix': account_id_service_prefix,
            'PolicyName': policy_name,
            'Version': version_num,
            'CommitID': commit_id,
            'PolicyJSON': policy_json
        }
        
        # Update DynamoDB
        action = 'Creating' if not item_exists else 'Updating'
        logger.info(f"{action} tenant policy {policy_name} for {account_id_service_prefix} to version {version_num}")
        
        # Add policy to DynamoDB
        table.put_item(Item=new_item)
        
        logger.info(f"Successfully {action.lower()}d tenant policy: {policy_name}")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Policy {action.lower()}d successfully",
                "policyName": policy_name,
                "accountIdServicePrefix": account_id_service_prefix,
                "version": version_num
            })
        }
    
    except Exception as e:
        logger.error(f"Error processing tenant policy {object_key}: {str(e)}")
        raise

@tracer.capture_method
def process_tenant_policies(table_name: str, bucket_name: str) -> dict:
    """Process all tenant policies from S3 bucket and update DynamoDB."""
    logger.info(f"Processing tenant policies from bucket: {bucket_name} to table: {table_name}")
    
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
                    'bucket': bucket_name
                })
            }
            
        # Process each policy file
        updated_policies = 0
        created_policies = 0
        skipped_policies = 0
        error_policies = 0
        result_details = []
        
        for item in response['Contents']:
            key = item['Key']
            
            # Skip directories and non-JSON files
            if key.endswith('/') or not key.lower().endswith('.json'):
                continue
                
            logger.info(f"Processing tenant policy file: {key}")
            
            try:
                result = process_tenant_policy(table_name, bucket_name, key)
                result_body = json.loads(result.get('body', '{}'))
                
                if result.get('statusCode') == 200:
                    action = result_body.get('message', '')
                    if 'No changes' in action:
                        skipped_policies += 1
                        result_details.append({
                            "file": key,
                            "policyName": result_body.get('policyName'),
                            "accountIdServicePrefix": result_body.get('accountIdServicePrefix'),
                            "status": "skipped",
                            "reason": "No changes"
                        })
                    elif 'created' in action:
                        created_policies += 1
                        result_details.append({
                            "file": key,
                            "policyName": result_body.get('policyName'),
                            "accountIdServicePrefix": result_body.get('accountIdServicePrefix'),
                            "status": "created",
                            "version": result_body.get('version')
                        })
                    elif 'updated' in action:
                        updated_policies += 1
                        result_details.append({
                            "file": key,
                            "policyName": result_body.get('policyName'),
                            "accountIdServicePrefix": result_body.get('accountIdServicePrefix'),
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
                logger.error(f"Error processing tenant policy {key}: {str(e)}")
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
                'message': 'Processed tenant policies in DynamoDB',
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
        logger.error(f"Error in tenant policy processing: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f"Error updating tenant policies: {str(e)}"
            })
        }

@tracer.capture_method
def extract_service_prefixes_from_actions(policy_data: dict) -> list:
    """Extract the AWS service prefixes from policy actions."""
    logger.info("Extracting service prefixes from policy actions")
    
    service_prefixes = set()
    
    # Extract from explicit ServicePrefixes if available
    if 'ServicePrefixes' in policy_data:
        if isinstance(policy_data['ServicePrefixes'], list):
            for prefix in policy_data['ServicePrefixes']:
                service_prefixes.add(prefix.lower())
        else:
            service_prefixes.add(policy_data['ServicePrefixes'].lower())
        
        if service_prefixes:
            logger.info(f"Found explicit ServicePrefixes in policy: {service_prefixes}")
            return list(service_prefixes)
    
    # Extract from policy statements
    statements = policy_data.get('Statement', [])
    if not statements:
        logger.warning("Policy has no 'Statement' field")
        return list(service_prefixes)
        
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
                    service_prefixes.add(service)
    
    logger.info(f"Extracted service prefixes: {service_prefixes}")
    return list(service_prefixes)

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
