#!/usr/bin/env python3
"""
Pursuit Maps - Full Sync with Votes & Stars
===========================================
Fetches from ManiaPlanet Feedback (249 maps with star ratings + vote counts),
Google Sheets, enriches via ManiaExchange API, and writes everything to Google Sheet.

New columns vs original sheet:
  I = YES/NO Rating (e.g. "3.5/5")
  J = YES/NO Votes (e.g. "32")
  K = 5-Star Avg (e.g. "4.2/5")
  L = 5-Star Total (e.g. "565")

Usage:
    python3 run_sync.py              # full sync + update sheets
    python3 run_sync.py --dry-run    # preview only
    python3 run_sync.py --auth-only  # OAuth setup only
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
BASE_DIR = Path(__file__).parent.parent.resolve()

# Column layout in Sheet:
# A=#, B=Map name, C=Author, D=Environment, E=Uploaded at, F=UID, G=MapType, H=Notes
# I=YN Rating, J=YN Votes, K=5-Star Avg, L=5-Star Total  (NEW)


def http_get(url, timeout=30, retries=2, delay=1):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-Sync/2.0)"
            })
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8")
        except Exception:
            if attempt < retries:
                time.sleep(delay)
    return None


def clean(v):
    return "" if v is None else str(v).strip()


# ── Fetch Functions ───────────────────────────────────────────────────────────

def fetch_feedback():
    """Fetch 249 maps from ManiaPlanet Feedback with star ratings + vote counts."""
    html = http_get(FEEDBACK_URL)
    if not html:
        print("  ERROR: Cannot fetch feedback", file=sys.stderr)
        return None

    img_splits = re.split(
        r'(?=<img[^>]*src="[^"]*files-v4\.live\.maniaplanet\.com/maps/)', html
    )
    maps = []
    for section in img_splits[1:]:
        uid_m = re.search(r'/maps/([a-f0-9]+)/([a-zA-Z0-9_\-]+)\.jpg', section)
        if not uid_m:
            continue
        uid = uid_m.group(2)
        hash_val = uid_m.group(1)

        name_m = re.search(r'title="([^"]+)"', section)
        name = name_m.group(1).strip() if name_m else ""

        s = re.sub(r'\s+', ' ', section)

        # YES/NO section: rating + vote count
        yesno_rating = 0.0
        yesno_votes = 0
        yn_m = re.search(
            r'YES.*?NO.*?<span style="color: gold[^"]*">.*?</span>\s*([\d.]+)\s*\((\d+)\)',
            s, re.DOTALL
        )
        if yn_m:
            yesno_rating = float(yn_m.group(1))
            yesno_votes = int(yn_m.group(2))

        # 5 STARS section: avg + total + distribution
        stars_avg = 0.0
        stars_total = 0
        star_pcts = []
        st_m = re.search(
            r'5 STARS.*?<span style="color: gold[^"]*">.*?</span>\s*([\d.]+)\s*\((\d+)\)',
            s, re.DOTALL
        )
        if st_m:
            stars_avg = float(st_m.group(1))
            stars_total = int(st_m.group(2))
            after = s[s.find(st_m.group(0)) + len(st_m.group(0)):]
            bars = re.findall(r'width:\s*(\d+)%', after[:500])
            star_pcts = [int(b) for b in bars[:5]]

        maps.append({
            "uid": uid, "hash": hash_val, "name": name,
            "yesno_rating": yesno_rating, "yesno_votes": yesno_votes,
            "stars_avg": stars_avg, "stars_total": stars_total,
            "star_pcts": star_pcts,
        })
    return maps


def fetch_sheet():
    """Fetch current Sheet data via gviz API."""
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
                    dm = re.match(r"Date\((\d+),(\d+),(\d+)(?:,(\d+),(\d+),(\d+))?\)", v)
                    if dm:
                        y, mo, d = int(dm.group(1)), int(dm.group(2)) + 1, int(dm.group(3))
                        h = int(dm.group(4) or 0)
                        mi = int(dm.group(5) or 0)
                        s = int(dm.group(6) or 0)
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


# ── Enrichment ────────────────────────────────────────────────────────────────

def enrich_maps(feedback_maps, sheet_maps):
    """Enrich feedback maps with MX data and cross-reference with sheet."""
    sheet_by_uid = {m["uid"]: m for m in sheet_maps} if sheet_maps else {}

    enriched = []
    mx_found = 0
    for i, fb in enumerate(feedback_maps):
        uid = fb["uid"]
        mx = fetch_mx(uid)
        sh = sheet_by_uid.get(uid, {})

        author = clean(mx.get("AuthorLogin", "")) or sh.get("_author", "")
        env = clean(mx.get("EnvironmentName", "")) or sh.get("_env", "")
        raw_mt = clean(mx.get("MapType", "")) or sh.get("_maptype", "")
        maptype = raw_mt.split("\\")[-1] if "\\" in raw_mt else raw_mt
        uploaded = sh.get("_uploaded", "") or clean(mx.get("UploadedAt", ""))
        notes = sh.get("_notes", "")

        # Values to fill in sheet empty cells
        fill = {}
        if not sh.get("_name") and fb.get("name"):
            fill["B"] = fb["name"]
        if not sh.get("_author") and author:
            fill["C"] = author
        if not sh.get("_env") and env:
            fill["D"] = env
        if not sh.get("_maptype") and maptype:
            fill["G"] = maptype
        if not sh.get("_name") and fb.get("name"):
            fill["B"] = fb["name"]

        enriched.append({
            "uid": uid, "hash": fb.get("hash", ""),
            "name": fb.get("name", ""),
            "author": author, "env": env, "uploaded": uploaded,
            "maptype": maptype, "notes": notes,
            "yesno_rating": fb.get("yesno_rating", 0),
            "yesno_votes": fb.get("yesno_votes", 0),
            "stars_avg": fb.get("stars_avg", 0),
            "stars_total": fb.get("stars_total", 0),
            "star_pcts": fb.get("star_pcts", []),
            "mx_trackid": mx.get("TrackID", ""),
            "fill": fill,
            "in_sheet": uid in sheet_by_uid,
            "sheet_row": sh.get("_row", ""),
        })

        if mx.get("TrackID"):
            mx_found += 1
        time.sleep(0.15)

        if (i + 1) % 50 == 0:
            print(f"  MX [{i+1}/{len(feedback_maps)}] enriched={mx_found}", file=sys.stderr)

    return enriched


# ── Sheet Writer (Google Sheets API v4) ──────────────────────────────────────

def write_to_sheet(enriched, dry_run):
    """Write new rows + cell updates + votes data to Google Sheets."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request as GRequest
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Google API libs not installed.", file=sys.stderr)
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    token_path = BASE_DIR / "token.json"
    secrets_path = BASE_DIR / "client_secrets.json"

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GRequest())
        elif secrets_path.exists():
            print("Opening browser for OAuth...", file=sys.stderr)
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            print("ERROR: Run --auth-only first!", file=sys.stderr)
            sys.exit(1)

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Find sheet title by GID
    try:
        ss = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheet_title = "Pursuit Channels New"
        for sheet in ss.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") == SHEET_GID:
                sheet_title = sheet["properties"]["title"]
                break
    except Exception:
        sheet_title = "Pursuit Channels New"

    total = 0

    # 1. New rows (maps not yet in sheet)
    new_rows = [m for m in enriched if not m["in_sheet"]]
    if new_rows:
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=f"'{sheet_title}'!A:A"
        ).execute()
        last_row = len(result.get("values", [[]]))

        values = []
        for i, m in enumerate(new_rows, last_row + 1):
            values.append([
                str(i),
                m["name"], m["author"], m["env"], m["uploaded"],
                m["uid"], m["maptype"], m["notes"],
                # New vote columns:
                "{}/5".format(m["yesno_rating"]) if m["yesno_rating"] else "",
                str(m["yesno_votes"]) if m["yesno_votes"] else "",
                "{}/5".format(m["stars_avg"]) if m["stars_avg"] else "",
                str(m["stars_total"]) if m["stars_total"] else "",
            ])

        if not dry_run and values:
            service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range=f"'{sheet_title}'!A{last_row+1}:L{last_row+len(values)}",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values}
            ).execute()
            print(f"  Written {len(values)} new rows")
            total += len(values)
        elif dry_run:
            print(f"  [DRY-RUN] Would write {len(values)} new rows")

    # 2. Update existing rows with votes data + fill empty cells
    updates = []
    for m in enriched:
        if not m["in_sheet"] or not m["sheet_row"]:
            continue
        try:
            row = int(m["sheet_row"])
        except (ValueError, TypeError):
            continue

        # Always update votes columns (they're new)
        if m["yesno_rating"]:
            updates.append((row, "I", "{}/5".format(m["yesno_rating"])))
        if m["yesno_votes"]:
            updates.append((row, "J", str(m["yesno_votes"])))
        if m["stars_avg"]:
            updates.append((row, "K", "{}/5".format(m["stars_avg"])))
        if m["stars_total"]:
            updates.append((row, "L", str(m["stars_total"])))

        # Fill empty original columns
        for col, val in m["fill"].items():
            updates.append((row, col, val))

    if updates:
        if not dry_run:
            data = []
            for row_num, col, val in updates:
                data.append({
                    "range": f"'{sheet_title}'!{col}{row_num}",
                    "values": [[val]],
                })
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={"valueInputOption": "USER_ENTERED", "data": data}
            ).execute()
            print(f"  Updated {len(updates)} cells (votes + fill)")
            total += len(updates)
        else:
            vote_updates = [u for u in updates if u[1] in ("I", "J", "K", "L")]
            fill_updates = [u for u in updates if u[1] not in ("I", "J", "K", "L")]
            print(f"  [DRY-RUN] Would update {len(vote_updates)} vote cells + {len(fill_updates)} fill cells")
            print(f"  Sample vote updates:")
            for r, c, v in vote_updates[:5]:
                print(f"    {c}{r}: {v}")

    return total


# ── GitHub Action ─────────────────────────────────────────────────────────────

def create_github_action():
    """Create/update GitHub Actions workflow."""
    workflow = """name: Pursuit Maps Sync

on:
  schedule:
    - cron: '0 5 * * *'  # 5:00 AM UTC daily
  workflow_dispatch:

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
        run: pip install google-auth google-auth-oauthlib google-api-python-client

      - name: Restore credentials
        env:
          GOOGLE_CLIENT_SECRETS: ${{ secrets.GOOGLE_CLIENT_SECRETS }}
          GOOGLE_SHEETS_TOKEN: ${{ secrets.GOOGLE_SHEETS_TOKEN }}
        run: |
          echo "$GOOGLE_CLIENT_SECRETS" > client_secrets.json
          echo "$GOOGLE_SHEETS_TOKEN" > token.json

      - name: Run sync
        run: python3 scripts/run_sync.py

      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: sync-reports-${{ github.run_number }}
          path: |
            feedback_full.json
"""
    wp = BASE_DIR / ".github" / "workflows" / "sync.yml"
    wp.parent.mkdir(parents=True, exist_ok=True)
    with open(wp, "w") as f:
        f.write(workflow)
    return wp


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pursuit Maps Sync v2 (with votes)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auth-only", action="store_true")
    parser.add_argument("--setup-action", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Pursuit Maps Sync v2.0 - with Votes & Stars")
    print("Time: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)

    if args.setup_action:
        path = create_github_action()
        print("Created: {}".format(path))
        return

    if args.auth_only:
        print("\nPress Enter to start OAuth...")
        input()
        write_to_sheet([], dry_run=False)
        return

    # Step 1: Feedback (249 maps with stars + votes)
    print("\n[1/4] Fetching ManiaPlanet Feedback...")
    feedback = fetch_feedback()
    if not feedback:
        sys.exit(1)
    print("  Got {} maps with vote data".format(len(feedback)))

    # Step 2: Sheet
    print("\n[2/4] Fetching Google Sheets...")
    sheet = fetch_sheet()
    print("  Got {} sheet rows".format(len(sheet) if sheet else 0))

    # Step 3: Enrich with MX
    print("\n[3/4] Enriching with ManiaExchange...")
    enriched = enrich_maps(feedback, sheet)
    mx_n = sum(1 for m in enriched if m["mx_trackid"])
    print("  Enriched {} with MX".format(mx_n))

    # Stats
    new_n = sum(1 for m in enriched if not m["in_sheet"])
    fill_n = sum(1 for m in enriched if m["in_sheet"] and m["fill"])
    vote_n = sum(1 for m in enriched if m["in_sheet"] and m["yesno_rating"])
    print("\n  New maps to add: {}".format(new_n))
    print("  Existing maps with empty cells to fill: {}".format(fill_n))
    print("  Maps with vote data for sheet: {}".format(vote_n))

    # Step 4: Write to Sheet
    if not args.dry_run:
        print("\n[4/4] Writing to Google Sheets...")
        total = write_to_sheet(enriched, dry_run=False)
        print("\n  Total changes: {}".format(total))

        # Save feedback cache
        with open(BASE_DIR / "feedback_full.json", "w") as f:
            json.dump(feedback, f, ensure_ascii=False, indent=2)

        print("\n  Sheet: https://docs.google.com/spreadsheets/d/{}/edit#gid={}".format(SHEET_ID, SHEET_GID))
    else:
        print("\n[4/4] DRY RUN - no writes")
        write_to_sheet(enriched, dry_run=True)

    # Cleanup
    feedback_cache = BASE_DIR / "feedback_full.json"
    if feedback_cache.exists() and not args.dry_run:
        print("  Cache saved: {}".format(feedback_cache))


if __name__ == "__main__":
    main()
