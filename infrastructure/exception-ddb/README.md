# Tenant Exception DDB Infrastructure

This directory contains the SAM (Serverless Application Model) template for deploying the Tenant Exception Policy processing infrastructure.

## Infrastructure Components

### DynamoDB Table

- **Table Name**: `tenant-exception-ga-{environment}` (where environment is preview/nonprod/prod)
- **Primary Key**: `exception` (String) - Composite key with exception ID and/or service name
- **Billing Mode**: Pay-per-request for automatic scaling
- **Deletion Protection**: Enabled for production environments

### Lambda Function

- **Function Name**: `prp-{environment}-tenant-exception-policy-processor`
- **Runtime**: Python 3.11
- **Architecture**: x86_64
- **Memory**: 128 MB
- **Timeout**: 30 seconds
- **Environment Variables**:
  - `TABLE_NAME`: DynamoDB table name
  - `AWS_XRAY_TRACING_NAME`: X-Ray tracing configuration

### EventBridge Rules

- **Rule Name**: `prp-{environment}-tenant-exception-s3-rule`
- **Event Pattern**: S3 object creation events
- **Target**: Lambda function for policy processing

### IAM Roles

- **Lambda Execution Role**: `tenant-custom-tenant-exception-processor-role-{environment}`
- **Permissions**:
  - DynamoDB read/write access
  - S3 object read access
  - CloudWatch Logs write access
  - X-Ray tracing permissions
  - SSM parameter read/write access

### SSM Parameters

- **Parameter Name**: `/tenant/exception/dynamodb/{environment}/table-arn`
- **Description**: Stores DynamoDB table ARN for cross-account access
- **Type**: String

## Deployment

### GitHub Actions Deployment

This infrastructure is automatically deployed via the **Deploy Tenant Exception DDB** workflow:

```yaml
# Triggered by changes to:
# - infrastructure/exception-ddb/**
# - src/functions/tenant-exception-ddb/**
```

### Deployment Environments

| Environment | Stack Name | Table Name | Deployment Trigger |
|-------------|------------|------------|-------------------|
| **Preview** | `prp-tenant-exception-policies-preview` | `tenant-exception-ga-preview` | Push to `TTRS-*` branches |
| **Non-Production** | `prp-tenant-exception-policies-nonprod` | `tenant-exception-ga-nonp` | PR merge to `main` |
| **Production** | `prp-tenant-exception-policies-prod` | `tenant-exception-ga-prod` | PR merge to `prod` |

### Manual Deployment

```bash
# Navigate to this directory
cd infrastructure/exception-ddb

# Build the SAM application
sam build

# Deploy with guided prompts
sam deploy --guided

# Or deploy with parameters
sam deploy \
  --parameter-overrides \
    PolicyType=tenant \
    ServiceType=exception \
    EnvSuffix=dev \
    Environment=development \
    OrganizationId=YOUR_ORG_ID \
    TableName=tenant-exception-ga-dev \
    LambdaRoleName=tenant-custom-tenant-exception-processor-role-dev
```

## Template Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `PolicyType` | Type of policy (tenant/org) | `tenant` | Yes |
| `ServiceType` | Service type (exception/guardrails) | `exception` | Yes |
| `EnvSuffix` | Environment suffix | `dev` | Yes |
| `Environment` | Full environment name | `development` | Yes |
| `OrganizationId` | AWS Organization ID | - | Yes |
| `TableName` | DynamoDB table name | - | Yes |
| `LambdaRoleName` | Lambda execution role name | - | Yes |

## Template Outputs

| Output | Description | Export Name |
|--------|-------------|-------------|
| `TenantExceptionTable` | DynamoDB table name | `TenantExceptionTable-{Environment}` |
| `TenantExceptionTableArn` | DynamoDB table ARN | `TenantExceptionTableArn-{Environment}` |
| `TenantExceptionFunction` | Lambda function name | `TenantExceptionFunction-{Environment}` |
| `TenantExceptionFunctionArn` | Lambda function ARN | `TenantExceptionFunctionArn-{Environment}` |

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
aws cloudformation describe-stacks --stack-name prp-tenant-exception-policies-dev

# View logs
sam logs -n TenantExceptionPolicyProcessor --stack-name prp-tenant-exception-policies-dev --tail

# Local testing
sam local invoke TenantExceptionPolicyProcessor --event events/s3-event.json
```
