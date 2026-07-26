# 🚀 Complete Setup Guide

This guide walks you through setting up the Support Agent Memory project from scratch, with screenshots and troubleshooting tips.

## ⏱️ Estimated Time: 30 minutes

---

## 📋 Step 1: CockroachDB Account Setup (5 minutes)

### 1.1 Create Account

1. Visit: https://cockroachlabs.cloud/signup
2. Sign up with email or GitHub
3. Verify your email

### 1.2 Create Cluster

1. Click **"Create Cluster"**
2. Select **"Serverless"** (free tier)
3. Choose region: **us-east-1** (same as Bedrock)
4. Name your cluster: `support-agent-db`
5. Click **"Create cluster"**
6. Wait ~30 seconds for provisioning

### 1.3 Get Connection String

1. Click **"Connect"** button
2. Select **"General connection string"**
3. Create SQL user (or use default `root`)
4. Copy the connection string:
   ```
   postgresql://username:password@cluster-name.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
   ```
5. **IMPORTANT:** Save this securely (you'll need it later)

### 1.4 Run Database Schema

**Option A: Using CockroachDB SQL Client**
```bash
# Install cockroach CLI
# macOS: brew install cockroachdb/tap/cockroach
# Windows: Download from https://www.cockroachlabs.com/docs/stable/install-cockroachdb-windows

# Run schema
cockroach sql --url="YOUR_CONNECTION_STRING" < database/schema.sql
```

**Option B: Using Cloud Console**
1. Go to CockroachDB Cloud Console
2. Click **"SQL Shell"** tab
3. Copy contents of `database/schema.sql`
4. Paste and run

**Verify:**
```sql
SHOW TABLES;
-- Should show: users, conversations, messages, user_context, memory_audit
```

---

## 🔧 Step 2: AWS Account Setup (10 minutes)

### 2.1 Create AWS Account

1. Visit: https://aws.amazon.com/free/
2. Sign up (requires credit card, but free tier is sufficient)
3. Complete verification

### 2.2 Enable Amazon Bedrock

1. Log in to AWS Console
2. Search for **"Bedrock"** in services
3. Select region: **us-east-1** (top right)
4. Click **"Model access"** (left sidebar)
5. Click **"Enable specific models"**
6. Select:
   - ✅ **Claude 3.5 Sonnet** (Anthropic)
   - ✅ **Titan Embeddings G1 - Text v2** (Amazon)
7. Click **"Request model access"**
8. Wait 2-5 minutes for approval (usually instant)

**Verify:**
- Status should show **"Access granted"** for both models

### 2.3 Configure AWS CLI

```bash
# Install AWS CLI
# Windows: https://awscli.amazonaws.com/AWSCLIV2.msi
# macOS: brew install awscli
# Linux: pip install awscli

# Configure credentials
aws configure

# Enter:
# - AWS Access Key ID: [from IAM console]
# - AWS Secret Access Key: [from IAM console]
# - Default region: us-east-1
# - Default output format: json
```

**Get Access Keys:**
1. AWS Console → IAM → Users → Your user
2. Security credentials tab
3. Create access key → CLI → Create
4. Download CSV (save securely!)

### 2.4 Install AWS SAM CLI

**Windows:**
```bash
# Download installer
# https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

# Run MSI installer
```

**macOS:**
```bash
brew install aws-sam-cli
```

**Linux:**
```bash
# Follow guide: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
```

**Verify:**
```bash
sam --version
# Should show: SAM CLI, version 1.xx.x
```

---

## 💻 Step 3: Local Development Setup (5 minutes)

### 3.1 Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/support-agent-memory.git
cd support-agent-memory
```

### 3.2 Install Python Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### 3.3 Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit .env with your values
# Windows: notepad .env
# macOS/Linux: nano .env
```

**Required variables:**
```env
COCKROACHDB_URL=postgresql://user:pass@cluster.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
AWS_REGION=us-east-1
```

### 3.4 Test Locally (Optional)

```bash
cd backend
python handler.py

# Visit: http://localhost:8000
# API docs: http://localhost:8000/docs
```

**Test endpoints:**
```bash
# Health check
curl http://localhost:8000/health

# Chat (mock data in Phase 0)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","message":"hello"}'
```

---

## ☁️ Step 4: Deploy to AWS (10 minutes)

### 4.1 Build Application

```bash
# From project root
sam build

# Should see: Build Succeeded
```

### 4.2 Deploy to AWS

```bash
sam deploy --guided

# Answer prompts:
```

**Deployment Prompts:**
```
Stack Name: support-agent-memory
AWS Region: us-east-1
Parameter CockroachDBURL: [paste your connection string]
Parameter Environment: development
Parameter MemoryRetrievalLimit: 5
Parameter MemorySimilarityThreshold: 0.7
Confirm changes before deploy: Y
Allow SAM CLI IAM role creation: Y
Disable rollback: N
Save arguments to configuration file: Y
SAM configuration file: samconfig.toml
SAM configuration environment: default
```

**Wait 2-3 minutes for deployment...**

### 4.3 Get Deployment Outputs

After successful deployment, note these values:

```
CloudFormation outputs:
---------------------------------------------
Key: ApiUrl
Value: https://xyz123.lambda-url.us-east-1.on.aws

Key: FrontendUrl  
Value: http://bucket-name.s3-website-us-east-1.amazonaws.com
```

**Save these URLs!**

### 4.4 Update Frontend Configuration

```bash
# Edit frontend/index.html
# Find line: const API_URL = 'YOUR_LAMBDA_URL_HERE';
# Replace with your ApiUrl from above

# Windows:
notepad frontend/index.html

# macOS/Linux:
nano frontend/index.html
```

### 4.5 Deploy Frontend

```bash
# Upload to S3 bucket (from deployment outputs)
aws s3 cp frontend/index.html s3://YOUR_BUCKET_NAME/ --acl public-read

# Get frontend URL from deployment outputs
echo "Frontend: http://YOUR_BUCKET_NAME.s3-website-us-east-1.amazonaws.com"
```

---

## ✅ Step 5: Verify Deployment (2 minutes)

### 5.1 Test API Endpoints

```bash
# Health check
curl https://YOUR_LAMBDA_URL/health

# Expected: {"status":"healthy","timestamp":"...","version":"1.0.0","environment":"development"}

# Chat endpoint (Phase 0 uses mock data)
curl -X POST https://YOUR_LAMBDA_URL/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "message": "I need help with login"
  }'

# Expected: {"response":"...","conversation_id":"...","memories_used":[...],"processing_time_ms":123}
```

### 5.2 Test Frontend

1. Open frontend URL in browser
2. Type a message: "I can't log in"
3. Send message
4. Should see response with mock memories in sidebar

### 5.3 Check CloudWatch Logs

```bash
# View logs
aws logs tail /aws/lambda/support-agent-memory-agent --follow

# Or via AWS Console:
# CloudWatch → Log groups → /aws/lambda/support-agent-memory-agent
```

---

## 🎉 Success!

You now have a **working Phase 0 deployment**:

✅ CockroachDB schema created  
✅ Lambda function deployed  
✅ Frontend hosted on S3  
✅ Mock memory retrieval working  

**Next Steps (Phase 1):**
- Integrate real Bedrock Titan embeddings
- Implement vector search
- Store actual memories in CockroachDB

---

## 🐛 Troubleshooting

### Database Connection Errors

**Error:** `connection refused`

**Solution:**
1. Check CockroachDB connection string format
2. Ensure cluster is running (Cloud Console)
3. Verify SSL mode: `?sslmode=verify-full`
4. Check firewall/network settings

### Bedrock Access Denied

**Error:** `AccessDeniedException`

**Solution:**
1. Verify model access granted in Bedrock console
2. Check IAM role has `bedrock:InvokeModel` permission
3. Confirm region is `us-east-1`
4. Wait 5 minutes after requesting access

### Lambda Deployment Fails

**Error:** `CREATE_FAILED`

**Solution:**
1. Check SAM CLI version: `sam --version` (need 1.50+)
2. Verify AWS credentials: `aws sts get-caller-identity`
3. Check CloudFormation console for detailed error
4. Ensure unique S3 bucket name (add account ID)

### Frontend Shows Error

**Error:** `Failed to fetch`

**Solution:**
1. Check API URL in `frontend/index.html`
2. Verify Lambda function URL is public
3. Check CORS settings in `template.yaml`
4. Open browser console for detailed error

### Local Testing Issues

**Error:** `ModuleNotFoundError`

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Reinstall dependencies
pip install -r backend/requirements.txt

# Check Python version
python --version  # Need 3.11+
```

---

## 💰 Cost Estimate

**Free Tier (sufficient for hackathon):**
- CockroachDB: Free 10 GiB storage
- AWS Lambda: 1M free requests/month
- Bedrock: Pay-per-use (~$0.01/conversation)
- S3: First 5 GB free

**Estimated hackathon cost: $5-10 total**

---

## 📞 Getting Help

- **Issues:** [GitHub Issues](https://github.com/YOUR_USERNAME/support-agent-memory/issues)
- **CockroachDB Support:** [Community Slack](https://cockroa.ch/slack)
- **AWS Support:** [Forums](https://forums.aws.amazon.com/)

---

**Ready for Phase 1?** See `WINNING_STRATEGY.md` for next steps!
