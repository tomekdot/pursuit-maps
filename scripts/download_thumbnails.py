#!/usr/bin/env python3
"""
Extract map UIDs from ManiaPlanet Feedback page and download thumbnails.

Usage:
    python3 extract_maps.py --output-dir ./thumbnails --csv-out maps.csv

Requirements: Python 3.7+
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

FEEDBACK_URL = "https://feedback.prod.live.maniaplanet.com/votes/display/106"
THUMB_BASE = "https://files-v4.live.maniaplanet.com/maps"
MX_SEARCH = "https://tm.mania.exchange/mapsearch?query="
MX_USER = "https://tm.mania.exchange/usersearch?query="
FEEDBACK_EPISODE = "https://feedback.prod.live.maniaplanet.com/votes/display/106"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/*,*/*;q=0.8",
}


def download_thumbnail(hash_val: str, uid: str, output_dir: str) -> bool:
    """Download a single thumbnail by hash and UID."""
    url = f"{THUMB_BASE}/{hash_val}/{uid}.jpg"
    out_path = os.path.join(output_dir, f"{uid}.jpg")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return True  # Already downloaded

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if len(data) < 100:
                return False
            with open(out_path, "wb") as f:
                f.write(data)
        return True
    except Exception as e:
        print(f"  FAIL: {uid[:30]}... - {e}", file=sys.stderr)
        return False


def generate_map_url(map_name: str) -> str:
    """Generate tm.mania.exchange search URL for a map."""
    import urllib.parse
    return f"{MX_SEARCH}{urllib.parse.quote(map_name)}"


def generate_author_url(author: str) -> str:
    """Generate tm.mania.exchange user search URL."""
    import urllib.parse
    return f"{MX_USER}{urllib.parse.quote(author)}"


def write_csv(maps: list, csv_path: str):
    """Write map data to CSV."""
    import csv

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Lp", "UID", "Map name", "Hash",
            "Thumbnail URL", "Map URL", "Author URL", "Feedback URL"
        ])
        for i, m in enumerate(maps, 1):
            writer.writerow([
                i, m["uid"], m["name"], m["hash"],
                f"{THUMB_BASE}/{m['hash']}/{m['uid']}.jpg",
                generate_map_url(m["name"]),
                generate_author_url(m.get("author", "")),
                FEEDBACK_EPISODE,
            ])


def main():
    parser = argparse.ArgumentParser(description="Download map thumbnails from ManiaPlanet Feedback")
    parser.add_argument("--output-dir", default="thumbnails", help="Output directory for JPG files")
    parser.add_argument("--csv-out", default="maps.csv", help="Output CSV file path")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between downloads (seconds)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of downloads (0=all)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # NOTE: Map list must be extracted from the feedback page first using browser JS
    # See README.md for JavaScript extraction code. Save result as maps.json:
    # [{"hash": "abc123", "uid": "xyz789", "name": "Map Name"}, ...]

    json_path = os.path.join(os.path.dirname(args.csv_out), "maps.json")
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.", file=sys.stderr)
        print("First extract map data from feedback page using browser JS.", file=sys.stderr)
        print("See README.md for JavaScript extraction code.", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        maps = json.load(f)

    print(f"Loaded {len(maps)} maps from {json_path}")

    if args.limit > 0:
        maps = maps[:args.limit]

    # Download thumbnails
    ok = 0
    fail = 0
    for i, m in enumerate(maps, 1):
        uid = m["uid"]
        hash_val = m.get("hash", "")

        if not hash_val:
            print(f"  [{i}/{len(maps)}] SKIP: {uid[:30]}... (no hash)")
            fail += 1
            continue

        out_path = os.path.join(args.output_dir, f"{uid}.jpg")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            ok += 1
            continue

        if download_thumbnail(hash_val, uid, args.output_dir):
            ok += 1
            print(f"  [{i}/{len(maps)}] OK: {uid[:40]}...")
        else:
            fail += 1

        if args.delay > 0:
            time.sleep(args.delay)

    # Write CSV
    write_csv(maps, args.csv_out)

    print(f"\nDone: {ok} downloaded, {fail} failed, total: {len(maps)}")
    print(f"CSV: {args.csv_out}")
    print(f"Thumbnails: {args.output_dir}/")


if __name__ == "__main__":
    main()
