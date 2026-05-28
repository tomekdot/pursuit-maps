#!/usr/bin/env python3
"""
Pursuit Maps - One-Click Sync & Update Sheets
=============================================
Fetches data from all sources, compares, and updates Google Sheets.

Usage:
    python3 run_sync.py              # full sync + update sheets
    python3 run_sync.py --dry-run    # preview only, no sheet writes
    python3 run_sync.py --auth-only  # just do OAuth setup
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# Fix sys.path
sys.path = [p for p in sys.path if "Python313" not in p and "Python314" not in p]

# ── Config ────────────────────────────────────────────────────────────────────

SHEET_ID = "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ"
SHEET_GID = 763170857
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?gid={SHEET_GID}&tqx=out:json&headers=1"
)
MX_API = "https://tm.mania.exchange/api/maps/get_map_info/id"
FEEDBACK_URL = "https://feedback.prod.live.maniaplanet.com/votes/display/106"
BASE_DIR = Path(__file__).parent.resolve()

# Column mapping: field_name -> (column_letter, source)
FIELD_MAP = {
    "name":     ("B", "Map name"),
    "author":   ("C", "Author login"),
    "env":      ("D", "Environment"),
    "uploaded": ("E", "Uploaded at"),
    "maptype":  ("G", "MapType"),
    "notes":    ("H", "Notes"),
}


def http_get(url, timeout=30, retries=2, delay=1):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-Sync/1.0)"
            })
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8")
        except Exception:
            if attempt < retries:
                time.sleep(delay)
    return None


# ── Fetch Functions ───────────────────────────────────────────────────────────

def fetch_feedback():
    """Fetch maps from ManiaPlanet Feedback page."""
    html = http_get(FEEDBACK_URL)
    if not html:
        print("  ERROR: Cannot fetch feedback page", file=sys.stderr)
        return None

    img_pattern = re.findall(
        r'src=["\']https://files-v4\.live\.maniaplanet\.com/maps/([a-f0-9]+)/([a-zA-Z0-9_\-]+)\.jpg["\']',
        html
    )
    h6_pattern = re.findall(r'<h6[^>]*>(.*?)</h6>', html, re.DOTALL)
    names = []
    for h6 in h6_pattern:
        text = re.sub(r'<[^>]+>', '', h6).strip()
        if text and text not in ('YES/NO', '5 STARS', '', 'YES', 'NO'):
            names.append(text)

    maps = []
    seen = set()
    for i, (hash_val, uid) in enumerate(img_pattern):
        if uid not in seen:
            seen.add(uid)
            maps.append({
                "uid": uid,
                "name": names[i] if i < len(names) else "",
                "hash": hash_val,
            })
    return maps


def fetch_sheet():
    """Fetch current Google Sheets data via gviz."""
    raw = http_get(SHEET_URL)
    if not raw:
        return None
    try:
        json_str = raw.split("(", 1)[1].rsplit(");", 1)[0]
        data = json.loads(json_str)
    except (IndexError, json.JSONDecodeError):
        return None

    rows = data.get("table", {}).get("rows", [])
    maps = []
    for row in rows:
        cells = row.get("c", [])
        def gc(idx):
            if idx < len(cells) and cells[idx]:
                v = cells[idx].get("v", None)
                if v is None:
                    return ""
                if isinstance(v, str) and v.startswith("Date("):
                    m = re.match(r"Date\((\d+),(\d+),(\d+)(?:,(\d+),(\d+),(\d+))?\)", v)
                    if m:
                        y, mo, d = int(m.group(1)), int(m.group(2))+1, int(m.group(3))
                        h = int(m.group(4) or 0); mi = int(m.group(5) or 0); s = int(m.group(6) or 0)
                        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
                if isinstance(v, float) and v == int(v):
                    return str(int(v))
                return str(v).strip()
            return ""
        uid = gc(5)
        if uid:
            maps.append({
                "uid": uid, "_row": gc(0),
                "_name": gc(1), "_author": gc(2), "_env": gc(3),
                "_uploaded": gc(4), "_maptype": gc(6), "_notes": gc(7),
            })
    return maps


def fetch_mx(uid):
    """Fetch MX data for one UID."""
    raw = http_get(f"{MX_API}/{uid}", timeout=15, retries=1, delay=0.5)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "TrackID" in data:
            return data
    except json.JSONDecodeError:
        pass
    return {}


# ── Sync Logic ────────────────────────────────────────────────────────────────

def build_enriched_maps(feedback_maps, sheet_maps):
    """Build enriched map list from all sources."""
    sheet_by_uid = {m["uid"]: m for m in sheet_maps} if sheet_maps else {}

    enriched = []
    for fb in feedback_maps:
        uid = fb["uid"]
        mx = fetch_mx(uid)

        sh = sheet_by_uid.get(uid, {})

        # Best name: feedback > MX > sheet
        name = fb.get("name", "") or clean(mx.get("Name", "")) or sh.get("_name", "")
        # Best author: MX > sheet
        author = clean(mx.get("AuthorLogin", "")) or sh.get("_author", "")
        # Best env: MX > sheet
        env = clean(mx.get("EnvironmentName", "")) or sh.get("_env", "")
        # Best maptype: MX > sheet (normalize TrackMania\PursuitArena -> PursuitArena)
        raw_mt = clean(mx.get("MapType", "")) or sh.get("_maptype", "")
        maptype = raw_mt.split("\\")[-1] if "\\" in raw_mt else raw_mt
        # Best uploaded: sheet > MX
        uploaded = sh.get("_uploaded", "") or clean(mx.get("UploadedAt", ""))
        # Notes: sheet > empty
        notes = sh.get("_notes", "")

        # Track what data we can fill
        fill_from_mx = {}
        if not sh.get("_author") and author:
            fill_from_mx["author"] = author
        if not sh.get("_env") and env:
            fill_from_mx["env"] = env
        if not sh.get("_maptype") and maptype:
            fill_from_mx["maptype"] = maptype
        if not sh.get("_name") and name:
            fill_from_mx["name"] = name
        if not sh.get("_uploaded") and uploaded:
            fill_from_mx["uploaded"] = uploaded

        enriched.append({
            "uid": uid,
            "name": name,
            "author": author,
            "env": env,
            "uploaded": uploaded,
            "maptype": maptype,
            "notes": notes,
            "hash": fb.get("hash", ""),
            "mx_trackid": mx.get("TrackID", ""),
            "fill_from_mx": fill_from_mx,
            "sheet_row": sh.get("_row", ""),
            "in_sheet": uid in sheet_by_uid,
        })

        time.sleep(0.15)

    return enriched


def clean(v):
    if v is None:
        return ""
    return str(v).strip()


def generate_sheet_operations(enriched):
    """Generate list of sheet operations from enriched data."""
    new_rows = []       # Maps not in sheet to be appended
    cell_updates = []   # Empty cells to fill: (row, col_letter, value, description)

    for m in enriched:
        if not m["in_sheet"]:
            new_rows.append(m)
        else:
            row = m["sheet_row"]
            if isinstance(row, str) and row.replace("?", "").strip().isdigit():
                row_num = int(row)
            elif isinstance(row, (int, float)):
                row_num = int(row)
            else:
                continue  # skip rows we can't identify

            # Check each field
            if m["fill_from_mx"].get("name"):
                cell_updates.append((row_num, "B", m["fill_from_mx"]["name"], f"name='{m['fill_from_mx']['name']}'"))
            if m["fill_from_mx"].get("author"):
                cell_updates.append((row_num, "C", m["fill_from_mx"]["author"], f"author='{m['fill_from_mx']['author']}'"))
            if m["fill_from_mx"].get("env"):
                cell_updates.append((row_num, "D", m["fill_from_mx"]["env"], f"env='{m['fill_from_mx']['env']}'"))
            if m["fill_from_mx"].get("uploaded"):
                cell_updates.append((row_num, "E", m["fill_from_mx"]["uploaded"], f"uploaded='{m['fill_from_mx']['uploaded']}'"))
            if m["fill_from_mx"].get("maptype"):
                cell_updates.append((row_num, "G", m["fill_from_mx"]["maptype"], f"maptype='{m['fill_from_mx']['maptype']}'"))

    return new_rows, cell_updates


# ── Sheet Writer ─────────────────────────────────────────────────────────────

def write_to_sheet(new_rows, cell_updates, dry_run=False):
    """Write new rows and cell updates to Google Sheets."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request as GoogleRequest
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Google API libraries not installed.", file=sys.stderr)
        print("Install: pip install google-auth google-auth-oauthlib google-api-python-client", file=sys.stderr)
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    token_path = BASE_DIR / "token.json"
    secrets_path = BASE_DIR / "client_secrets.json"

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        elif secrets_path.exists():
            print("Opening browser for OAuth login...", file=sys.stderr)
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            print(f"Token saved to {token_path}", file=sys.stderr)
        else:
            print("ERROR: No token.json or client_secrets.json found!", file=sys.stderr)
            print("Run: python3 run_sync.py --auth-only", file=sys.stderr)
            sys.exit(1)

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Find sheet title
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheet_title = "Pursuit Channels New"
        for sheet in spreadsheet.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") == SHEET_GID:
                sheet_title = sheet["properties"]["title"]
                break
    except Exception:
        sheet_title = "Pursuit Channels New"

    total_changes = 0

    # 1. Write new rows
    if new_rows:
        # Find last row
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=f"'{sheet_title}'!A:A"
        ).execute()
        last_row = len(result.get("values", []))
        next_num = last_row  # next row number

        values = []
        for i, m in enumerate(new_rows, next_num + 1):
            values.append([
                str(i),
                m["name"],
                m["author"],
                m["env"],
                m["uploaded"],
                m["uid"],
                m["maptype"],
                m["notes"],
            ])

        if not dry_run and values:
            body = {"values": values}
            range_spec = f"'{sheet_title}'!A{next_num+1}:H{next_num+len(values)}"
            result = service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID, range=range_spec,
                valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body=body
            ).execute()
            written = result.get("updates", {}).get("updatedRows", 0)
            print(f"  Written {written} new rows to sheet")
            total_changes += written
        elif dry_run:
            print(f"  [DRY-RUN] Would write {len(values)} new rows (starting at row {next_num+1})")
            for v in values[:5]:
                print(f"    #{v[0]} | {v[1][:50]} | {v[2]} | {v[3]} | {v[5][:30]}")
            if len(values) > 5:
                print(f"    ... and {len(values)-5} more")
            total_changes += len(values)

    # 2. Fill empty cells
    if cell_updates:
        if not dry_run:
            data = []
            for row_num, col, val, desc in cell_updates:
                data.append({
                    "range": f"'{sheet_title}'!{col}{row_num}",
                    "values": [[val]],
                })
            body = {"valueInputOption": "USER_ENTERED", "data": data}
            result = service.spreadsheets().values().batchUpdate(
                spreadsheetId=SHEET_ID, body=body
            ).execute()
            updated = result.get("totalUpdatedCells", 0)
            print(f"  Filled {updated} empty cells")
            total_changes += updated
        else:
            print(f"  [DRY-RUN] Would fill {len(cell_updates)} empty cells:")
            for row_num, col, val, desc in cell_updates[:10]:
                print(f"    {col}{row_num}: {desc}")
            if len(cell_updates) > 10:
                print(f"    ... and {len(cell_updates)-10} more")
            total_changes += len(cell_updates)

    return total_changes


# ── GitHub Actions Workflow ──────────────────────────────────────────────────

def create_github_action():
    """Create the GitHub Actions workflow file."""
    workflow = """name: Pursuit Maps Sync

on:
  schedule:
    # Run daily at 6:00 AM UTC
    - cron: '0 6 * * *'
  workflow_dispatch:  # Allow manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install google-auth google-auth-oauthlib google-api-python-client

      - name: Restore credentials
        env:
          GOOGLE_CLIENT_SECRETS: ${{ secrets.GOOGLE_CLIENT_SECRETS }}
          GOOGLE_SHEETS_TOKEN: ${{ secrets.GOOGLE_SHEETS_TOKEN }}
        run: |
          echo "$GOOGLE_CLIENT_SECRETS" > client_secrets.json
          echo "$GOOGLE_SHEETS_TOKEN" > token.json

      - name: Run sync
        run: python3 scripts/run_sync.py

      - name: Save updated token
        env:
          GOOGLE_SHEETS_TOKEN: ${{ secrets.GOOGLE_SHEETS_TOKEN }}
        run: |
          # Update the token secret if refreshed
          if [ -f token.json ]; then
            TOKEN_CONTENT=$(cat token.json)
            if [ "$TOKEN_CONTENT" != "$GOOGLE_SHEETS_TOKEN" ]; then
              echo "Token was refreshed, updating secret..."
              # Note: requires GH_TOKEN with repo scope to update secrets
              curl -s -X PUT \\
                -H "Authorization: Bearer ${{ secrets.GH_PAT }}" \\
                -H "Accept: application/vnd.github+json" \\
                https://api.github.com/repos/${{ github.repository }}/actions/secrets/GOOGLE_SHEETS_TOKEN \\
                -d "{\"encrypted_value\":\"$(echo $TOKEN_CONTENT | base64 -w 0)\",\"key_id\":\"${{ steps.get-key.outputs.key_id }}\"}"
            fi
          fi

      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: sync-reports
          path: |
            sheet_fill_report.md
            feedback_cache.json
"""
    workflow_path = BASE_DIR / ".github" / "workflows" / "sync.yml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    with open(workflow_path, "w", encoding="utf-8") as f:
        f.write(workflow)
    return workflow_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pursuit Maps One-Click Sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--auth-only", action="store_true", help="Just do OAuth setup")
    parser.add_argument("--setup-action", action="store_true", help="Create GitHub Action workflow")
    args = parser.parse_args()

    print("=" * 60)
    print("Pursuit Maps Sync & Update")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if args.setup_action:
        path = create_github_action()
        print(f"\nCreated GitHub Action: {path}")
        print("Next steps:")
        print("1. Add GOOGLE_CLIENT_SECRETS and GOOGLE_SHEETS_TOKEN as GitHub Secrets")
        print("2. The action will run daily at 6:00 UTC and on manual trigger")
        return

    if args.auth_only:
        print("\n[ AUTH MODE ]")
        print("This will open a browser for Google OAuth login.")
        print("After login, token.json will be saved for future use.")
        input("Press Enter to continue...")
        # Trigger auth by writing empty sheet
        write_to_sheet([], [], dry_run=False)
        return

    # Step 1: Fetch feedback
    print("\n[1/4] Fetching ManiaPlanet Feedback...")
    feedback_maps = fetch_feedback()
    if not feedback_maps:
        print("  ERROR: Could not fetch feedback. Check internet connection.", file=sys.stderr)
        sys.exit(1)
    print(f"  Got {len(feedback_maps)} maps from feedback ✓")

    # Step 2: Fetch sheet
    print("\n[2/4] Fetching Google Sheets...")
    sheet_maps = fetch_sheet()
    if sheet_maps is None:
        print("  WARNING: Could not fetch sheet. Will still process feedback + MX", file=sys.stderr)
        sheet_maps = []
    else:
        print(f"  Got {len(sheet_maps)} maps from sheet ✓")

    # Step 3: Enrich with MX
    print(f"\n[3/4] Enriching {len(feedback_maps)} maps with ManiaExchange...")
    enriched = build_enriched_maps(feedback_maps, sheet_maps)
    mx_count = sum(1 for m in enriched if m.get("mx_trackid"))
    print(f"  Enriched {mx_count} maps with MX data ✓")

    # Step 4: Generate operations
    print("\n[4/4] Comparing and generating sheet operations...")
    new_rows, cell_updates = generate_sheet_operations(enriched)
    print(f"  New rows to add: {len(new_rows)}")
    print(f"  Empty cells to fill: {len(cell_updates)}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Feedback maps:     {len(feedback_maps)}")
    print(f"  Sheet rows:        {len(sheet_maps)}")
    print(f"  MX enriched:       {mx_count}")
    print(f"  New rows to add:   {len(new_rows)}")
    print(f"  Cells to fill:     {len(cell_updates)}")

    if args.dry_run:
        print("\n  [DRY RUN - no changes made]")
        if new_rows:
            print("\n  New rows (first 10):")
            for m in new_rows[:10]:
                print(f"    {m['name'][:50]:50s} | {m['author']:20s} | {m['env']:10s} | {m['maptype']}")
        if cell_updates:
            print("\n  Cell updates (first 10):")
            for row_num, col, val, desc in cell_updates[:10]:
                print(f"    {col}{row_num}: {desc}")
        return

    # Write to sheet
    print("\n[ WRITING TO GOOGLE SHEETS ]")
    try:
        total = write_to_sheet(new_rows, cell_updates, dry_run=False)
        print(f"\n  Total changes written: {total} ✓")
        print(f"\n  View: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={SHEET_GID}")
    except Exception as e:
        print(f"\n  ERROR writing to sheet: {e}", file=sys.stderr)
        print(f"  Try: python3 run_sync.py --auth-only", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
