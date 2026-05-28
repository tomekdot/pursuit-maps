#!/usr/bin/env python3
"""
Pursuit Maps Data Generator
============================
Generates a markdown table with TrackMania Pursuit maps
from Google Sheets data (gviz API).

Usage:
    python3 pursuit_maps_generator.py                          # default sheet
    python3 pursuit_maps_generator.py --sheet-id ID --gid GID   # custom sheet
    python3 pursuit_maps_generator.py --json-only               # JSON output only
    python3 pursuit_maps_generator.py --with-thumbnails DIR     # include thumbnails
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_SHEET_ID = "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ"
DEFAULT_GID = 763170857

# Google gviz date format: Date(2017,9,6,20,57,42)
# Note: months are 0-indexed in Google's format
GOOGLE_DATE_RE = re.compile(
    r"Date\((\d{4}),(\d{1,2}),(\d{1,2})(?:,(\d{1,2}),(\d{1,2}),(\d{1,2}))?\)"
)

# Column mapping from Sheets tab "Pursuit Channels New"
COLUMNS = {
    0: ("#", "number"),
    1: ("Map name", "string"),
    2: ("Author login", "string"),
    3: ("Environment", "string"),
    4: ("Uploaded at", "datetime"),
    5: ("UID", "string"),
    6: ("MapType", "string"),
    7: ("Notes", "string"),
}


def parse_google_date(val):
    """Parse Google Sheets Date(...) format to 'yyyy-mm-dd hh:mm:ss'."""
    if not val or not isinstance(val, str):
        return ""
    m = GOOGLE_DATE_RE.match(val.strip())
    if not m:
        return str(val)
    year = int(m.group(1))
    month = int(m.group(2)) + 1  # Google uses 0-indexed months
    day = int(m.group(3))
    hour = int(m.group(4)) if m.group(4) else 0
    minute = int(m.group(5)) if m.group(5) else 0
    second = int(m.group(6)) if m.group(6) else 0
    try:
        dt = datetime(year, month, day, hour, minute, second)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(val)


def get_cell_value(cell, col_type="string"):
    """Extract value from a Google Sheets cell dict."""
    if cell is None:
        return ""
    val = cell.get("v", None)
    if val is None:
        return ""
    if col_type == "datetime" and isinstance(val, str):
        return parse_google_date(val)
    if col_type == "number":
        # Google returns numbers as floats
        if isinstance(val, float) and val == int(val):
            return str(int(val))
        return str(val)
    if col_type == "string":
        # Use formatted value if available
        return cell.get("f", str(val))
    return str(val)


def read_sheet(sheet_id: str, gid: int) -> dict:
    """Read a public Google Sheet via gviz API (no auth needed)."""
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?gid={gid}&tqx=out:json&headers=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        raw = resp.read().decode("utf-8")
    except Exception as e:
        print(f"ERROR: Failed to fetch sheet: {e}", file=sys.stderr)
        sys.exit(1)

    # Strip the gviz wrapper: /*O_o*/\ngoogle.visualization.Query.setResponse({...});
    try:
        json_str = raw.split("(", 1)[1].rsplit(");", 1)[0]
        return json.loads(json_str)
    except (IndexError, json.JSONDecodeError) as e:
        print(f"ERROR: Failed to parse response: {e}", file=sys.stderr)
        print(f"Raw response (first 500 chars): {raw[:500]}", file=sys.stderr)
        sys.exit(1)


def extract_maps(sheet_data: dict) -> list[dict]:
    """Extract map records from parsed sheet data."""
    rows = sheet_data["table"]["rows"]
    col_types = {i: ct for i, (label, ct) in COLUMNS.items()}

    maps = []
    for row_data in rows:
        cells = row_data["c"]

        def cell(idx):
            return get_cell_value(
                cells[idx] if idx < len(cells) else None,
                col_types.get(idx, "string"),
            )

        # Skip rows without UID (column 5)
        uid = cell(5)
        if not uid:
            continue

        maps.append(
            {
                "#": cell(0),
                "Map name": cell(1),
                "Author login": cell(2),
                "Environment": cell(3),
                "Uploaded at": cell(4),
                "UID": uid,
                "MapType": cell(6),
                "Notes": cell(7),
            }
        )

    return maps


def load_thumbnails_dir(dir_path: str) -> set[str]:
    """Return set of UIDs that have thumbnails in the given directory."""
    if not dir_path or not os.path.isdir(dir_path):
        return set()
    uids = set()
    for f in os.listdir(dir_path):
        name = os.path.splitext(f)[0]
        if name:
            uids.add(name)
    return uids


def format_map_type(mt: str) -> str:
    """Shorten MapType for display."""
    if not mt:
        return ""
    # "TrackMania\PursuitArena" -> "PursuitArena"
    return mt.split("\\")[-1] if "\\" in mt else mt


def generate_markdown(
    maps: list[dict],
    thumbnails_dir: str = "",
    sheet_url: str = "",
) -> str:
    """Generate a complete markdown document from map data."""
    lines = []

    # Header
    lines.append("# Pursuit Maps - ManiaPlanet Feedback")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  "
        f"| Total maps: {len(maps)}"
    )
    if sheet_url:
        lines.append(f"Source: [Google Sheets]({sheet_url})")
    lines.append("")

    # Environment summary
    env_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for m in maps:
        env = m["Environment"] or "Unknown"
        env_counts[env] = env_counts.get(env, 0) + 1
        mt = format_map_type(m.get("MapType", ""))
        type_counts[mt] = type_counts.get(mt, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Environment | Count |")
    lines.append("|------------|-------|")
    for env in sorted(env_counts.keys()):
        lines.append(f"| {env} | {env_counts[env]} |")
    lines.append("")
    lines.append("| MapType | Count |")
    lines.append("|---------|-------|")
    for mt in sorted(type_counts.keys()):
        lines.append(f"| {mt} | {type_counts[mt]} |")
    lines.append("")

    # Thumbnail availability
    if thumbnails_dir:
        available = load_thumbnails_dir(thumbnails_dir)
        with_thumb = sum(1 for m in maps if m["UID"] in available)
        lines.append(
            f"Thumbnails: {with_thumb}/{len(maps)} available "
            f"(`{thumbnails_dir}`)"
        )
        lines.append("")

    # Main table
    lines.append("## Maps")
    lines.append("")
    header = ["#", "Map name", "Author login", "Environment", "Uploaded at",
              "UID", "MapType", "Notes"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    for i, m in enumerate(maps, 1):
        env_icon = {
            "Valley": "VF",
            "Canyon": "CN",
            "Stadium": "ST",
            "Lagoon": "LG",
        }.get(m.get("Environment", ""), "  ")

        # Clean up MapType display
        mt_display = format_map_type(m.get("MapType", ""))
        notes = m.get("Notes", "").replace("|", "\\|")

        row = [
            str(i),
            m.get("Map name", "").replace("|", "\\|"),
            m.get("Author login", "").replace("|", "\\|"),
            f"{env_icon} {m.get('Environment', '')}",
            m.get("Uploaded at", ""),
            f"`{m['UID']}`" if m.get("UID") else "",
            mt_display,
            notes,
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Author stats
    author_counts: dict[str, int] = {}
    for m in maps:
        auth = m["Author login"] or "(none)"
        author_counts[auth] = author_counts.get(auth, 0) + 1

    lines.append("## Authors")
    lines.append("")
    lines.append("| Author | Maps |")
    lines.append("|--------|------|")
    for auth in sorted(author_counts.keys(), key=lambda a: -author_counts[a]):
        lines.append(f"| {auth} | {author_counts[auth]} |")
    lines.append("")

    # UID reference list (for easy copying)
    lines.append("## UIDs")
    lines.append("")
    lines.append("```")
    for m in maps:
        if m.get("UID"):
            lines.append(f"{m['UID']}  {m.get('Map name', '')}  ({m.get('Author login', '')})")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown table from Pursuit Maps Google Sheets"
    )
    parser.add_argument(
        "--sheet-id",
        default=DEFAULT_SHEET_ID,
        help=f"Google Sheet ID (default: {DEFAULT_SHEET_ID})",
    )
    parser.add_argument(
        "--gid",
        type=int,
        default=DEFAULT_GID,
        help=f"Sheet GID / tab ID (default: {DEFAULT_GID})",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="pursuit_maps_table.md",
        help="Output markdown file (default: pursuit_maps_table.md)",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional JSON output file",
    )
    parser.add_argument(
        "--with-thumbnails",
        default="",
        help="Path to thumbnails directory ({UID}.jpg files)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Output raw JSON only (no markdown)",
    )
    parser.add_argument(
        "--sheet-url",
        default="",
        help="Google Sheets URL (for linking in markdown)",
    )
    args = parser.parse_args()

    print(f"Reading sheet {args.sheet_id}, gid={args.gid}...", file=sys.stderr)
    sheet_data = read_sheet(args.sheet_id, args.gid)

    maps = extract_maps(sheet_data)
    print(f"Extracted {len(maps)} maps with UID", file=sys.stderr)

    # JSON output
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(maps, f, ensure_ascii=False, indent=2)
        print(f"JSON saved: {args.json_output}", file=sys.stderr)

    if args.json_only:
        print(json.dumps(maps, ensure_ascii=False, indent=2))
        return

    # Markdown output
    sheet_url = args.sheet_url or (
        f"https://docs.google.com/spreadsheets/d/{args.sheet_id}/edit"
        f"#gid={args.gid}"
    )

    md = generate_markdown(maps, args.with_thumbnails, sheet_url)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Markdown saved: {args.output}", file=sys.stderr)

    # Also print to stdout
    print(md)


if __name__ == "__main__":
    main()
