#!/usr/bin/env python3
"""
Pursuit Maps - GAS Web App Runner
==================================
Sends data to Google Apps Script Web App (deployed in Sheet).
Works locally and with GitHub Actions - no credentials needed!

Usage:
    python3 gas_runner.py                 # send data to GAS
    python3 gas_runner.py --action votes  # send votes only
    python3 gas_runner.py --test          # test connection
    python3 gas_runner.py --setup         # add column headers

Config:
    Set GAS Web App URL in gas_url.txt file or GAS_WEBAPP_URL env var
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import re
from pathlib import Path

sys.path = [p for p in sys.path if "Python313" not in p and "Python314" not in p]

BASE_DIR = Path(__file__).parent.resolve()
GAS_URL_FILE = BASE_DIR / "gas_url.txt"

# ── GAS URL ──────────────────────────────────────────────────────────────────

def get_gas_url():
    """Get GAS Web App URL from file or environment variable."""
    url = os.environ.get("GAS_WEBAPP_URL", "")
    if url:
        return url.strip()
    if GAS_URL_FILE.exists():
        return GAS_URL_FILE.read_text().strip()
    print("ERROR: GAS Web App URL not found!", file=sys.stderr)
    print("Set GAS_WEBAPP_URL env var or create gas_url.txt with the URL.", file=sys.stderr)
    print("Deploy GAS script first (see gas-webapp/README.md).", file=sys.stderr)
    sys.exit(1)

# ── HTTP Helpers ─────────────────────────────────────────────────────────────

def http_post(url, data, retries=3):
    """POST JSON data to GAS Web App."""
    body = json.dumps(data).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            print("  HTTP {}: {}".format(e.code, body_text[:200]), file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2)
        except Exception as e:
            print("  Error: {}".format(e), file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2)
    return None

def http_get(url, params=None, retries=3):
    """GET request to GAS Web App."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PursuitMaps/1.0"})
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return None

# ── Data Loaders ─────────────────────────────────────────────────────────────

def load_feedback():
    """Load feedback data (from cache or fetch fresh)."""
    cache = BASE_DIR / "feedback_full.json"
    if cache.exists():
        with open(cache, "r") as f:
            return json.load(f)
    print("No feedback cache. Run vote_tracker.py first.", file=sys.stderr)
    return None

def load_enriched():
    """Load enriched data from run_sync output."""
    cache = BASE_DIR / "enriched_maps.json"
    if cache.exists():
        with open(cache, "r") as f:
            return json.load(f)
    return None

# ── Sheet Data (via gviz) ────────────────────────────────────────────────────

def fetch_sheet_data():
    """Fetch current sheet data for comparison."""
    sheet_url = (
        "https://docs.google.com/spreadsheets/d/"
        "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ/"
        "gviz/tq?gid=763170857&tqx=out:json&headers=1"
    )
    try:
        req = urllib.request.Request(sheet_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        raw = resp.read().decode("utf-8")
        json_str = raw.split("(", 1)[1].rsplit(");", 1)[0]
        data = json.loads(json_str)
    except Exception:
        return {}

    rows = data.get("table", {}).get("rows", [])
    sheet_by_uid = {}
    for i, row in enumerate(rows):
        cells = row.get("c", [])
        def gc(idx):
            if idx < len(cells) and cells[idx]:
                v = cells[idx].get("v", None)
                if v is None:
                    return ""
                return str(v).strip()
            return ""
        uid = gc(5)
        if uid:
            sheet_by_uid[uid] = {
                "row": gc(0) or str(i + 2),
                "name": gc(1),
                "author": gc(2),
                "env": gc(3),
                "uploaded": gc(4),
                "maptype": gc(6),
                "notes": gc(7),
            }
    return sheet_by_uid

# ── Sync Logic ───────────────────────────────────────────────────────────────

def prepare_sync_payload(feedback_maps, sheet_data):
    """Prepare payload for GAS sync action."""
    new_maps = []
    existing = {}

    for fb in feedback_maps:
        uid = fb["uid"]
        if uid in sheet_data:
            # Existing row - check for empty cells to fill
            sh = sheet_data[uid]
            fill = {}
            if not sh.get("name") and fb.get("name"):
                fill["B"] = fb["name"]
            if not sh.get("author") and fb.get("author"):
                fill["C"] = fb["author"]
            if not sh.get("env") and fb.get("env"):
                fill["D"] = fb["env"]
            if not sh.get("maptype") and fb.get("maptype"):
                fill["G"] = fb["maptype"]
            if not sh.get("uploaded") and fb.get("uploaded"):
                fill["E"] = fb["uploaded"]
            if fill:
                existing[uid] = {
                    "row": int(sh["row"]) if sh.get("row", "").isdigit() else 0,
                    "fill": fill,
                }
        else:
            # New map
            new_maps.append({
                "uid": uid,
                "name": fb.get("name", ""),
                "author": fb.get("author", ""),
                "env": fb.get("env", ""),
                "uploaded": fb.get("uploaded", ""),
                "maptype": fb.get("maptype", ""),
                "notes": fb.get("notes", ""),
            })

    return {
        "action": "sync",
        "maps": new_maps,
        "existing": existing,
    }

def prepare_votes_payload(feedback_maps, sheet_data):
    """Prepare payload for GAS votes action."""
    votes = {}
    uid_to_row = {}

    for fb in feedback_maps:
        uid = fb["uid"]
        votes[uid] = {
            "yn_rating": "{}/5".format(fb["yesno_rating"]) if fb.get("yesno_rating") else "",
            "yn_votes": str(fb.get("yesno_votes", "")),
            "stars_avg": "{}/5".format(fb["stars_avg"]) if fb.get("stars_avg") else "",
            "stars_total": str(fb.get("stars_total", "")),
        }
        if uid in sheet_data:
            row = sheet_data[uid].get("row", "0")
            if row.isdigit():
                uid_to_row[uid] = int(row)

    return {
        "action": "votes",
        "votes": votes,
        "uid_to_row": uid_to_row,
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pursuit Maps GAS Runner")
    parser.add_argument("--test", action="store_true", help="Test GAS connection")
    parser.add_argument("--setup", action="store_true", help="Add column headers via GAS")
    parser.add_argument("--action", choices=["sync", "votes", "full", "sort"], default="full")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    gas_url = get_gas_url()

    # Test connection
    if args.test:
        print("Testing GAS connection...")
        result = http_get(gas_url, {"action": "ping"})
        if result:
            print("OK: {}".format(json.dumps(result)))
        else:
            print("FAILED")
        return

    # Setup headers
    if args.setup:
        print("Adding column headers...")
        result = http_get(gas_url, {"action": "setup"})
        print(json.dumps(result, indent=2) if result else "FAILED")
        return

    # Load data
    feedback = load_feedback()
    if not feedback:
        sys.exit(1)

    sheet_data = fetch_sheet_data()
    print("Feedback: {} maps, Sheet: {} rows".format(len(feedback), len(sheet_data)))

    # Dry run
    if args.dry_run:
        if args.action in ("sync", "full"):
            payload = prepare_sync_payload(feedback, sheet_data)
            new_n = len(payload["maps"])
            fill_n = len(payload["existing"])
            print("[DRY-RUN] Sync: {} new rows, {} cells to fill".format(new_n, fill_n))
            for uid, info in list(payload["existing"].items())[:5]:
                print("  Row {}: {}".format(info["row"], info["fill"]))

        if args.action in ("votes", "full"):
            vp = prepare_votes_payload(feedback, sheet_data)
            matched = len(vp["uid_to_row"])
            print("[DRY-RUN] Votes: {} maps with sheet row mapping".format(matched))
        return

    # Execute
    results = {}

    if args.action in ("sync", "full"):
        payload = prepare_sync_payload(feedback, sheet_data)
        new_n = len(payload["maps"])
        fill_n = len(payload["existing"])
        print("Sync: {} new rows, {} cells to fill".format(new_n, fill_n))

        if new_n > 0 or fill_n > 0:
            result = http_post(gas_url, payload)
            results["sync"] = result
            if result:
                print("Result: {}".format(json.dumps(result)))
            else:
                print("FAILED")
        else:
            print("Nothing to sync.")

    if args.action in ("votes", "full"):
        vp = prepare_votes_payload(feedback, sheet_data)
        matched = len(vp["uid_to_row"])
        print("Votes: updating {} rows".format(matched))

        if matched > 0:
            result = http_post(gas_url, vp)
            results["votes"] = result
            if result:
                print("Result: {}".format(json.dumps(result)))
            else:
                print("FAILED")
        else:
            print("No matching rows to update.")

    # Sort action
    if args.action == "sort":
        print("Sort: sorting sheet by Uploaded At...")
        result = http_post(gas_url, {"action": "sort"})
        results["sort"] = result
        if result:
            print("Result: {}".format(json.dumps(result)))
        else:
            print("FAILED")

    # Save results
    with open(BASE_DIR / "gas_last_result.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
