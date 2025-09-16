# Organization Guardrails Policy Processor

This Lambda function processes organization-level policies with a service-based schema as part of the TETRIS TARv2 policy management system.

## DynamoDB Table Schema

### Primary Key
- **ServicePrefix** (String): The AWS service name derived from policy actions.
  - Example: `ec2`, `s3`, `rds`
- **Version** (Number): Policy version number, incremented with each update.

### Attributes
- **PolicyJSON** (Map): JSON representation of the policy document.
- **CommitID** (String): Git commit ID for version tracking.

## Function Overview

This Lambda function handles:

1. Processing organization-level policies from S3 bucket events
2. Extracting service name from policy actions or filename
3. Storing policies in DynamoDB with service-based indexing
4. Incrementing version numbers as policies are updated
5. Validating policy structure and content

## Policy Processing Logic

The function extracts the AWS service name from:

1. Explicit `ServicePrefix` field in the policy if present
2. The first part of AWS actions (before the colon) in the policy statements
3. Validating against allowed service prefixes

## Environment Variables

- **TABLE_NAME**: DynamoDB table name (e.g., org-guardrails-preview)
- **AWS_REGION**: AWS region for service endpoints

## GitHub Actions Workflow

This function is deployed via the **Deploy Organization Guardrails DDB** workflow (`.github/workflows/deploy-org-guardrails.yml`).

### Workflow Triggers

- **Push events** to `TTRS-*` branches for development testing
- **Pull Request merges** to `main` and `prod` branches for deployments
- **Path-based triggers**: Only when files in `infrastructure/org-ddb/**` or `src/functions/org_gr_ddb/**` are modified

### Deployment Environment Strategy

| Branch/PR Target | Environment | Purpose |
|------------------|-------------|---------|
| `TTRS-*` branches | preview | Feature development and testing |
| PR → `main` | nonp | Integration testing and validation |
| PR → `prod` | prod | Live production deployment |

### Pipeline Stages

1. **Setup & Validation**
   - Environment setup
   - Python script validation
   - AWS wrapper validation

2. **Unit Testing**
   - Minimum 50% code coverage requirement
   - Comprehensive test suite
   - Coverage reporting (HTML, XML)
   - JUnit XML test results

3. **Environment Determination**
   - Automatic environment detection
   - Environment-specific configurations
   - Stack naming conventions

4. **SAM Deployment**
   - Template validation
   - Build optimization
   - Deployment with retries
   - Stack protection

5. **Verification**
   - Stack status verification
   - DynamoDB table validation
   - Data population checks
   - Resource policy validation

## Infrastructure Resources

- **S3 Bucket**
  - Versioning enabled
  - Public access blocked (bucket and account level)
  - EventBridge notifications

- **DynamoDB Table**
  - On-demand capacity
  - Resource-based policies
  - Organization-scoped access

- **Lambda Function**
  - Python 3.11 runtime
  - 900 second timeout
  - Minimal deployment package
  - Environment-based configuration

- **IAM Roles**
  - Least privilege permissions
  - Resource-level conditions
  - Organization ID restrictions

## Local Development

### Prerequisites

- Python 3.11
- AWS SAM CLI
- AWS credentials configured

### Environment Setup

```bash
# Set environment variables
export TABLE_NAME="test-org-guardrails-table"
export AWS_REGION="ap-southeast-2"
```

### Running Tests

```bash
# Run all tests with coverage
pytest -v --cov=. --cov-report=term-missing

# Run specific test file
pytest test_org_policy.py -v
```

### Local Deployment

```bash
# Navigate to infrastructure directory
cd infrastructure/org-ddb

# Build and deploy
sam build
sam deploy --guided
