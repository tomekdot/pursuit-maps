#!/usr/bin/env python3
"""
Pursuit Maps - ManiaExchange Data Enricher
===========================================
Zapisywanie informacji z API ManiaExchange (endpoint V1)
dla każdej mapy z UID w pliku CSV.

Endpoint: https://tm.mania.exchange/api/maps/get_map_info/id/{UID}

Nowe kolumny dodawane do CSV:
  - MX TrackID          : TrackID / MapID z MX
  - MX Name             : Nazwa mapy na MX (Name)
  - MX GbxMapName       : Oryginalna nazwa z pliku Gbx
  - MX AuthorLogin      : Login autora z Gbx
  - MX MapType          : Typ mapy (PursuitArena, GoalHuntArena, itp.)
  - MX TitlePack        : TitlePack (Pursuit, Trackmania, itp.)
  - MX EnvironmentName  : Środowisko po stronie MX
  - MX VehicleName      : Pojazd wymagany przez mapę
  - MX DifficultyName   : Poziom trudności
  - MX LengthName       : Długość/w czasie
  - MX UploadedAt       : Data uploadu na MX
  - MX UpdatedAt        : Data ostatniej aktualizacji
  - MX Downloadable     : Czy można pobrać
  - MX Comments         : Komentarze mapy
  - MX AwardCount       : Liczba nagród
  - MX HasThumbnail     : Czy ma wlasny thumbnail
  - MX HasScreenshot    : Czy ma screenshot

Użycie:
    python3 enrich_with_mx.py
    python3 enrich_with_mx.py --csv path/to/input.csv --output path/to/output.csv
    python3 enrich_with_mx.py --dry-run        # nie zapisuje, tylko podsumowanie
    python3 enrich_with_mx.py --delay 0.5       # opoóźnienie między requestami (sekundy)
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime


# ── Config ────────────────────────────────────────────────────────────────────

MX_API_BASE = "https://tm.mania.exchange/api/maps/get_map_info/id"

# New columns to add (in order)
MX_FIELDS = [
    ("MX TrackID",        "TrackID"),
    ("MX Name",           "Name"),
    ("MX GbxMapName",     "GbxMapName"),
    ("MX AuthorLogin",    "AuthorLogin"),
    ("MX MapType",        "MapType"),
    ("MX TitlePack",      "TitlePack"),
    ("MX EnvironmentName","EnvironmentName"),
    ("MX VehicleName",    "VehicleName"),
    ("MX DifficultyName", "DifficultyName"),
    ("MX LengthName",     "LengthName"),
    ("MX UploadedAt",     "UploadedAt"),
    ("MX UpdatedAt",      "UpdatedAt"),
    ("MX Downloadable",   "Downloadable"),
    ("MX Comments",       "Comments"),
    ("MX AwardCount",     "AwardCount"),
    ("MX HasThumbnail",   "HasThumbnail"),
    ("MX HasScreenshot",  "HasScreenshot"),
]

# Default input file
DEFAULT_CSV = r"C:\Users\tomekdot\maniaplanet_feedback_106_with_uid.csv"


def query_mx(uid: str, retries: int = 3, delay: float = 0.2) -> dict:
    """Query ManiaExchange API for a map by UID. Returns parsed JSON or empty dict."""
    url = f"{MX_API_BASE}/{uid}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-Enricher/1.0)"
            })
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            # API returns {} for unknown UIDs
            if isinstance(data, dict) and "TrackID" in data:
                return data
            return {}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}  # Map not found on MX
            if attempt < retries - 1:
                time.sleep(delay * 2)
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay * 2)
    return {}


def safe_get(data: dict, key: str) -> str:
    """Safely extract a value from API response."""
    val = data.get(key)
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def main():
    parser = argparse.ArgumentParser(
        description="Enrich Pursuit Maps CSV with ManiaExchange API data"
    )
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Input CSV file path")
    parser.add_argument("-o", "--output", default="", help="Output CSV file path")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no file write")
    parser.add_argument("--delay", type=float, default=0.15,
                       help="Seconds between API requests (default: 0.15)")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating .bak backup")
    args = parser.parse_args()

    input_csv = args.csv
    if not os.path.exists(input_csv):
        print(f"ERROR: File not found: {input_csv}", file=sys.stderr)
        sys.exit(1)

    # Default output: same as input (in-place update)
    output_csv = args.output or input_csv

    # Read input CSV
    print(f"Reading: {input_csv}", file=sys.stderr)
    with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    print(f"Rows: {len(rows)}, Columns: {fieldnames}", file=sys.stderr)

    # Determine which MX columns are already present
    existing_cols = set(fieldnames)
    new_col_names = [name for name, _ in MX_FIELDS if name not in existing_cols]
    added_col_names = [name for name, _ in MX_FIELDS]

    if not new_col_names:
        print("All MX columns already present in CSV.", file=sys.stderr)
        print("Re-enriching existing data...", file=sys.stderr)

    print(f"MX columns to check: {len(added_col_names)}", file=sys.stderr)
    print(f"\nQuerying ManiaExchange API (delay={args.delay}s)...", file=sys.stderr)

    # Query MX for each row with UID
    enriched = 0
    empty = 0
    errors = 0

    for i, row in enumerate(rows):
        uid = row.get("UID", "").strip()
        if not uid:
            empty += 1
            continue

        mx_data = query_mx(uid)

        for col_name, api_key in MX_FIELDS:
            row[col_name] = safe_get(mx_data, api_key)

        if mx_data.get("TrackID"):
            enriched += 1
        else:
            empty += 1

        # Progress indicator
        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(rows)}] enriched: {enriched}, not found: {empty}",
                  file=sys.stderr)

        time.sleep(args.delay)

    print(f"\nDone! Enriched: {enriched}, Not on MX: {empty}, No UID: 0",
          file=sys.stderr)

    # Build output fieldnames (preserve order, add new MX cols at end)
    output_fieldnames = list(fieldnames)
    for col_name, _ in MX_FIELDS:
        if col_name not in output_fieldnames:
            output_fieldnames.append(col_name)

    # Only keep columns that are in our list (remove any duplicates seen)
    if not new_col_names:
        output_fieldnames = list(dict.fromkeys(output_fieldnames))

    # Print preview
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Preview (first 5 rows):", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    for row in rows[:5]:
        uid = row.get("UID", "")
        mx_name = row.get("MX Name", "")
        mx_env = row.get("MX EnvironmentName", "")
        mx_veh = row.get("MX VehicleName", "")
        mx_type = row.get("MX MapType", "")
        print(f"  {row.get('Map name',''):40s} | MX: {mx_name:30s} | "
              f"Env: {mx_env:10s} | Veh: {mx_veh:15s} | Type: {mx_type}", file=sys.stderr)

    if args.dry_run:
        print("\nDRY RUN - no file written.", file=sys.stderr)
        return

    # Backup existing file if overwriting
    if output_csv == input_csv and not args.no_backup:
        bak = input_csv + ".bak"
        try:
            os.replace(input_csv, bak)
            print(f"Backup: {bak}", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Could not create backup: {e}", file=sys.stderr)

    # Write output CSV
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nOutput: {output_csv}", file=sys.stderr)
    print(f"Columns ({len(output_fieldnames)}): {output_fieldnames}", file=sys.stderr)

    # Stats
    env_map: dict[str, int] = {}
    veh_map: dict[str, int] = {}
    type_map: dict[str, int] = {}
    for row in rows:
        env = row.get("MX EnvironmentName", "") or "(not on MX)"
        veh = row.get("MX VehicleName", "") or "(n/a)"
        mtype = row.get("MX MapType", "") or "(n/a)"
        env_map[env] = env_map.get(env, 0) + 1
        veh_map[veh] = veh_map.get(veh, 0) + 1
        type_map[mtype] = type_map.get(mtype, 0) + 1

    print(f"\n{'='*60}", file=sys.stderr)
    print("MX Environment distribution:", file=sys.stderr)
    for env in sorted(env_map.keys()):
        print(f"  {env:20s}: {env_map[env]}", file=sys.stderr)

    print("\nMX Vehicle distribution:", file=sys.stderr)
    for veh in sorted(veh_map.keys()):
        print(f"  {veh:20s}: {veh_map[veh]}", file=sys.stderr)

    print("\nMX MapType distribution:", file=sys.stderr)
    for mt in sorted(type_map.keys()):
        print(f"  {mt:25s}: {type_map[mt]}", file=sys.stderr)


if __name__ == "__main__":
    main()
