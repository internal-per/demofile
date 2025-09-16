# Tenant Guardrails Policy Processor

This Lambda function processes tenant-specific policies with a composite key schema as part of the TETRIS TARv2 policy management system.

## DynamoDB Table Schema for Tenant Policies

### Primary Key

- **AccountIDServicePrefix** (String): A composite key consisting of the AWS Account ID and service prefixes separated by colons.
  - Format: `{AccountId}:{service1}:{service2}:{serviceN}`
  - Example: `595412020923:ec2:rds:s3`

### Sort Key

- **PolicyName** (String): Name of the policy, alphanumeric.
  - Example: `ec2frontendstack`

### Attributes

- **Version** (Number): Policy version number, incremented with each update.
- **CommitID** (String): Git commit ID used for reconciliation and verification.
  - Example: `437c01f9d5a0ab921ae7dbf288b12431fa9b793d`
- **PolicyJSON** (Map): The actual policy document.

  ```json
  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Effect": "Allow",
              "Action": [
                  "ec2:launchinstance",
                  "s3:listbuckets",
                  "s3:getobjects"
              ],
              "Resource": "*"
          }
      ]
  }
  ```

## Function Overview

This Lambda function handles:

1. Processing tenant policies from S3 bucket events
2. Extracting service prefixes from policy actions
3. Creating the composite primary key from AWS Account ID and service prefixes
4. Storing policies in DynamoDB with the proper schema
5. Incrementing version numbers as policies are updated
6. Registering the table ARN in SSM Parameter Store for cross-account access

## GitHub Actions Workflow

This function is deployed via the **Deploy Tenant Guardrails DDB** workflow (`.github/workflows/deploy-tenant-guardrails.yml`).

### Workflow Triggers

- **Push events** to `TTRS-*` branches for development testing
- **Pull Request merges** to `main` and `prod` branches for deployments
- **Path-based triggers**: Only when files in `infrastructure/tenant-ddb/**` or `src/functions/tenant-gr-ddb/**` are modified

### Deployment Environments

| Environment | Stack Name | Table Name | Purpose |
|-------------|------------|------------|---------|
| **Preview** (dev) | `prp-tenant-gr-policies-preview` | `tenant-gr-ga-preview` | Development testing |
| **Non-Production** | `prp-tenant-gr-policies-nonprod` | `tenant-gr-ga-nonp` | Integration testing |
| **Production** | `prp-tenant-gr-policies-prod` | `tenant-gr-ga-prod` | Live production |

### Pipeline Stages

1. **Setup & Validation**: Environment setup, dependency installation, script validation
2. **Unit Testing**: 2 comprehensive test cases with coverage reporting (minimum 50%)
3. **Environment Determination**: Automatic environment detection based on branch/PR
4. **SAM Deployment**: Infrastructure and Lambda function deployment
5. **Verification**: Stack status and table population verification

### Testing Coverage

- **2 test cases** covering core functionality
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
pytest src/functions/tenant-gr-ddb/ -v

# Run with coverage
pytest src/functions/tenant-gr-ddb/ --cov=src/functions/tenant-gr-ddb --cov-report=html -v
```

### Local Deployment

```bash
# Navigate to infrastructure directory
cd infrastructure/tenant-ddb

# Build and deploy
sam build
sam deploy --guided
```
