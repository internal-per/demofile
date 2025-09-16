"""Validation utilities for policy data."""
from typing import Dict, Any, Optional

def validate_policy_data(data: Dict[str, Any]) -> Optional[str]:
    """Validate policy data against required schema.
    
    Args:
        data: Dictionary containing policy data
        
    Returns:
        Optional[str]: Error message if validation fails, None if successful
    """
    required_fields = {
        'ServicePrefix': str,
        'Version': int,
        'PolicyJSON': dict,
        'CommitID': str
    }
    
    # Check for missing fields
    for field in required_fields:
        if field not in data:
            return f"Missing required field: {field}"
            
    # Validate field types
    for field, expected_type in required_fields.items():
        if not isinstance(data[field], expected_type):
            return f"Invalid type for {field}: expected {expected_type.__name__}, got {type(data[field]).__name__}"
            
    # Additional validation for PolicyJSON
    if not data['PolicyJSON']:
        return "PolicyJSON cannot be empty"
        
    # Service prefix validation
    if not data['ServicePrefix'].isalnum():
        return "ServicePrefix must be alphanumeric"
        
    # Version validation
    if data['Version'] < 1:
        return "Version must be greater than 0"
        
    return None

def validate_service_name(service_name: str) -> bool:
    """Validate AWS service name format.
    
    Args:
        service_name: Service identifier to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return bool(service_name and service_name.isalnum())