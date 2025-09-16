"""Service layer for policy operations."""
import boto3
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError

from ..models.policy import Policy
from ..utils.validators import validate_policy_data
from ..config.aws_config import AWSConfig

class PolicyService:
    """Service for managing organization policies."""
    
    def __init__(self):
        """Initialize DynamoDB client and table."""
        config = AWSConfig.get_dynamodb_config()
        self.dynamodb = boto3.resource('dynamodb', region_name=config['region_name'])
        self.table = self.dynamodb.Table(config['table_name'])
    
    def get_policy(self, service_prefix: str, version: int) -> Optional[Policy]:
        """Retrieve policy by service prefix and version.
        
        Args:
            service_prefix: AWS service identifier
            version: Policy version number
            
        Returns:
            Optional[Policy]: Policy if found, None otherwise
            
        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            response = self.table.get_item(
                Key={
                    'ServicePrefix': service_prefix,
                    'Version': version
                }
            )
            item = response.get('Item')
            return Policy.from_dict(item) if item else None
        except ClientError as e:
            raise e
    
    def create_policy(self, policy: Policy) -> bool:
        """Create new policy.
        
        Args:
            policy: Policy to create
            
        Returns:
            bool: True if successful, False if policy exists
            
        Raises:
            ValueError: If policy data is invalid
            ClientError: If DynamoDB operation fails
        """
        # Validate policy data
        error = validate_policy_data(policy.to_dict())
        if error:
            raise ValueError(error)
            
        try:
            self.table.put_item(
                Item=policy.to_dict(),
                ConditionExpression='attribute_not_exists(ServicePrefix) AND attribute_not_exists(Version)'
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise e
    
    def update_policy(self, policy: Policy) -> bool:
        """Update existing policy.
        
        Args:
            policy: Policy to update
            
        Returns:
            bool: True if successful, False if policy doesn't exist
            
        Raises:
            ValueError: If policy data is invalid
            ClientError: If DynamoDB operation fails
        """
        # Validate policy data
        error = validate_policy_data(policy.to_dict())
        if error:
            raise ValueError(error)
            
        try:
            self.table.put_item(
                Item=policy.to_dict(),
                ConditionExpression='attribute_exists(ServicePrefix) AND attribute_exists(Version)'
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise e
    
    def list_policies(self, service_prefix: str) -> List[Policy]:
        """List all versions of a service policy.
        
        Args:
            service_prefix: AWS service identifier
            
        Returns:
            List[Policy]: List of policies
            
        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            response = self.table.query(
                KeyConditionExpression='ServicePrefix = :prefix',
                ExpressionAttributeValues={':prefix': service_prefix}
            )
            return [Policy.from_dict(item) for item in response.get('Items', [])]
        except ClientError as e:
            raise e
    
    def delete_policy(self, service_prefix: str, version: int) -> bool:
        """Delete policy by service prefix and version.
        
        Args:
            service_prefix: AWS service identifier
            version: Policy version number
            
        Returns:
            bool: True if successful, False if policy doesn't exist
            
        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            self.table.delete_item(
                Key={
                    'ServicePrefix': service_prefix,
                    'Version': version
                },
                ConditionExpression='attribute_exists(ServicePrefix) AND attribute_exists(Version)'
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise e