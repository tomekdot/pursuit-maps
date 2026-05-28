# Google Sheets Write Access - Setup Guide

## Option A: User OAuth (works locally + GitHub Actions with token)

### Step 1: Create OAuth Client ID
1. Go to https://console.cloud.google.com/
2. Select or create project → "APIs & Services" → "Credentials"
3. Click "Create Credentials" → "OAuth Client ID"
4. If prompted:
   - App type: External
   - Name: `Pursuit Maps Sync`
   - Add your email as test user
5. Application type: "Desktop app"
6. Name: `pursuit-maps`
7. Click "Create"
8. Download JSON → save as `client_secrets.json`

### Step 2: First Auth
```bash
python3 scripts/run_sync.py --auth-only
```
Browser opens → login → `token.json` saved.

### Step 3: GitHub Secrets
Add these secrets to repo:
- `GOOGLE_CLIENT_SECRETS` = contents of client_secrets.json
- `GOOGLE_SHEETS_TOKEN` = contents of token.json

---

## Option B: Service Account (recommended, auto-works in GitHub Actions)

### Step 1: Create Service Account
1. https://console.cloud.google.com/ → IAM & Admin → Service Accounts
2. "Create Service Account"
3. Name: `pursuit-maps-sync`
4. Grant role: Editor
5. Create Key → JSON → download
6. Save as `service_account.json`

### Step 2: Share the Sheet
1. Open the Sheet
2. Click "Share"
3. Add the service account email (found in the JSON, like `...@...iam.gserviceaccount.com`)
4. Grant Editor access

### Step 3: GitHub Secrets
Add secret:
- `GOOGLE_SERVICE_ACCOUNT` = contents of service_account.json

Then run_sync.py will auto-detect it.
