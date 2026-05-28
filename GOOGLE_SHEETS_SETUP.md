# Google Sheets OAuth Setup Instructions

## Step 1: Create Google Cloud Project
1. Go to https://console.cloud.google.com/
2. Click "Select a project" → "New Project"
3. Name it: `pursuit-maps-sync`
4. Click "Create"

## Step 2: Enable Google Sheets API
1. In your new project, go to "APIs & Services" → "Library"
2. Search for "Google Sheets API"
3. Click "Enable"

## Step 3: Create OAuth Client ID
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth Client ID"
3. If prompted to configure OAuth consent screen:
   - Choose "External"
   - Fill in: App name = `Pursuit Maps Sync`, email = your email
   - Add scope: `https://www.googleapis.com/auth/spreadsheets`
   - Add your email as a test user
   - Save and continue
4. Application type: "Desktop app"
5. Name: `pursuit-maps-desktop`
6. Click "Create"
7. Download the JSON file
8. Save it as `client_secrets.json` in this directory

## Step 4: First-time Auth Run
Run this command once to authenticate:
```bash
python3 scripts/sheets_writer.py --auth
```
This will open a browser, you'll log in, and a `token.json` will be saved.

After that, token.json is reused automatically (it refreshes itself).

## Where to put the files
```
pursuit-maps/
├── client_secrets.json    <-- downloaded from Google Cloud
├── token.json             <-- auto-generated after first auth run
└── scripts/
    └── sheets_writer.py
```

## For GitHub Actions (automated runs)
The `token.json` will be saved as a GitHub Secret.
After first auth, run:
```bash
cat token.json  # copy the content
```
Then add it as GitHub Secret named `GOOGLE_SHEETS_TOKEN`.

Also add `client_secrets.json` content as `GOOGLE_CLIENT_SECRETS` secret.
The GitHub Action will recreate both files from secrets at runtime.
