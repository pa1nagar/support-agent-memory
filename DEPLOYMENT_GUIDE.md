# 🚀 AWS Lambda Deployment Guide

## Prerequisites

1. AWS CLI installed and configured
2. AWS SAM CLI installed
3. Python 3.11+
4. AWS account with permissions for:
   - Lambda
   - CloudFormation
   - S3
   - IAM
   - Bedrock

## Quick Deploy (5 Minutes)

### Step 1: Install AWS SAM CLI (if not installed)

**Windows (PowerShell):**
```powershell
# Using Chocolatey
choco install aws-sam-cli

# Or download installer from:
# https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
```

**Verify installation:**
```powershell
sam --version
# Should show: SAM CLI, version 1.x.x
```

### Step 2: Review SAM Template

The `template.yaml` file is already configured. Review it:

```powershell
cat template.yaml
```

Key features:
- Python 3.11 runtime
- 512 MB memory
- 30-second timeout
- Environment variables from .env
- IAM role with Bedrock permissions
- Function URL (no API Gateway needed)

### Step 3: Build the Application

```powershell
cd "d:\Python World\Experiment\cockrochDB\support-agent-memory"
sam build
```

This will:
- Create `.aws-sam` directory
- Install Python dependencies
- Package the Lambda function

**Expected output:**
```
Build Succeeded

Built Artifacts  : .aws-sam\build
Built Template   : .aws-sam\build\template.yaml
```

### Step 4: Deploy (Guided - First Time)

```powershell
sam deploy --guided
```

**Answer the prompts:**

```
Stack Name: support-agent-memory
AWS Region: us-east-1
Parameter Environment: production
Parameter CockroachDBURL: [paste your connection string]
Parameter BedrockModelID: us.anthropic.claude-sonnet-4-6
Parameter BedrockEmbeddingModelID: amazon.titan-embed-text-v2:0
Confirm changes before deploy: Y
Allow SAM CLI IAM role creation: Y
Disable rollback: N
Save arguments to configuration file: Y
SAM configuration file: samconfig.toml
SAM configuration environment: default
```

**Deployment will take 2-3 minutes.**

### Step 5: Get Your Lambda URL

After deployment succeeds, look for:

```
Outputs
-------------------------------------------------------------------------------------
Key                 AgentFunctionUrl
Description         Function URL for Support Agent
Value               https://abc123.lambda-url.us-east-1.on.aws
-------------------------------------------------------------------------------------
```

**Copy this URL!** This is your live API endpoint.

### Step 6: Update Frontend

Edit `frontend/index.html`:

```javascript
// Change from:
const API_URL = 'http://localhost:8000';

// To:
const API_URL = 'https://YOUR_LAMBDA_URL.lambda-url.us-east-1.on.aws';
```

### Step 7: Deploy Frontend to S3

```powershell
# Create S3 bucket for frontend
aws s3 mb s3://support-agent-memory-frontend-YOURNAME

# Enable static website hosting
aws s3 website s3://support-agent-memory-frontend-YOURNAME --index-document index.html

# Upload files
aws s3 cp frontend/ s3://support-agent-memory-frontend-YOURNAME/ --recursive --acl public-read

# Get website URL
echo "http://support-agent-memory-frontend-YOURNAME.s3-website-us-east-1.amazonaws.com"
```

---

## Subsequent Deploys (After First Time)

After initial guided deploy, use:

```powershell
sam build && sam deploy
```

No prompts - uses saved config from `samconfig.toml`

---

## Environment Variables

Set these in AWS Systems Manager Parameter Store for better security:

```powershell
# Store CockroachDB URL
aws ssm put-parameter --name /support-agent/cockroachdb-url --value "postgresql://..." --type SecureString

# Update template.yaml to reference:
# !Sub '{{resolve:ssm:/support-agent/cockroachdb-url}}'
```

---

## Testing Deployed Lambda

### Test Health Endpoint

```powershell
curl https://YOUR_LAMBDA_URL.lambda-url.us-east-1.on.aws/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-07-26T14:00:00Z",
  "version": "1.0.0",
  "environment": "production"
}
```

### Test Chat Endpoint

```powershell
curl -X POST https://YOUR_LAMBDA_URL.lambda-url.us-east-1.on.aws/chat `
  -H "Content-Type: application/json" `
  -d '{\"user_id\":\"test-user\",\"message\":\"Hello!\"}'
```

---

## Monitoring

### View Logs

```powershell
# Stream live logs
sam logs --stack-name support-agent-memory --tail

# Or use AWS CLI
aws logs tail /aws/lambda/support-agent-memory-agent --follow
```

### CloudWatch Dashboard

1. Go to: https://console.aws.amazon.com/cloudwatch/
2. Navigate to: Logs → Log groups
3. Find: `/aws/lambda/support-agent-memory-agent`
4. Click to view logs

### Metrics to Monitor

- **Invocations**: Number of requests
- **Duration**: Response time (should be 10-20s)
- **Errors**: Should be near zero
- **Throttles**: Should be zero

---

## Cost Estimate

### AWS Lambda
- **Free Tier**: 1M requests/month, 400K GB-seconds
- **After Free Tier**: $0.20 per 1M requests
- **Your Usage (estimated)**: $0-5/month

### AWS Bedrock
- **Claude Sonnet 4.6**: ~$3 per 1M input tokens
- **Titan Embeddings**: ~$0.10 per 1M tokens
- **Your Usage (estimated)**: $5-10/month for testing

### CockroachDB
- **Free Tier**: 10 GB storage, unlimited requests
- **Your Usage**: Well within free tier

### S3 (Frontend Hosting)
- **Free Tier**: 5 GB storage, 15 GB transfer
- **Your Usage**: ~$0.10/month

**Total Monthly Cost: $5-15** (mostly Bedrock)

---

## Troubleshooting

### Error: "CREATE_FAILED" during deploy

**Cause**: Usually IAM permissions or resource limits

**Solution**:
```powershell
# Check CloudFormation events
aws cloudformation describe-stack-events --stack-name support-agent-memory --max-items 10

# Delete failed stack
aws cloudformation delete-stack --stack-name support-agent-memory

# Retry deployment
sam deploy --guided
```

### Error: "AccessDenied" for Bedrock

**Cause**: Bedrock models not enabled in your region

**Solution**:
1. Go to: https://console.aws.amazon.com/bedrock/
2. Click "Model access" in left sidebar
3. Click "Enable specific models"
4. Enable: Claude Sonnet 4.6 and Titan Embeddings V2
5. Wait 2-3 minutes for approval
6. Retry deployment

### Error: Lambda timeout after 30 seconds

**Cause**: Database connection slow or Bedrock throttling

**Solution**:
1. Increase timeout in `template.yaml`:
   ```yaml
   Timeout: 60  # Increase from 30 to 60
   ```
2. Redeploy: `sam build && sam deploy`

### Error: "Cannot connect to CockroachDB"

**Cause**: Connection string incorrect or firewall

**Solution**:
1. Verify connection string in Parameter Store
2. Test locally first: `python backend/handler.py`
3. Check CockroachDB firewall allows AWS IPs

---

## Rollback

If something goes wrong:

```powershell
# Rollback to previous version
aws cloudformation rollback-stack --stack-name support-agent-memory

# Or delete entire stack
aws cloudformation delete-stack --stack-name support-agent-memory
```

---

## Production Checklist

Before sharing your Lambda URL publicly:

- [ ] Environment variables set correctly
- [ ] Secrets not hardcoded
- [ ] IAM role has minimum permissions
- [ ] CORS configured properly
- [ ] Rate limiting enabled (if needed)
- [ ] CloudWatch alarms set up
- [ ] Logs are being generated
- [ ] Health check returns 200 OK
- [ ] Chat endpoint works
- [ ] Memory retrieval works
- [ ] Frontend updated with Lambda URL
- [ ] Frontend deployed to S3
- [ ] S3 bucket policy allows public read

---

## Cleanup (After Hackathon)

To avoid charges after the hackathon:

```powershell
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name support-agent-memory

# Delete S3 frontend bucket
aws s3 rb s3://support-agent-memory-frontend-YOURNAME --force

# Delete CloudWatch logs (optional)
aws logs delete-log-group --log-group-name /aws/lambda/support-agent-memory-agent
```

---

## 🎯 Success Criteria

After deployment, you should have:

1. ✅ Lambda function URL (live API)
2. ✅ S3 static website URL (live frontend)
3. ✅ Both URLs working and accessible
4. ✅ No errors in CloudWatch logs
5. ✅ Able to send chat messages and get responses
6. ✅ Memory retrieval working in production

**Deployment time: ~20 minutes total**

---

## Next Steps

1. Test your deployed app thoroughly
2. Copy Lambda URL for Devpost submission
3. Copy S3 website URL for demo
4. Record demo video showing LIVE deployed app
5. Submit to hackathon!

**You're ready to win!** 🏆
