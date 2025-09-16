"""Lambda handler for organization guardrails DynamoDB operations.

This module exposes `handler` which routes simple CRUD-like API Gateway
requests to service functions. Use relative imports so the module works
when packaged as a Lambda function with its folder as the package root.
"""

import json
from typing import Dict, Any, Optional

from .models.policy import Policy
from .services.policy_service import PolicyService
from .config.aws_config import validate_environment

# Initialize policy service once per cold-start
policy_service = PolicyService()


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body

    Returns:
        Dict[str, Any]: Formatted response
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def handle_create_policy(body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST policy request.

    Args:
        body: Request body
    Returns:
        Dict[str, Any]: Response with creation status
    """
    try:
        policy = Policy.from_dict(body)
        if policy_service.create_policy(policy):
            return create_response(201, {"message": "Policy created successfully"})
        return create_response(409, {"error": "Policy already exists"})
    except (ValueError, KeyError) as e:
        return create_response(400, {"error": str(e)})


def _get_query_params(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return query params dict for API Gateway v1/v2 compatibility."""
    params = event.get("queryStringParameters") or {}
    # For HTTP API v2 the event shape may differ; leave as-is for now.
    return params


def handle_get_policy(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET policy request."""
    params = _get_query_params(event)
    service_prefix = params.get("service")
    version = params.get("version")

    if not service_prefix:
        return create_response(400, {"error": "Missing service parameter"})

    if version:
        try:
            version = int(version)
            policy = policy_service.get_policy(service_prefix, version)
            if not policy:
                return create_response(404, {"error": "Policy not found"})
            return create_response(200, {"policy": policy.to_dict()})
        except ValueError:
            return create_response(400, {"error": "Invalid version parameter"})

    # If no version, try to get latest. PolicyService may provide get_latest_policy
    get_latest = getattr(policy_service, "get_latest_policy", None)
    if callable(get_latest):
        policy = get_latest(service_prefix)
        if not policy:
            return create_response(404, {"error": "Policy not found"})
        return create_response(200, {"policy": policy.to_dict()})

    # Fallback: list all and pick highest version
    policies = policy_service.list_policies(service_prefix)
    if not policies:
        return create_response(404, {"error": "Policy not found"})
    latest = max(policies, key=lambda p: p.Version)
    return create_response(200, {"policy": latest.to_dict()})


def handle_update_policy(body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle PUT policy request."""
    try:
        policy = Policy.from_dict(body)
        if policy_service.update_policy(policy):
            return create_response(200, {"message": "Policy updated successfully"})
        return create_response(404, {"error": "Policy not found"})
    except (ValueError, KeyError) as e:
        return create_response(400, {"error": str(e)})


def handle_delete_policy(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle DELETE policy request."""
    params = _get_query_params(event)
    service_prefix = params.get("service")
    version = params.get("version")

    if not service_prefix or not version:
        return create_response(400, {"error": "Missing service or version parameter"})

    try:
        version = int(version)
        if policy_service.delete_policy(service_prefix, version):
            return create_response(200, {"message": "Policy deleted successfully"})
        return create_response(404, {"error": "Policy not found"})
    except ValueError:
        return create_response(400, {"error": "Invalid version parameter"})


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for policy operations.

    Routes based on API Gateway v1 `httpMethod` key. Validate environment
    variables at runtime so missing configuration surfaces clearly.
    """
    try:
        validate_environment()

        body = json.loads(event.get("body", "{}"))
        operation = event.get("httpMethod")

        if operation == "GET":
            return handle_get_policy(event)
        if operation == "POST":
            return handle_create_policy(body)
        if operation == "PUT":
            return handle_update_policy(body)
        if operation == "DELETE":
            return handle_delete_policy(event)

        return create_response(400, {"error": "Invalid operation"})

    except ValueError as e:
        return create_response(400, {"error": str(e)})
    except Exception as e:
        return create_response(500, {"error": f"Internal error: {str(e)}"})
