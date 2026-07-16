# Ollama Chat Fix - Deployment Summary

## Problem
The `/chat` endpoint at kleeblatt.space cannot connect to the Ollama LLM model because the production Docker deployment doesn't include the Ollama service.

## Root Cause
1. **Production compose file (`docker-compose.prod.yml`) was missing the Ollama service**
2. The `/api/ai-search/chat` endpoint expects `CUSTOM_MODEL_ENDPOINT` to connect to an Ollama instance
3. Without Ollama in the Docker network, the connection fails

## Changes Made

### 1. Updated `docker-compose.prod.yml`
✅ Added Ollama service definition with:
- GPU acceleration (CUDA support)
- Persistent volume for models
- Startup script for auto-loading models
- Health checks with appropriate start period

### 2. Created `/docker/ollama-startup.sh`
✅ A startup script that:
- Pulls the configured model (qwen2.5:1.5b) if missing
- Validates the model is ready
- Keeps Ollama running in background mode

### 3. Created Feature Branch
✅ All changes are on a feature branch and ready to be committed and pushed.

## Deployment Steps

### Option A: Push to GitHub (Recommended)
```bash
cd /home/debian/kleinanzeigen-ai

# Git status
git status

# Add and commit
git add docker-compose.prod.yml docker/ollama-startup.sh
git commit -m "Add Ollama service to production deployment"

# Push to create feature branch
git push -u origin ollama-fix

# Then create a PR via web interface and merge
```

### Option B: Manual Deploy to Server
Run this sequence on your production server (kleeblatt.space):

```bash
# SSH to server
ssh -i ~/.ssh/id_rsa -L 8000:localhost:8000 dhu.heinrich+kleeblatt.space@kleeblatt.space

# Navigate to project
cd /opt/kleinanzeigen-ai

# Pull latest code
git fetch origin
git reset --hard origin/main

# Add the new files if not already there
cp /home/debian/kleinanzeigen-ai/docker-compose.prod.yml ./docker-compose.prod.yml
mkdir -p docker
cp /home/debian/kleinanzeigen-ai/docker/ollama-startup.sh ./docker/

# Rebuild and restart
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml build ollama api
docker compose -f docker-compose.prod.yml up -d

# Verify
sleep 120  # Wait for Ollama to load model
curl http://localhost:11434/api/tags  # Check Ollama is running
curl http://localhost:8000/api/ai-search/chat  # Test API
```

## Expected Result After Deployment

When you visit https://kleeblatt.space/chat:
- ✅ The chat interface loads successfully
- ✅ The `/api/ai-search/chat` endpoint returns `llm_connected: true`
- ✅ Model name shows: `qwen2.5:1.5b`
- ✅ No "LLM model not active" error
- ✅ You can send messages and get AI responses

## Verification Checklist
- [ ] Pull feature branch to main (or merge PR)
- [ ] Docker builds successfully with no errors
- [ ] Ollama service starts and passes health check
- [ ] qwen2.5:1.5b model is loaded
- [ ] API endpoint returns `llm_connected: true`
- [ ] Chat page no longer shows connection error

## Next Steps
1. **Commit and push** the changes to your GitHub repository
2. **Create a Pull Request** (as per your workflow preference)
3. **Wait for CI to pass** (lint, tests, smoke tests)
4. **Merge to main** - this will trigger auto-deploy
5. **Visit kleeblatt.space/chat** to verify the fix

Would you like me to continue with committing and pushing these changes to your repository?
