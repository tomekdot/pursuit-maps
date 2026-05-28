#!/usr/bin/env python3
"""
Pursuit Maps Synchronizer
==========================
Automatyczna synchronizacja danych map Pursuit z trzech źródeł:
  1. ManiaPlanet Feedback (feedback.prod.live.maniaplanet.com/votes/display/106)
  2. Google Sheets (gviz API)
  3. ManiaExchange API (tm.maniaexchange)

Generuje:
  - enriched_feedback_106.csv - pełny CSV z wszystkimi danymi
  - sheet_fill_report.md - gotowy raport do wklejenia w Sheet
  - changes_diff.md - nowe/zmienione mapy od ostatniego uruchomienia
  - json output dla dalszego przetwarzania

Użycie:
    python3 pursue_maps_sync.py                  # pełna synchronizacja
    python3 pursue_maps_sync.py --fetch-feedback # tylko pobierz feedback
    python3 pursue_maps_sync.py --fetch-mx       # tylko pobierz MX
    python3 pursue_maps_sync.py --dry-run        # podgląd bez zapisu
    python3 pursue_maps_sync.py --compare        # tylko porównaj z poprzednim stanem
    python3 pursue_maps_sync.py --auto-fill      # wygeneruj gotowe wartości do wklejenia
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(r"C:\Users\tomekdot\pursuit-maps")
CSV_PATH = Path(r"C:\Users\tomekdot\maniaplanet_feedback_106_with_uid.csv")
SNAPSHOT_PATH = BASE_DIR / "last_snapshot.json"
FEEDBACK_CACHE = BASE_DIR / "feedback_cache.json"

# ── Google Sheets Config ──────────────────────────────────────────────────────

SHEET_ID = "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ"
SHEET_GID = 763170857
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?gid={SHEET_GID}&tqx=out:json&headers=1"
)

# ── ManiaExchange API ─────────────────────────────────────────────────────────

MX_API = "https://tm.mania.exchange/api/maps/get_map_info/id"

# ── Feedback URL ──────────────────────────────────────────────────────────────

FEEDBACK_URL = "https://feedback.prod.live.maniaplanet.com/votes/display/106"


# ── Utility functions ─────────────────────────────────────────────────────────

def parse_google_date(val):
    """Parse Google Sheets Date(y,m,d,...) -> 'yyyy-mm-dd hh:mm:ss'"""
    if not val or not isinstance(val, str):
        return ""
    m = re.match(r"Date\((\d+),(\d+),(\d+)(?:,(\d+),(\d+),(\d+))?\)", val.strip())
    if not m:
        return str(val)
    y, mo, d = int(m.group(1)), int(m.group(2)) + 1, int(m.group(3))
    h = int(m.group(4)) if m.group(4) else 0
    mi = int(m.group(5)) if m.group(5) else 0
    s = int(m.group(6)) if m.group(6) else 0
    try:
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
    except ValueError:
        return str(val)


def fmt_num(v):
    """Format number: float->int if whole, else string."""
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v) if v else ""


def clean(v):
    """Clean string value."""
    if v is None:
        return ""
    s = str(v).strip()
    return s


def http_get(url, timeout=30, retries=2, delay=1):
    """HTTP GET with retry."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-Sync/1.0)"
            })
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < retries:
                time.sleep(delay)
            else:
                return None


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def fetch_feedback_page():
    """Fetch ManiaPlanet Feedback page and parse maps from HTML + embedded JS.

    This is the authoritative source - 249 maps with UID, name, thumbnail hash.
    The page structure: <h6>map name</h6> ... <img src="...maps/{hash}/{UID}.jpg">

    Returns list of dicts with keys: uid, name, hash (from page) + vote data.
    """
    html = http_get(FEEDBACK_URL)
    if not html:
        print("  WARNING: Could not fetch feedback page - using cached data", file=sys.stderr)
        return None

    maps = []

    # Strategy 1: Extract UIDs from img src patterns in HTML
    # Pattern: /maps/{hex_hash}/{UID_base62}.jpg
    img_pattern = re.findall(
        r'src=["\']https://files-v4\.live\.maniaplanet\.com/maps/([a-f0-9]+)/([a-zA-Z0-9_\-]+)\.jpg["\']',
        html
    )

    # Strategy 2: Extract map names from <h6> tags
    # Feedbacks shows maps with <h6>YES/NO</h6><h6>5 STARS</h6><h6>MAP NAME</h6>
    h6_pattern = re.findall(r'<h6[^>]*>(.*?)</h6>', html, re.DOTALL)
    names = []
    for h6 in h6_pattern:
        text = re.sub(r'<[^>]+>', '', h6).strip()
        if text and text not in ('YES/NO', '5 STARS', '', 'YES', 'NO'):
            names.append(text)

    # Strategy 3: Look for map data in JSON embedded in the page
    # Some versions have window.__INITIAL_STATE__ or similar
    json_patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        r'window\.__data\s*=\s*({.*?});',
        r'"maps"\s*:\s*(\[.*?\])',
    ]
    embedded_maps = None
    for pattern in json_patterns:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict) and 'maps' in data:
                    embedded_maps = data['maps']
                elif isinstance(data, list):
                    embedded_maps = data
                break
            except json.JSONDecodeError:
                continue

    if embedded_maps:
        print(f"  Found {len(embedded_maps)} maps in embedded JSON", file=sys.stderr)
        for m in embedded_maps:
            uid = m.get('uid', m.get('trackUID', m.get('UID', '')))
            name = m.get('name', m.get('Name', m.get('mapName', '')))
            hash_val = m.get('hash', m.get('Hash', m.get('imageHash', '')))
            if uid:
                maps.append({
                    'uid': clean(uid),
                    'name': clean(name),
                    'hash': clean(hash_val),
                })
    else:
        # Match img src with h6 names
        print(f"  Found {len(img_pattern)} img UIDs, {len(names)} h6 names", file=sys.stderr)
        for i, (hash_val, uid) in enumerate(img_pattern):
            name = names[i] if i < len(names) else ""
            maps.append({
                'uid': clean(uid),
                'name': clean(name),
                'hash': clean(hash_val),
            })

    # Deduplicate by uid
    seen = set()
    unique = []
    for m in maps:
        if m['uid'] and m['uid'] not in seen:
            seen.add(m['uid'])
            unique.append(m)

    # If we got 0 maps, the page structure may have changed significantly
    if len(unique) == 0:
        print("  WARNING: Could not parse maps from feedback page", file=sys.stderr)
        print("  Trying alternative parsing...", file=sys.stderr)
        # Broader search for any UID-like strings near img tags
        all_uids = re.findall(r'/maps/[a-f0-9]+/([a-zA-Z0-9_\-]+)\.jpg', html)
        all_uids = list(set(all_uids))
        print(f"  Found {len(all_uids)} unique UIDs from img src", file=sys.stderr)
        for uid in all_uids:
            maps.append({'uid': uid, 'name': '', 'hash': ''})
        unique = maps

    return unique


def fetch_sheet_data():
    """Fetch Google Sheets data via gviz API."""
    raw = http_get(SHEET_URL)
    if not raw:
        print("  WARNING: Could not fetch sheet data", file=sys.stderr)
        return None

    try:
        json_str = raw.split("(", 1)[1].rsplit(");", 1)[0]
        data = json.loads(json_str)
    except (IndexError, json.JSONDecodeError) as e:
        print(f"  ERROR: Failed to parse sheet response: {e}", file=sys.stderr)
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
                    return parse_google_date(v)
                if isinstance(v, float) and v == int(v):
                    return str(int(v))
                return str(v).strip()
            return ""

        uid = gc(5)
        if not uid:
            continue

        maps.append({
            "uid": uid,
            "_sheet_row": gc(0),
            "sheet_name": gc(1),
            "sheet_author": gc(2),
            "sheet_env": gc(3),
            "sheet_uploaded": gc(4),
            "sheet_maptype": gc(6),
            "sheet_notes": gc(7),
        })

    return maps


def fetch_mx_data(uid):
    """Fetch single map data from ManiaExchange API."""
    url = f"{MX_API}/{uid}"
    raw = http_get(url, timeout=15, retries=1, delay=0.5)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "TrackID" in data:
            return data
        return {}
    except json.JSONDecodeError:
        return {}


def enrich_with_mx(maps, delay=0.15, force=False):
    """Add MX data to all maps that have UIDs. Shows progress."""
    enriched = 0
    skipped = 0

    for i, m in enumerate(maps):
        uid = m.get("uid", "")
        if not uid:
            continue

        mx = fetch_mx_data(uid)

        # Store MX fields with mx_ prefix
        if mx and "TrackID" in mx:
            m["mx_trackid"] = mx.get("TrackID", "")
            m["mx_name"] = clean(mx.get("Name", ""))
            m["mx_gbxname"] = clean(mx.get("GbxMapName", ""))
            m["mx_author"] = clean(mx.get("AuthorLogin", ""))
            m["mx_maptype"] = clean(mx.get("MapType", ""))
            m["mx_titlepack"] = clean(mx.get("TitlePack", ""))
            m["mx_env"] = clean(mx.get("EnvironmentName", ""))
            m["mx_vehicle"] = clean(mx.get("VehicleName", ""))
            m["mx_difficulty"] = clean(mx.get("DifficultyName", ""))
            m["mx_length"] = clean(mx.get("LengthName", ""))
            m["mx_uploaded"] = clean(mx.get("UploadedAt", ""))
            m["mx_updated"] = clean(mx.get("UpdatedAt", ""))
            m["mx_downloadable"] = "true" if mx.get("Downloadable") else "false"
            m["mx_comments"] = clean(mx.get("Comments", ""))
            m["mx_awards"] = fmt_num(mx.get("AwardCount"))
            m["mx_has_thumb"] = "true" if mx.get("HasThumbnail") else "false"
            m["mx_has_screenshot"] = "true" if mx.get("HasScreenshot") else "false"
            enriched += 1
        else:
            skipped += 1

        if (i + 1) % 25 == 0:
            print(f"  MX [{i+1}/{len(maps)}] enriched={enriched}, not_found={skipped}",
                  file=sys.stderr)

        time.sleep(delay)

    print(f"  MX done: {enriched} found, {skipped} not found", file=sys.stderr)
    return enriched, skipped


# ── Comparison Logic ──────────────────────────────────────────────────────────

def compare_and_report(feedback_maps, sheet_maps, mx_enriched):
    """Compare data from all sources and generate actionable report."""
    report = {
        "new_in_feedback": [],
        "missing_in_feedback": [],
        "new_in_sheet": [],
        "missing_in_sheet": [],
        "sheet_empty_fields": [],
        "mx_data_available": [],
        "env_mismatches": [],
        "author_mismatches": [],
    }

    # Build lookup maps
    fb_by_uid = {m["uid"]: m for m in feedback_maps}
    sh_by_uid = {m["uid"]: m for m in sheet_maps}
    mx_by_uid = {m["uid"]: m for m in mx_enriched if m.get("mx_trackid")}

    all_uids = set(list(fb_by_uid.keys()) + list(sh_by_uid.keys()))

    for uid in sorted(all_uids):
        fb = fb_by_uid.get(uid)
        sh = sh_by_uid.get(uid)
        mx = mx_by_uid.get(uid)

        # New in feedback (not in sheet)
        if fb and not sh:
            report["new_in_feedback"].append({
                "uid": uid,
                "name": fb.get("name", ""),
                "hash": fb.get("hash", ""),
                "mx_name": mx.get("mx_name", "") if mx else "",
                "mx_author": mx.get("mx_author", "") if mx else "",
                "mx_env": mx.get("mx_env", "") if mx else "",
                "mx_maptype": mx.get("mx_maptype", "") if mx else "",
                "mx_uploaded": mx.get("mx_uploaded", "") if mx else "",
            })

        # New in sheet (not in feedback)
        if sh and not fb:
            report["new_in_sheet"].append({
                "uid": uid,
                "name": sh.get("sheet_name", ""),
                "author": sh.get("sheet_author", ""),
            })

        # Check for empty fields in sheet
        if sh:
            empty = []
            if not sh.get("sheet_name"): empty.append("Map name")
            if not sh.get("sheet_author"): empty.append("Author login")
            if not sh.get("sheet_env"): empty.append("Environment")
            if not sh.get("sheet_uploaded"): empty.append("Uploaded at")
            if not sh.get("sheet_maptype"): empty.append("MapType")
            if empty:
                # Check if we can fill from MX or feedback
                fill_from_mx = {}
                fill_from_fb = {}
                if mx:
                    if not sh.get("sheet_author") and mx.get("mx_author"):
                        fill_from_mx["Author login"] = mx["mx_author"]
                    if not sh.get("sheet_env") and mx.get("mx_env"):
                        fill_from_mx["Environment"] = mx["mx_env"]
                    if not sh.get("sheet_maptype") and mx.get("mx_maptype"):
                        fill_from_mx["MapType"] = mx["mx_maptype"]
                    if not sh.get("sheet_name") and mx.get("mx_name"):
                        fill_from_mx["Map name"] = mx["mx_name"]
                if fb:
                    if not sh.get("sheet_name") and fb.get("name"):
                        fill_from_fb["Map name"] = fb["name"]

                report["sheet_empty_fields"].append({
                    "uid": uid,
                    "sheet_row": sh.get("_sheet_row", ""),
                    "sheet_name": sh.get("sheet_name", ""),
                    "missing": empty,
                    "fill_from_mx": fill_from_mx,
                    "fill_from_feedback": fill_from_fb,
                })

        # Check for environment mismatches
        if fb and sh:
            fb_name = fb.get("name", "")
            sh_name = sh.get("sheet_name", "")
            if fb_name and sh_name and fb_name != sh_name:
                # Check if it's a known alias
                pass  # track name differences

    return report


# ── Report Generators ────────────────────────────────────────────────────────

def generate_sheet_fill_report(report, output_path):
    """Generate markdown report ready for sheet filling. One section per category."""
    lines = []
    lines.append("# Sheet Fill Report - Generated " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")
    lines.append("Google Sheet: https://docs.google.com/spreadsheets/d/" + SHEET_ID + "/edit#gid=" + str(SHEET_GID))
    lines.append("")

    # Section 1: Maps with empty fields that CAN be auto-filled
    auto_fill = [e for e in report["sheet_empty_fields"]
                 if e.get("fill_from_mx") or e.get("fill_from_feedback")]
    if auto_fill:
        lines.append("## AUTO-FILL: Maps with data available from MX/Feedback")
        lines.append("")
        lines.append("| Sheet Row | Map name | Missing | Fill from MX | Fill from Feedback |")
        lines.append("|-----------|----------|---------|--------------|-------------------|")
        for e in auto_fill:
            row = e["sheet_row"] or "?"
            name = e["sheet_name"] or e["uid"][:30]
            missing = ", ".join(e["missing"])
            mx_vals = "; ".join(f"{k}='{v}'" for k, v in e.get("fill_from_mx", {}).items())
            fb_vals = "; ".join(f"{k}='{v}'" for k, v in e.get("fill_from_feedback", {}).items())
            lines.append(f"| {row} | {name} | {missing} | {mx_vals} | {fb_vals} |")
        lines.append("")

    # Section 2: Maps with empty fields that CANNOT be auto-filled manually
    manual = [e for e in report["sheet_empty_fields"]
              if not e.get("fill_from_mx") and not e.get("fill_from_feedback")]
    if manual:
        lines.append("## MANUAL: Maps needing investigation")
        lines.append("")
        lines.append("| Sheet Row | Map name | UID | Missing fields |")
        lines.append("|-----------|----------|-----|----------------|")
        for e in manual:
            row = e["sheet_row"] or "?"
            name = e["sheet_name"] or "(empty)"
            missing = ", ".join(e["missing"])
            uid_short = e["uid"][:30]
            lines.append(f"| {row} | {name} | `{uid_short}` | {missing} |")
        lines.append("")

    # Section 3: New maps in feedback not yet in sheet
    if report["new_in_feedback"]:
        lines.append("## NEW MAPS: In Feedback but not in Sheet")
        lines.append("")
        lines.append("| # | Map name | Author (MX) | Environment (MX) | MapType (MX) | Name (Feedback) | Source |")
        lines.append("|---|----------|-------------|-------------------|--------------|-----------------|--------|")
        for i, m in enumerate(report["new_in_feedback"], 1):
            lines.append(
                f"| {i} | {m['mx_name'] or m['name']} | {m.get('mx_author', '')} "
                f"| {m.get('mx_env', '')} | {m.get('mx_maptype', '')} "
                f"| {m['name']} | {'MX' if m.get('mx_trackid') else 'feedback'} |"
            )
        lines.append("")

    # Section 4: Maps in sheet but not in feedback (custom additions)
    if report["new_in_sheet"]:
        lines.append("## SHEET-ONLY: Maps in Sheet but not in Feedback")
        lines.append("")
        lines.append("| Map name | Author |")
        lines.append("|----------|--------|")
        for m in report["new_in_sheet"]:
            lines.append(f"| {m['name']} | {m.get('author', '')} |")
        lines.append("")

    # Section 5: Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Empty fields (auto-fill available): {len(auto_fill)}")
    lines.append(f"- Empty fields (manual research needed): {len(manual)}")
    lines.append(f"- New in feedback (not in sheet): {len(report['new_in_feedback'])}")
    lines.append(f"- New in sheet (not in feedback): {len(report['new_in_sheet'])}")
    lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def generate_csv(feedback_maps, mx_by_uid, output_path):
    """Generate the authoritative enriched CSV."""
    fieldnames = [
        "Lp.", "UID", "Map name", "Hash", "Thumbnail URL", "Map URL", "Author URL", "Feedback URL",
        "MX TrackID", "MX Name", "MX GbxMapName", "MX AuthorLogin",
        "MX MapType", "MX TitlePack", "MX EnvironmentName", "MX VehicleName",
        "MX DifficultyName", "MX LengthName",
        "MX UploadedAt", "MX UpdatedAt", "MX Downloadable",
        "MX Comments", "MX AwardCount",
        "MX HasThumbnail", "MX HasScreenshot",
    ]

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for i, m in enumerate(feedback_maps, 1):
            row = {
                "Lp.": str(i),
                "UID": m.get("uid", ""),
                "Map name": m.get("name", ""),
                "Hash": m.get("hash", ""),
                "Thumbnail URL": f"https://files-v4.live.maniaplanet.com/maps/{m.get('hash', '')}/{m.get('uid', '')}.jpg" if m.get("hash") else "",
                "Map URL": f"https://tm.mania.exchange/mapsearch?query={urllib.request.quote(m.get('name', ''))}",
                "Author URL": "",  # would need author from somewhere
                "Feedback URL": FEEDBACK_URL,
            }
            mx = mx_by_uid.get(m.get("uid", ""), {})
            if mx:
                row["MX TrackID"] = mx.get("mx_trackid", "")
                row["MX Name"] = mx.get("mx_name", "")
                row["MX GbxMapName"] = mx.get("mx_gbxname", "")
                row["MX AuthorLogin"] = mx.get("mx_author", "")
                row["MX MapType"] = mx.get("mx_maptype", "")
                row["MX TitlePack"] = mx.get("mx_titlepack", "")
                row["MX EnvironmentName"] = mx.get("mx_env", "")
                row["MX VehicleName"] = mx.get("mx_vehicle", "")
                row["MX DifficultyName"] = mx.get("mx_difficulty", "")
                row["MX LengthName"] = mx.get("mx_length", "")
                row["MX UploadedAt"] = mx.get("mx_uploaded", "")
                row["MX UpdatedAt"] = mx.get("mx_updated", "")
                row["MX Downloadable"] = mx.get("mx_downloadable", "")
                row["MX Comments"] = mx.get("mx_comments", "")
                row["MX AwardCount"] = mx.get("mx_awards", "")
                row["MX HasThumbnail"] = mx.get("mx_has_thumb", "")
                row["MX HasScreenshot"] = mx.get("mx_has_screenshot", "")

            writer.writerow(row)


def save_snapshot(feedback_maps, sheet_maps, mx_enriched):
    """Save current state as JSON for future comparison."""
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "feedback_count": len(feedback_maps),
        "sheet_count": len(sheet_maps),
        "mx_count": len([m for m in mx_enriched if m.get("mx_trackid")]),
        "feedback_uids": [m["uid"] for m in feedback_maps],
        "sheet_uids": [m["uid"] for m in sheet_maps],
    }
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pursuit Maps Synchronizer")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--fetch-feedback", action="store_true", help="Only fetch feedback")
    parser.add_argument("--fetch-mx-only", action="store_true", help="Only enrich with MX")
    parser.add_argument("--compare-only", action="store_true", help="Compare with snapshot")
    parser.add_argument("--delay", type=float, default=0.15, help="MX API delay (sec)")
    parser.add_argument("--output-csv", default=str(CSV_PATH), help="Output CSV path")
    parser.add_argument("--report", default=str(BASE_DIR / "sheet_fill_report.md"),
                       help="Output report path")
    args = parser.parse_args()

    print("=" * 60)
    print("Pursuit Maps Synchronizer v2.0")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # === Step 1: Fetch ManiaPlanet Feedback ===
    print("\n[1/4] Fetching ManiaPlanet Feedback page...")
    feedback_maps = None

    if not args.fetch_mx_only and not args.compare_only:
        feedback_maps = fetch_feedback_page()
        if feedback_maps:
            print(f"  Got {len(feedback_maps)} maps from feedback")

            # Save cache
            if not args.dry_run:
                with open(FEEDBACK_CACHE, "w", encoding="utf-8") as f:
                    json.dump(feedback_maps, f, ensure_ascii=False, indent=2)
                print(f"  Cached to {FEEDBACK_CACHE}")
        else:
            # Try loading from CSV (which has UID + name + hash from previous feedback scrape)
            print("  Falling back to CSV data...", file=sys.stderr)
            if CSV_PATH.exists():
                with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        uid = row.get("UID", "").strip()
                        name = row.get("Map name", "").strip()
                        hash_val = row.get("Hash", "").strip()
                        if uid:
                            feedback_maps = feedback_maps or []
                            feedback_maps.append({"uid": uid, "name": name, "hash": hash_val})
                print(f"  Loaded {len(feedback_maps)} maps from CSV")

    if args.fetch_feedback:
        return

    if not feedback_maps:
        print("ERROR: No feedback data available", file=sys.stderr)
        sys.exit(1)

    # === Step 2: Fetch Google Sheets ===
    print("\n[2/4] Fetching Google Sheets data...")
    sheet_maps = fetch_sheet_data()
    if sheet_maps:
        sheet_by_uid = {m["uid"]: m for m in sheet_maps}
        print(f"  Got {len(sheet_maps)} maps from Sheets")
    else:
        sheet_by_uid = {}
        sheet_maps = []
        print("  WARNING: No sheet data - will proceed with feedback + MX only")

    # === Step 3: Enrich with ManiaExchange ===
    print(f"\n[3/4] Enriching {len(feedback_maps)} maps with ManiaExchange API...")
    if args.fetch_mx_only:
        # Load existing feedback data first
        if FEEDBACK_CACHE.exists():
            with open(FEEDBACK_CACHE, "r", encoding="utf-8") as f:
                feedback_maps = json.load(f)
        else:
            print("  No feedback cache found, fetching...")
            feedback_maps = fetch_feedback_page() or []

    enriched_count, skipped_count = enrich_with_mx(feedback_maps, delay=args.delay)
    mx_by_uid = {m["uid"]: m for m in feedback_maps if m.get("mx_trackid")}

    # === Step 4: Generate Reports ===
    print("\n[4/4] Generating reports...")
    report = compare_and_report(feedback_maps, sheet_maps, feedback_maps)

    fill_report_path = Path(args.report)
    generate_sheet_fill_report(report, fill_report_path)
    print(f"  Report: {fill_report_path}")

    # Save enriched CSV
    if not args.dry_run:
        generate_csv(feedback_maps, mx_by_uid, args.output_csv)
        print(f"  CSV: {args.output_csv}")

        # Save snapshot for future comparison
        save_snapshot(feedback_maps, sheet_maps, feedback_maps)
        print(f"  Snapshot: {SNAPSHOT_PATH}")

    # === Print Summary ===
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Feedback maps:    {len(feedback_maps)}")
    print(f"  Sheet maps:       {len(sheet_maps)}")
    print(f"  MX enriched:      {enriched_count}")
    print(f"  MX not found:     {skipped_count}")
    print(f"  Auto-fillable:    {len([e for e in report['sheet_empty_fields'] if e.get('fill_from_mx') or e.get('fill_from_feedback')])}")
    print(f"  Manual research:  {len([e for e in report['sheet_empty_fields'] if not e.get('fill_from_mx') and not e.get('fill_from_feedback')])}")
    print(f"  New in feedback:  {len(report['new_in_feedback'])}")
    print(f"  Sheet-only maps:  {len(report['new_in_sheet'])}")
    print()
    print(f"  Report file: {fill_report_path}")
    if not args.dry_run:
        print(f"  CSV file: {args.output_csv}")
        print(f"  Snapshot: {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
