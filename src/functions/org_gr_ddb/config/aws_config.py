"""Configuration settings for organization guardrails."""
import os
from typing import Dict, Any

class AWSConfig:
    """AWS configuration settings."""
    
    @staticmethod
    def get_dynamodb_config() -> Dict[str, Any]:
        """Get DynamoDB configuration.
        
        Returns:
            Dict[str, Any]: Configuration dictionary
            
        Raises:
            ValueError: If required environment variables are missing
        """
        table_name = os.environ.get('TABLE_NAME')
        if not table_name:
            raise ValueError('TABLE_NAME environment variable is required')
            
        return {
            'table_name': table_name,
            'region_name': os.environ.get('AWS_REGION', 'ap-southeast-2')
        }

def validate_environment() -> None:
    """Validate required environment variables.
    
    Raises:
        ValueError: If required variables are missing
    """
    required_vars = ['TABLE_NAME', 'AWS_REGION']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        raise ValueError(f'Missing required environment variables: {", ".join(missing_vars)}')