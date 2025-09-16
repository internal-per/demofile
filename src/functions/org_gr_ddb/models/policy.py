"""Policy data model for organization guardrails."""
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class Policy:
    """Policy data model matching DynamoDB structure.
    
    Attributes:
        ServicePrefix (str): AWS service identifier
        Version (int): Policy version number
        PolicyJSON (Dict[str, Any]): Policy document
        CommitID (str): Git commit ID
    """
    ServicePrefix: str
    Version: int
    PolicyJSON: Dict[str, Any]
    CommitID: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format.
        
        Returns:
            Dict[str, Any]: Dictionary representation
        """
        return {
            'ServicePrefix': self.ServicePrefix,
            'Version': self.Version,
            'PolicyJSON': self.PolicyJSON,
            'CommitID': self.CommitID
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Policy':
        """Create Policy from dictionary.
        
        Args:
            data: Dictionary containing policy data
            
        Returns:
            Policy: New Policy instance
        """
        return cls(
            ServicePrefix=data['ServicePrefix'],
            Version=data['Version'],
            PolicyJSON=data['PolicyJSON'],
            CommitID=data['CommitID']
        )