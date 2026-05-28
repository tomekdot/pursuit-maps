#!/usr/bin/env python3
"""
Read Google Sheets data via gviz API (no auth required for public sheets).

Usage:
    python3 read_sheets.py --sheet-id SHEET_ID --gid GID --output maps.json

Requirements: Python 3.7+
"""

import argparse
import json
import sys
import urllib.request


def read_sheet(sheet_id: str, gid: int = 0) -> dict:
    """Read a public Google Sheet via gviz API."""
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?gid={gid}&tqx=out:json&headers=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    raw = resp.read().decode("utf-8")

    # Response format: /*O_o*/\ngoogle.visualization.Query.setResponse({...});
    json_str = raw.split("(", 1)[1].rsplit(");", 1)[0]
    return json.loads(json_str)


def extract_map_uids(sheet_data: dict) -> list:
    """Extract map UIDs and metadata from sheet data.

    Expected columns for "Pursuit Channels New" tab:
        A (#), B (Map name), C (Author), D (Environment),
        E (Uploaded at), F (UID), G (MapType), H (Notes)
    """
    maps = []
    cols = sheet_data["table"]["cols"]
    rows = sheet_data["table"]["rows"]

    for i, row in enumerate(rows):
        cells = row["c"]

        def get_cell(idx):
            if idx < len(cells) and cells[idx]:
                return cells[idx].get("v", "")
            return ""

        def get_formatted(idx):
            if idx < len(cells) and cells[idx]:
                return cells[idx].get("f", cells[idx].get("v", ""))
            return ""

        uid = get_cell(5)  # Column F = UID
        if not uid:
            continue

        maps.append({
            "row": i + 2,
            "number": get_cell(0),
            "name": get_cell(1),
            "author": get_cell(2),
            "environment": get_cell(3),
            "uploaded": get_formatted(4),
            "uid": uid,
            "map_type": get_cell(6),
            "notes": get_cell(7),
        })

    return maps


def main():
    parser = argparse.ArgumentParser(description="Read Google Sheets via gviz API")
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID")
    parser.add_argument("--gid", type=int, default=763170857, help="Sheet GID (tab ID)")
    parser.add_argument("--output", default="sheets_data.json", help="Output JSON file")
    parser.add_argument("--csv-out", default="", help="Optional CSV output")
    args = parser.parse_args()

    print(f"Reading sheet {args.sheet_id}, gid={args.gid}...")
    data = read_sheet(args.sheet_id, args.gid)

    cols = data["table"]["cols"]
    rows = data["table"]["rows"]
    print(f"Columns: {[c['label'] for c in cols[:8]]}")
    print(f"Rows: {len(rows)}")

    maps = extract_map_uids(data)
    print(f"Maps with UID: {len(maps)}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(maps, f, ensure_ascii=False, indent=2)
    print(f"Saved to: {args.output}")

    if args.csv_out:
        import csv
        with open(args.csv_out, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Row", "#", "Map name", "Author", "Environment",
                           "Uploaded at", "UID", "MapType", "Notes"])
            for m in maps:
                writer.writerow([
                    m["row"], m["number"], m["name"], m["author"],
                    m["environment"], m["uploaded"], m["uid"],
                    m["map_type"], m["notes"]
                ])
        print(f"CSV saved to: {args.csv_out}")


if __name__ == "__main__":
    main()
