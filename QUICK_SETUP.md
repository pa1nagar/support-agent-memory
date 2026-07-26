# ⚡ Quick Setup - Seed Database in 10 Minutes

## Prerequisites

Before seeding, you need:

1. ✅ **CockroachDB Account** with connection string
2. ✅ **AWS Account** with Bedrock access enabled
3. ✅ **Python 3.11+** installed

---

## Step 1: CockroachDB Setup (3 minutes)

### Option A: Create New Cluster

1. Go to: https://cockroachlabs.cloud/signup
2. Sign up (free tier)
3. Create cluster in **us-east-1** region
4. Copy connection string from "Connect" button
5. Format: `postgresql://user:pass@cluster.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full`

### Option B: Use Existing Cluster

Already have CockroachDB? Just get your connection string.

---

## Step 2: AWS Bedrock Setup (2 minutes)

### Enable Model Access:

1. AWS Console → Search "Bedrock"
2. Select region: **us-east-1** (top right)
3. Click "Model access" (left sidebar)
4. Click "Enable specific models"
5. Check:
   - ✅ **Claude 3.5 Sonnet** (Anthropic)
   - ✅ **Titan Embeddings G1 - Text v2** (Amazon)
6. Click "Request model access"
7. Wait ~2 minutes (usually instant)

### Configure AWS CLI:

```bash
# Install if needed
# Windows: https://awscli.amazonaws.com/AWSCLIV2.msi
# Mac: brew install awscli

# Configure
aws configure
# Enter your Access Key ID and Secret Access Key
# Default region: us-east-1
# Output format: json
```

---

## Step 3: Project Setup (2 minutes)

```bash
# Navigate to project
cd "d:\Python World\Experiment\cockrochDB\support-agent-memory"

# Create virtual environment (recommended)
python -m venv venv

# Activate
venv\Scripts\activate

# Install dependencies
pip install -r backend\requirements.txt
```

---

## Step 4: Configure Environment (1 minute)

```bash
# Copy template
copy .env.example .env

# Edit .env (use notepad or any editor)
notepad .env
```

**Required values in .env:**

```env
# Your CockroachDB connection string
COCKROACHDB_URL=postgresql://user:pass@cluster.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full

# AWS Region (must match Bedrock)
AWS_REGION=us-east-1

# These should be correct by default
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
```

**Save and close.**

---

## Step 5: Run Database Schema (1 minute)

### Option A: Using CockroachDB CLI

```bash
# Install cockroach CLI if needed
# Windows: Download from https://www.cockroachlabs.com/docs/stable/install-cockroachdb-windows

# Run schema
cockroach sql --url="YOUR_CONNECTION_STRING_HERE" < database\schema.sql
```

### Option B: Using Cloud Console

1. Go to CockroachDB Cloud Console
2. Click your cluster
3. Click "SQL Shell" tab
4. Open `database/schema.sql` in text editor
5. Copy all contents
6. Paste into SQL Shell
7. Press Enter

**Verify:**

```sql
SHOW TABLES;
-- Should show: users, conversations, messages, user_context, memory_audit
```

---

## Step 6: Pre-flight Check (1 minute)

```bash
cd backend
python setup_check.py
```

**Expected output:**

```
✅ ALL CHECKS PASSED!
Ready to seed database!
```

**If checks fail:**
- Read the error messages carefully
- Most common: Wrong CockroachDB URL or Bedrock not enabled
- Fix issues and run `setup_check.py` again

---

## Step 7: Seed Database! 🎉

```bash
# Seed with default (10 users, 2 conversations each)
python seed_data.py

# Or specify custom amounts
python seed_data.py 20 3
# 20 users, 3 conversations each = ~480 messages

# For large dataset (for demo video)
python seed_data.py 50 4
# 50 users, 4 conversations each = ~1600 messages
```

**Confirm when prompted:**

```
Seeding database with 10 users, 2 conversations each
Total messages: ~160
Continue? (y/n): y
```

**Watch it run:**

```
Creating user 1/10: user-0001
  Conversation 1/2: abc123...
    Stored message pair 1/4
    Stored message pair 2/4
    ...
✅ Seed complete!
   Users created: 10
   Messages stored: 160
   Time elapsed: 45.2 seconds
   Average: 0.28s per message
```

---

## Step 8: Verify Data

```bash
# Check message count
python -c "
from database import get_db_manager
db = get_db_manager()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) as count FROM messages')
        print(f'Messages: {cur.fetchone()[\"count\"]}')
        cur.execute('SELECT COUNT(*) as count FROM messages WHERE embedding IS NOT NULL')
        print(f'With embeddings: {cur.fetchone()[\"count\"]}')
"
```

**Expected:**

```
Messages: 160
With embeddings: 160
```

---

## Troubleshooting

### "COCKROACHDB_URL not set"

- Check `.env` file exists
- Verify `COCKROACHDB_URL=` line is uncommented
- No spaces around `=` sign
- URL must start with `postgresql://`

### "Bedrock access denied"

- Go to AWS Console → Bedrock → Model access
- Verify both Claude and Titan show "Access granted"
- Check region is us-east-1
- Wait 5 minutes and try again

### "Database connection failed"

- Verify CockroachDB cluster is running (check Cloud Console)
- Check connection string format: `postgresql://user:pass@host:26257/db?sslmode=verify-full`
- Ensure `?sslmode=verify-full` is at the end
- Check firewall/network not blocking port 26257

### "Missing tables"

- Run schema: `cockroach sql --url="..." < database\schema.sql`
- Or copy/paste schema into Cloud Console SQL Shell

### "Import errors"

- Ensure virtual environment activated: `venv\Scripts\activate`
- Reinstall: `pip install -r backend\requirements.txt`
- Check Python version: `python --version` (need 3.11+)

---

## Next Steps After Seeding

Once seeding completes:

### Test Locally:

```bash
python handler.py
# Visit: http://localhost:8000
```

### Test Chat:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"user-0001\",\"message\":\"I have login issues\"}"
```

### View Memory Debug:

```bash
curl http://localhost:8000/memory-debug/user-0001
```

### Deploy to AWS:

```bash
cd ..
sam build
sam deploy --guided
```

---

## Quick Reference

**Seed again (fresh data):**

```bash
# Delete old data
cockroach sql --url="YOUR_URL" -e "TRUNCATE messages, conversations, users CASCADE;"

# Seed new data
python seed_data.py 10 2
```

**Check data:**

```bash
# Count messages
cockroach sql --url="YOUR_URL" -e "SELECT COUNT(*) FROM messages;"

# See sample messages
cockroach sql --url="YOUR_URL" -e "SELECT content FROM messages LIMIT 5;"
```

**Test vector search:**

```bash
python -c "
from bedrock_client import get_bedrock_client
from database import get_db_manager

bedrock = get_bedrock_client()
db = get_db_manager()

embedding = bedrock.generate_embedding('login problem')
results = db.search_similar_messages('user-0001', embedding, limit=3)
print(f'Found {len(results)} similar messages')
for r in results:
    print(f'  - {r[\"content\"][:50]}... (similarity: {r[\"similarity\"]:.2f})')
"
```

---

## Cost Estimate

**For seeding:**
- 10 users, 2 convs = 160 messages × 2 embeddings = 320 Bedrock calls
- Cost: 320 × $0.0001 = **$0.032** (~3 cents)

**For 50 users, 4 convs:**
- ~1600 messages × 2 = 3200 calls
- Cost: **$0.32** (~32 cents)

Totally affordable! 💰

---

## Ready?

Run the pre-flight check:

```bash
cd backend
python setup_check.py
```

If all green, seed the database:

```bash
python seed_data.py
```

🎉 **You'll have a working AI agent with real memory in 10 minutes!**
