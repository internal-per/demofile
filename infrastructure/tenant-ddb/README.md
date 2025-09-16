# Tenant Guardrails DDB Infrastructure

This directory contains the SAM (Serverless Application Model) template for deploying the Tenant Guardrails Policy processing infrastructure.

## Infrastructure Components

### DynamoDB Table

- **Table Name**: `tenant-gr-ga-{environment}` (where environment is preview/nonprod/prod)
- **Primary Key**: `AccountIDServicePrefix` (String) - Composite key with Account ID and service prefixes
- **Sort Key**: `PolicyName` (String) - Policy name identifier
- **Billing Mode**: Pay-per-request for automatic scaling
- **Deletion Protection**: Enabled for production environments

### Lambda Function

- **Function Name**: `prp-{environment}-tenant-gr-policy-processor`
- **Runtime**: Python 3.11
- **Architecture**: x86_64
- **Memory**: 128 MB
- **Timeout**: 30 seconds
- **Environment Variables**:
  - `TABLE_NAME`: DynamoDB table name
  - `AWS_XRAY_TRACING_NAME`: X-Ray tracing configuration

### EventBridge Rules

- **Rule Name**: `prp-{environment}-tenant-gr-s3-rule`
- **Event Pattern**: S3 object creation events
- **Target**: Lambda function for policy processing

### IAM Roles

- **Lambda Execution Role**: `tenant-custom-tenant-guardrails-processor-role-{environment}`
- **Permissions**:
  - DynamoDB read/write access
  - S3 object read access
  - CloudWatch Logs write access
  - X-Ray tracing permissions
  - SSM parameter read/write access

### SSM Parameters

- **Parameter Name**: `/tenant/guardrails/dynamodb/{environment}/table-arn`
- **Description**: Stores DynamoDB table ARN for cross-account access
- **Type**: String

## Deployment

### GitHub Actions Deployment

This infrastructure is automatically deployed via the **Deploy Tenant Guardrails DDB** workflow:

```yaml
# Triggered by changes to:
# - infrastructure/tenant-ddb/**
# - src/functions/tenant-gr-ddb/**
```

### Deployment Environments

| Environment | Stack Name | Table Name | Deployment Trigger |
|-------------|------------|------------|-------------------|
| **Preview** | `prp-tenant-gr-policies-preview` | `tenant-gr-ga-preview` | Push to `TTRS-*` branches |
| **Non-Production** | `prp-tenant-gr-policies-nonprod` | `tenant-gr-ga-nonp` | PR merge to `main` |
| **Production** | `prp-tenant-gr-policies-prod` | `tenant-gr-ga-prod` | PR merge to `prod` |

### Manual Deployment

```bash
# Navigate to this directory
cd infrastructure/tenant-ddb

# Build the SAM application
sam build

# Deploy with guided prompts
sam deploy --guided

# Or deploy with parameters
sam deploy \
  --parameter-overrides \
    PolicyType=tenant \
    ServiceType=guardrails \
    EnvSuffix=dev \
    Environment=development \
    OrganizationId=YOUR_ORG_ID \
    TableName=tenant-gr-ga-dev \
    LambdaRoleName=tenant-custom-tenant-guardrails-processor-role-dev
```

## Template Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `PolicyType` | Type of policy (tenant/org) | `tenant` | Yes |
| `ServiceType` | Service type (guardrails/exception) | `guardrails` | Yes |
| `EnvSuffix` | Environment suffix | `dev` | Yes |
| `Environment` | Full environment name | `development` | Yes |
| `OrganizationId` | AWS Organization ID | - | Yes |
| `TableName` | DynamoDB table name | - | Yes |
| `LambdaRoleName` | Lambda execution role name | - | Yes |

## Template Outputs

| Output | Description | Export Name |
|--------|-------------|-------------|
| `TenantGuardrailsTable` | DynamoDB table name | `TenantGuardrailsTable-{Environment}` |
| `TenantGuardrailsTableArn` | DynamoDB table ARN | `TenantGuardrailsTableArn-{Environment}` |
| `TenantGuardrailsFunction` | Lambda function name | `TenantGuardrailsFunction-{Environment}` |
| `TenantGuardrailsFunctionArn` | Lambda function ARN | `TenantGuardrailsFunctionArn-{Environment}` |

## Schema Details

### DynamoDB Item Structure

```json
{
  "AccountIDServicePrefix": "595412020923:ec2:rds:s3",
  "PolicyName": "ec2frontendstack",
  "Version": 1,
  "CommitID": "437c01f9d5a0ab921ae7dbf288b12431fa9b793d",
  "PolicyJSON": {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": ["ec2:*", "rds:*", "s3:*"],
        "Resource": "*"
      }
    ]
  }
}
```

## Monitoring and Observability

- **CloudWatch Logs**: Automatic log group creation with 30-day retention
- **X-Ray Tracing**: Enabled for performance monitoring and debugging
- **CloudWatch Metrics**: Lambda execution metrics and DynamoDB metrics
- **AWS Config**: Resource compliance monitoring (if enabled)

## Security Features

- **Resource-based Policies**: DynamoDB table allows cross-account access within organization
- **IAM Least Privilege**: Lambda function has minimal required permissions
- **Encryption**: DynamoDB encryption at rest using AWS managed keys
- **VPC Integration**: Optional VPC configuration for enhanced security

## Troubleshooting

### Common Issues

1. **Deployment Fails**: Check AWS credentials and permissions
2. **Function Timeout**: Increase timeout in template.yaml if processing large policies
3. **Access Denied**: Verify IAM role permissions and resource policies
4. **Table Not Found**: Ensure DynamoDB table is created before function execution

### Useful Commands

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name prp-tenant-gr-policies-dev

# View logs
sam logs -n TenantGuardrailsPolicyProcessor --stack-name prp-tenant-gr-policies-dev --tail

# Local testing
sam local invoke TenantGuardrailsPolicyProcessor --event events/s3-event.json
```
