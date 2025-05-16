import boto3
import json
import sys
import os

dynamodb = boto3.client('dynamodb')

def get_latest_version(table_name, service):
    """Retrieve the latest version for a service from the DynamoDB table."""
    response = dynamodb.query(
        TableName=table_name,
        KeyConditionExpression='services = :s',
        ExpressionAttributeValues={':s': {'S': service}},
    )
    items = response.get('Items', [])
    if not items:
        return None
    # Extract numerical versions (e.g., 'V1' -> 1)
    versions = [int(item['version']['S'][1:]) for item in items]
    max_version = max(versions)
    return f'V{max_version}'

def get_next_version(current_version):
    """Generate the next version number."""
    if not current_version:
        return 'V1'
    num = int(current_version[1:])
    return f'V{num + 1}'

def update_dynamodb(file_path, table_name):
    """Update the DynamoDB table with the new service version."""
    # Extract service name (e.g., 'data/ec2.json' -> 'Ec2')
    service = os.path.splitext(os.path.basename(file_path))[0].capitalize()
    
    # Read JSON data
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    # Get and increment version
    latest_version = get_latest_version(table_name, service)
    next_version = get_next_version(latest_version)
    
    # Prepare item (all values as strings for simplicity)
    item = {
        'services': {'S': service},
        'version': {'S': next_version}
    }
    for key, value in data.items():
        item[key] = {'S': str(value)}  # Adjust if other types are needed
    
    # Insert into DynamoDB with a condition to prevent overwriting
    dynamodb.put_item(
        TableName=table_name,
        Item=item,
        ConditionExpression='attribute_not_exists(services) AND attribute_not_exists(version)'
    )
    print(f"Inserted {service} version {next_version} into {table_name}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python update_dynamodb.py <file_path> <table_name>")
        sys.exit(1)
    update_dynamodb(sys.argv[1], sys.argv[2])