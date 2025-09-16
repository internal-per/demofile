# Organization Guardrails DDB Infrastructure

This directory contains the SAM (Serverless Application Model) template for deploying the Organization Guardrails Policy processing infrastructure.

## Infrastructure Components

### DynamoDB Table

- **Table Name**: `org-guardrails-ga-{environment}` (where environment is dev/nonprod/prod)
- **Primary Key**: `services` (String) - AWS service name derived from policy actions
- **Billing Mode**: Pay-per-request for automatic scaling
- **Deletion Protection**: Enabled for production environments

### Lambda Function

- **Function Name**: `prp-{environment}-org-guardrails-policy-processor`
- **Runtime**: Python 3.11
- **Architecture**: x86_64
- **Memory**: 128 MB
- **Timeout**: 30 seconds
- **Environment Variables**:
  - `TABLE_NAME`: DynamoDB table name
  - `AWS_XRAY_TRACING_NAME`: X-Ray tracing configuration

### EventBridge Rules

- **Rule Name**: `prp-{environment}-org-guardrails-s3-rule`
- **Event Pattern**: S3 object creation events
- **Target**: Lambda function for policy processing

### IAM Roles

- **Lambda Execution Role**: `org-custom-org-guardrails-processor-role-{environment}`
- **Permissions**:
  - DynamoDB read/write access
  - S3 object read access
  - CloudWatch Logs write access
  - X-Ray tracing permissions
  - SSM parameter read/write access

### SSM Parameters

- **Parameter Name**: `/org/guardrails/dynamodb/{environment}/table-arn`
- **Description**: Stores DynamoDB table ARN for cross-account access
- **Type**: String

## Deployment

### GitHub Actions Deployment

This infrastructure is automatically deployed via the **Deploy Organization Guardrails DDB** workflow:

```yaml
# Triggered by changes to:
# - infrastructure/org-ddb/**
# - src/functions/org-gr-ddb/**
```

### Deployment Environment Strategy

| Branch/PR Target | Environment | Stack Name | Deployment Trigger |
|------------------|-------------|------------|-------------------|
| `TTRS-*` branches | Development | `prp-org-guardrails-policies-dev` | Push to feature branches |
| PR → `main` | Non-Production | `prp-org-guardrails-policies-nonprod` | PR merge to main |
| PR → `prod` | Production | `prp-org-guardrails-policies-prod` | PR merge to prod |

### Manual Deployment

```bash
# Navigate to this directory
cd infrastructure/org-ddb

# Build the SAM application
sam build

# Deploy with guided prompts
sam deploy --guided

# Or deploy with parameters
sam deploy \
  --parameter-overrides \
    PolicyType=org \
    ServiceType=guardrails \
    Environment=development \
    OrganizationId=YOUR_ORG_ID
```

## Template Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `PolicyType` | Type of policy (org/tenant) | `org` | Yes |
| `ServiceType` | Service type (guardrails) | `guardrails` | Yes |
| `Environment` | Environment name (dev/nonprod/prod) | `dev` | Yes |
| `OrganizationId` | AWS Organization ID | - | Yes |

## Template Outputs

| Output | Description | Export Name |
|--------|-------------|-------------|
| `OrgGuardrailsTable` | DynamoDB table name | `OrgGuardrailsTable-{Environment}` |
| `OrgGuardrailsTableArn` | DynamoDB table ARN | `OrgGuardrailsTableArn-{Environment}` |
| `OrgGuardrailsFunction` | Lambda function name | `OrgGuardrailsFunction-{Environment}` |
| `OrgGuardrailsFunctionArn` | Lambda function ARN | `OrgGuardrailsFunctionArn-{Environment}` |

## Schema Details

### DynamoDB Item Structure

```json
{
  "services": "ec2",
  "Version": 1,
  "PolicyJSON": "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"ec2:*\"],\"Resource\":\"*\"}]}"
}
```

### Service Extraction Logic

The function extracts AWS service names from:

1. **Explicit ServiceName field** in the policy metadata
2. **Policy actions** - extracts service prefix from actions like `ec2:DescribeInstances`
3. **Filename fallback** - derives service from filename if actions parsing fails

## Monitoring and Observability

- **CloudWatch Logs**: Automatic log group creation with 30-day retention
- **X-Ray Tracing**: Enabled for performance monitoring and debugging
- **CloudWatch Metrics**: Lambda execution metrics and DynamoDB metrics
- **AWS Config**: Resource compliance monitoring (if enabled)

## Security Features

- **Resource-based Policies**: DynamoDB table allows cross-account access within organization
- **IAM Least Privilege**: Lambda function has minimal required permissions
- **Encryption**: DynamoDB encryption at rest using AWS managed keys
- **Organization Boundary**: Access restricted to AWS Organization members

## Use Cases

### Organization-Level Policy Management

- **Service-Specific Policies**: Store policies organized by AWS service
- **Cross-Account Access**: Enable policy consumption across organization accounts
- **Version Control**: Track policy changes with version numbering
- **Compliance**: Maintain organization-wide policy compliance

### Integration Patterns

- **S3 Event Processing**: Automatic policy ingestion from S3 uploads
- **Cross-Account Consumption**: Other accounts query policies via DynamoDB resource policies
- **CI/CD Integration**: Automated policy deployment via GitHub Actions
- **Audit Trail**: Policy changes tracked through version numbers

## Troubleshooting

### Common Issues

1. **Service Extraction Fails**: Ensure policies have valid AWS actions or explicit ServiceName field
2. **Cross-Account Access Denied**: Verify organization membership and resource policies
3. **Deployment Fails**: Check AWS credentials and CloudFormation permissions
4. **Function Errors**: Review CloudWatch logs for detailed error information

### Useful Commands

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name prp-org-guardrails-policies-dev

# View logs
sam logs -n OrgGuardrailsPolicyProcessor --stack-name prp-org-guardrails-policies-dev --tail

# Local testing
sam local invoke OrgGuardrailsPolicyProcessor --event events/s3-event.json

# Query DynamoDB table
aws dynamodb scan --table-name org-guardrails-ga-dev
```

## Best Practices

- **Policy Naming**: Use descriptive service-based naming conventions
- **Version Management**: Always increment versions for policy updates
- **Testing**: Use local SAM testing before deployment
- **Monitoring**: Set up CloudWatch alarms for function errors and DynamoDB throttling
