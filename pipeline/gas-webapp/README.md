# GAS Web App — Deploy Once, Run Forever

This script is deployed **inside** your Google Sheet via Extensions → Apps Script.
It acts as a webhook: the Python pipeline sends HTTP POST requests with JSON data,
and this script writes to the Sheet on your behalf.

## Setup (one-time, ~2 minutes)

1. Open your Sheet:
   https://docs.google.com/spreadsheets/d/1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ/edit#gid=763170857

2. Go to **Extensions → Apps Script**

3. Delete everything in the editor, paste the contents of `PursuitMaps.gs`

4. Save (Ctrl+S), name the project "Pursuit Maps Sync"

5. Click **Deploy → New deployment**
   - Click the gear icon → **Web app**
   - Description: `Pursuit Maps Sync`
   - Execute as: **Me**
   - Who has access: **Anyone**
   - Click **Deploy**
   - If "unverified app" warning appears: Advanced → Go to Pursuit Maps Sync → Allow

6. Copy the **Web app URL** from the deployment dialog

7. Save the URL as one of:
   - Local: `pipeline/gas_url.txt` (in the repo root)
   - GitHub: Secret `GAS_WEBAPP_URL` (Settings → Secrets → Actions)

## Test

```bash
python3 pipeline/pipeline.py --action validate
```

## How It Works

The GAS script exposes two HTTP endpoints via `doPost()`:

- **sync** — receives `{"action": "sync", "maps": [...], "existing": {...}}`
  - Adds new rows (columns A-H)
  - Fills empty cells in existing rows

- **votes** — receives `{"action": "votes", "votes": {"UID": {...}}, "uid_to_row": {}}`
  - Updates columns I-L (YN Rating, YN Votes, 5-Star Avg, 5-Star Total)

- **setup** — receives `{"action": "setup"}`
  - Adds column headers I-L if missing
