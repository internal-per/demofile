# Tenant Exception Policy Processor

This Lambda function processes exception policies with an exception-based schema as part of the TETRIS TARv2 policy management system.

## DynamoDB Table Schema for Exception Policies

### Primary Key

- **exception** (String): A composite key consisting of the exception ID and/or service name.
  - Format: `{exceptionId}:{serviceName}` or just `{exceptionId}`
  - Example: `exc-123:ec2` or `exception-456`

### Secondary Attributes

- **Version** (Number): Policy version number, incremented with each update.
- **AccountID** (String, Optional): The AWS account ID associated with this exception.
- **PolicyJSON** (String): JSON string representation of the policy document.

## Function Overview

This Lambda function handles:

1. Processing exception policies from S3 bucket events
2. Extracting exception IDs and/or service names from policy content or file paths
3. Creating appropriate keys for DynamoDB storage
4. Incrementing version numbers as policies are updated
5. Registering the table ARN in SSM Parameter Store for cross-account access

## Policy Processing Logic

The function extracts the exception ID from:

1. Explicit `ExceptionID` field in the policy if present
2. The `Metadata.ExceptionID` field if present
3. Path components that start with `exc-` or `exception-`
4. Falling back to the filename as a last resort

## GitHub Actions Workflow

This function is deployed via the **Deploy Tenant Exception DDB** workflow (`.github/workflows/deploy-tenant-exception.yml`).

### Workflow Triggers

- **Push events** to `TTRS-*` branches for development testing
- **Pull Request merges** to `main` and `prod` branches for deployments
- **Path-based triggers**: Only when files in `infrastructure/exception-ddb/**` or `src/functions/tenant-exception-ddb/**` are modified

### Deployment Environments

| Environment | Stack Name | Table Name | Purpose |
|-------------|------------|------------|---------|
| **Preview** (dev) | `prp-tenant-exception-policies-preview` | `tenant-exception-ga-preview` | Development testing |
| **Non-Production** | `prp-tenant-exception-policies-nonprod` | `tenant-exception-ga-nonp` | Integration testing |
| **Production** | `prp-tenant-exception-policies-prod` | `tenant-exception-ga-prod` | Live production |

### Pipeline Stages

1. **Setup & Validation**: Environment setup, dependency installation, script validation
2. **Unit Testing**: 13 comprehensive test cases with coverage reporting (minimum 50%)
3. **Environment Determination**: Automatic environment detection based on branch/PR
4. **SAM Deployment**: Infrastructure and Lambda function deployment
5. **Verification**: Stack status and table population verification

### Testing Coverage

- **13 test cases** covering all major functionality
- **pytest** with **moto** AWS mocking for isolated testing
- **Coverage reporting** with HTML and XML output
- **JUnit XML** for CI/CD integration

## Related Resources

- S3 bucket for policy storage
- EventBridge rules for S3 event processing
- DynamoDB table with resource-based policies
- SSM parameters for cross-account access
- CloudFormation stack for infrastructure management

## Local Development

### Running Tests

```bash
# Run all tests for this function
pytest src/functions/tenant-exception-ddb/ -v

# Run with coverage
pytest src/functions/tenant-exception-ddb/ --cov=src/functions/tenant-exception-ddb --cov-report=html -v
```

### Local Deployment

```bash
# Navigate to infrastructure directory
cd infrastructure/exception-ddb

# Build and deploy
sam build
sam deploy --guided
```
