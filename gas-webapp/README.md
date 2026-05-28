# GAS Web App Setup (one-time)

## Step 1: Deploy Google Apps Script
1. Open Sheet: https://docs.google.com/spreadsheets/d/1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ/edit#gid=763170857
2. Extensions → Apps Script
3. Delete everything from editor and paste the contents of `PursuitMaps.gs`
4. Save (Ctrl+S) - name the project "Pursuit Maps Sync"
5. Click **Deploy** → **New deployment**
6. Gear icon (settings) → **Web app**
7. Settings:
   - Description: `Pursuit Maps Sync`
   - Execute as: **Me** (your account)
   - Who has access: **Anyone**
8. Click **Deploy**
9. Authorize permissions
10. Copy the **Web app URL** (looks like `https://script.google.com/macros/s/AX.../exec`)
11. Paste URL into `gas_url.txt` file in this folder

## Step 2: Test
```bash
cd gas-webapp
python3 gas_runner.py --test      # test connection
python3 gas_runner.py --setup     # add column headers I-L
python3 gas_runner.py --dry-run   # preview only
python3 gas_runner.py             # full sync
```

## Step 3: GitHub Actions
1. Go to repo → Settings → Secrets → Actions
2. Add secret: `GAS_WEBAPP_URL` = URL from step 1
3. GitHub Actions will run automatically at 5:00 UTC

## Manual Usage
```bash
# Sync only (add new maps, fill empty cells)
python3 gas_runner.py --action sync

# Votes only (update columns I-L)
python3 gas_runner.py --action votes

# Everything
python3 gas_runner.py

# Preview without saving
python3 gas_runner.py --dry-run
```
