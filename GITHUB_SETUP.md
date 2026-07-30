# 🚀 GitHub Setup Instructions

## Step 1: Create GitHub Repository

1. Go to: https://github.com/new
2. Repository name: **support-agent-memory**
3. Description: **AI Support Agent with Persistent Memory - CockroachDB × AWS Hackathon**
4. **Make it PUBLIC** (required for hackathon)
5. **DO NOT** initialize with README (we already have one)
6. Click "Create repository"

## Step 2: Push Your Code

Open PowerShell in the project root and run these commands:

```powershell
# Navigate to project directory
cd "d:\Python World\Experiment\cockrochDB\support-agent-memory"

# Initialize Git repository
git init

# Add all files
git add .

# Create first commit
git commit -m "Initial commit - Support Agent Memory for CockroachDB × AWS Hackathon"

# Set main branch
git branch -M main

# Add remote (REPLACE YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/support-agent-memory.git

# Push to GitHub
git push -u origin main
```

## Step 3: Verify on GitHub

1. Go to: https://github.com/YOUR_USERNAME/support-agent-memory
2. You should see:
   - ✅ All your files
   - ✅ README.md displayed on homepage
   - ✅ MIT License badge
   - ✅ Repository is public

## Step 4: Add Topics (Optional but Recommended)

On your GitHub repo page:
1. Click "⚙️ Settings" → "Manage topics"
2. Add these topics:
   - `cockroachdb`
   - `aws-bedrock`
   - `ai-agent`
   - `vector-database`
   - `fastapi`
   - `python`
   - `hackathon`

## Step 5: Update README with Your Repo URL

After pushing, update the clone command in README.md:

```bash
# Replace YOUR_USERNAME with your actual GitHub username
git clone https://github.com/YOUR_USERNAME/support-agent-memory.git
```

Then commit and push:

```powershell
git add README.md
git commit -m "Update README with correct repo URL"
git push
```

## Troubleshooting

### Error: "remote origin already exists"
```powershell
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/support-agent-memory.git
```

### Error: "authentication failed"
You need to use a Personal Access Token (PAT):
1. Go to: https://github.com/settings/tokens
2. Generate new token (classic)
3. Select scopes: `repo`
4. Use token as password when pushing

### Error: "permission denied"
Make sure the repository is created on GitHub first!

---

## ✅ Success Checklist

After pushing, verify:
- [ ] Repository is PUBLIC
- [ ] README displays correctly
- [ ] MIT License is visible
- [ ] All code files are present
- [ ] .env file is NOT pushed (check .gitignore working)
- [ ] No secrets in the repository

---

**Once pushed, copy your repo URL for the Devpost submission!**

Repository URL format: `https://github.com/YOUR_USERNAME/support-agent-memory`
