#!/usr/bin/env python3
"""
Pursuit Maps Pipeline
=====================
Single script that fetches data from ManiaPlanet Feedback and ManiaExchange,
compares with Google Sheets, and pushes updates via GAS Web App.

Actions:
    sync    — fetch feedback + MX, compare with sheet, push new/changed maps
    votes   — update vote columns (YN Rating, 5-Star) in existing sheet rows
    report  — compare current votes with previous snapshot, generate report
    validate — run data quality checks, print summary

Usage:
    python3 pipeline.py                  # run sync + votes + report
    python3 pipeline.py --action sync    # sync only
    python3 pipeline.py --action votes   # votes only
    python3 pipeline.py --action report  # report only
    python3 pipeline.py --action validate  # validate data quality

Config:
    Set GAS_WEBAPP_URL env var or create pipeline/gas_url.txt with the GAS URL.
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

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
GAS_PATH = Path(__file__).parent / "gas_url.txt"
REPORT_PATH = BASE_DIR / "vote_report.md"
HISTORY_PATH = DATA_DIR / "vote_history.json"
FEEDBACK_CACHE = DATA_DIR / "feedback_full_json"

SHEET_ID = "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ"
SHEET_GID = 763170857
SHEET_API = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?gid={SHEET_GID}&tqx=out:json&headers=1"
)
MX_API = "https://tm.mania.exchange/api/maps/get_map_info/id"
FEEDBACK_URL = "https://feedback.prod.live.maniaplanet.com/votes/display/106"


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"  {msg}", file=sys.stderr)


def clean(v):
    return "" if v is None else str(v).strip()


def http_get(url, timeout=30, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-Pipeline/2.0)"
            })
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
    return None


def get_gas_url():
    url = os.environ.get("GAS_WEBAPP_URL", "")
    if url:
        return url.strip()
    if GAS_PATH.exists():
        return GAS_PATH.read_text().strip()
    print("ERROR: GAS_WEBAPP_URL not set and gas_url.txt not found", file=sys.stderr)
    sys.exit(1)


def gas_post(payload):
    """Send JSON payload to GAS Web App."""
    url = get_gas_url()
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode("utf-8"))


# ── Fetch: ManiaPlanet Feedback ─────────────────────────────────────────────

def fetch_feedback():
    """Fetch 249 maps from ManiaPlanet Feedback with separate YN + 5-Star ratings."""
    html = http_get(FEEDBACK_URL)
    if not html:
        log("ERROR: Cannot fetch feedback page")
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

        # YES/NO section (first gold span after YES/NO heading)
        yn_part = re.search(r'YES/NO.*?(?=5 STARS)', s, re.DOTALL)
        yn_rating, yn_votes = 0.0, 0
        if yn_part:
            m = re.search(
                r'<span style="color: gold[^"]*">.*?</span>\s*([\d.]+)\s*\((\d+)\)',
                yn_part.group(0), re.DOTALL
            )
            if m:
                yn_rating = float(m.group(1))
                yn_votes = int(m.group(2))

        # 5 STARS section (gold span after 5 STARS heading)
        st_part = re.search(r'5 STARS.*', s, re.DOTALL)
        stars_avg, stars_total = 0.0, 0
        if st_part:
            m = re.search(
                r'<span style="color: gold[^"]*">.*?</span>\s*([\d.]+)\s*\((\d+)\)',
                st_part.group(0), re.DOTALL
            )
            if m:
                stars_avg = float(m.group(1))
                stars_total = int(m.group(2))

        maps.append({
            "uid": uid, "hash": hash_val, "name": name,
            "yn_rating": yn_rating, "yn_votes": yn_votes,
            "stars_avg": stars_avg, "stars_total": stars_total,
        })

    # Cache to disk
    DATA_DIR.mkdir(exist_ok=True)
    with open(FEEDBACK_CACHE, "w") as f:
        json.dump(maps, f, ensure_ascii=False, indent=2)
    return maps


# ── Fetch: Google Sheets ────────────────────────────────────────────────────

def fetch_sheet():
    """Fetch current sheet data via gviz API."""
    raw = http_get(SHEET_API)
    if not raw:
        return None
    try:
        data = json.loads(raw.split("(", 1)[1].rsplit(");", 1)[0])
    except (IndexError, json.JSONDecodeError):
        return None

    rows = data.get("table", {}).get("rows", [])
    maps = []
    for row in rows:
        cells = row.get("c", [])
        def gc(idx):
            if idx < len(cells) and cells[idx]:
                v = cells[idx].get("v")
                if v is None:
                    return ""
                return str(v).strip()
            return ""
        uid = gc(5)
        if uid:
            maps.append({
                "uid": uid,
                "name": gc(1),
                "author": gc(2),
                "env": gc(3),
                "maptype": gc(6),
                "notes": gc(7),
            })
    return maps


# ── Fetch: ManiaExchange ────────────────────────────────────────────────────

def fetch_mx(uid):
    """Fetch map data from ManiaExchange API."""
    url = f"{MX_API}/{uid}"
    raw = http_get(url, timeout=15, retries=1)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "TrackID" in data:
            return data
    except json.JSONDecodeError:
        pass
    return {}


def enrich_with_mx(maps):
    """Add MX data to maps. Shows progress."""
    enriched = 0
    for i, m in enumerate(maps):
        uid = m.get("uid", "")
        if not uid:
            continue
        mx = fetch_mx(uid)
        if mx and "TrackID" in mx:
            raw_mt = clean(mx.get("MapType", ""))
            m["maptype"] = ("TrackMania\\" + raw_mt) if raw_mt and not raw_mt.startswith("TrackMania") else raw_mt
            m["author"] = clean(mx.get("AuthorLogin", ""))
            m["env"] = clean(mx.get("EnvironmentName", ""))
            m["mx_trackid"] = mx.get("TrackID", "")
            # UploadedAt from MX is ISO 8601: "2024-03-15T18:30:00Z" or similar
            uploaded_raw = clean(mx.get("UploadedAt", ""))
            if not uploaded_raw:
                uploaded_raw = clean(mx.get("Uploaded", ""))
            if uploaded_raw:
                # Normalize to "YYYY-MM-DD HH:MM:SS" for Sheets date parsing
                uploaded_raw = uploaded_raw.replace("T", " ").replace("Z", "")
                if "." in uploaded_raw:
                    uploaded_raw = uploaded_raw.split(".")[0]
                m["uploaded"] = uploaded_raw
            enriched += 1
        time.sleep(0.15)
        if (i + 1) % 50 == 0:
            log(f"MX [{i+1}/{len(maps)}] enriched={enriched}")
    log(f"MX done: {enriched} found")
    return enriched


# ── Action: sync ────────────────────────────────────────────────────────────

def action_sync():
    """Fetch feedback + MX, compare with sheet, push via GAS."""
    log("=== SYNC ===")

    # 1. Fetch feedback
    log("Fetching feedback...")
    feedback = fetch_feedback()
    if not feedback:
        return False
    log(f"Got {len(feedback)} maps from feedback")

    # 2. Fetch sheet
    log("Fetching sheet...")
    sheet = fetch_sheet()
    if sheet is None:
        log("WARNING: Cannot fetch sheet data")
        sheet = []
    log(f"Got {len(sheet)} sheet rows")

    sheet_uids = {m["uid"] for m in sheet}

    # 3. Find new maps (not in sheet)
    new_maps = [m for m in feedback if m["uid"] not in sheet_uids]
    log(f"New maps to add: {len(new_maps)}")

    if new_maps:
        # 4. Enrich new maps with MX
        log("Enriching with MX...")
        enrich_with_mx(new_maps)

        # 5. Build GAS sync payload
        gas_maps = []
        for m in new_maps:
            raw_mt = m.get("maptype", "")
            if raw_mt and not raw_mt.startswith("TrackMania"):
                raw_mt = "TrackMania\\" + raw_mt
            gas_maps.append({
                "uid": m["uid"],
                "name": m.get("name", ""),
                "author": m.get("author", ""),
                "env": m.get("env", ""),
                "uploaded": m.get("uploaded", ""),
                "maptype": raw_mt,
                "notes": "",
            })

        # 6. Send to GAS
        payload = {"action": "sync", "maps": gas_maps, "existing": {}}
        log(f"Sending {len(gas_maps)} maps to GAS...")
        result = gas_post(payload)
        log(f"GAS result: {json.dumps(result, indent=2)}")

    # 7. Update votes for ALL feedback maps
    log("Syncing votes to sheet...")
    action_votes(feedback)

    return True


# ── Action: votes ───────────────────────────────────────────────────────────

def action_votes(feedback=None):
    """Update vote columns in existing sheet rows via GAS."""
    if feedback is None:
        if FEEDBACK_CACHE.exists():
            with open(FEEDBACK_CACHE) as f:
                feedback = json.load(f)
        else:
            feedback = fetch_feedback()
        if not feedback:
            return False

    # Build votes payload for ALL maps
    votes = {}
    for m in feedback:
        yn_r = m.get("yn_rating", 0) or 0
        st_a = m.get("stars_avg", 0) or 0
        votes[m["uid"]] = {
            "yn_rating": "{:.1f}/5".format(yn_r),
            "yn_votes": str(int(m.get("yn_votes", 0) or 0)),
            "stars_avg": "{:.1f}/5".format(st_a),
            "stars_total": str(int(m.get("stars_total", 0) or 0)),
        }

    payload = {"action": "votes", "votes": votes, "uid_to_row": {}}
    log(f"Sending votes for {len(votes)} maps to GAS...")
    result = gas_post(payload)
    log(f"GAS result: {json.dumps(result, indent=2)}")
    return True


# ── Action: report ──────────────────────────────────────────────────────────

def action_report():
    """Compare current votes with previous snapshot, generate report."""
    log("=== VOTE REPORT ===")

    # Fetch current votes
    if FEEDBACK_CACHE.exists():
        with open(FEEDBACK_CACHE) as f:
            current = json.load(f)
    else:
        current = fetch_feedback()
    if not current:
        return False

    log(f"Current maps: {len(current)}")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Load history
    history = {}
    last_time = "N/A (first run)"
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH) as f:
            history = json.load(f)
        if history.get("snapshots"):
            last = history["snapshots"][-1]
            last_data = {m["uid"]: m for m in last.get("maps", [])}
            last_time = last.get("timestamp", "unknown")
        else:
            last_data = {}
    else:
        last_data = {}

    # Compare
    risen, fallen, new_maps = [], [], []
    for m in current:
        uid = m["uid"]
        if uid in last_data:
            prev = last_data[uid]
            d_yn = m.get("yn_rating", 0) - prev.get("yn_rating", 0)
            d_st = m.get("stars_avg", 0) - prev.get("stars_avg", 0)
            total_d = d_yn + d_st
            entry = {
                "name": m["name"],
                "prev_yn": prev.get("yn_rating", 0),
                "curr_yn": m.get("yn_rating", 0),
                "d_yn": d_yn,
                "prev_st": prev.get("stars_avg", 0),
                "curr_st": m.get("stars_avg", 0),
                "d_st": d_st,
            }
            if abs(d_yn) >= 0.1 or abs(d_st) >= 0.1:
                (risen if total_d > 0 else fallen).append(entry)
        else:
            new_maps.append(m)

    risen.sort(key=lambda x: -(x["d_yn"] + x["d_st"]))
    fallen.sort(key=lambda x: (x["d_yn"] + x["d_st"]))

    # Build report
    lines = [
        f"# Vote Report - {now}",
        "",
        f"Generated: {now} | Previous: {last_time}",
        "",
        "## Summary",
        "",
        f"- Total maps: {len(current)}",
        f"- Maps with rating changes: {len(risen) + len(fallen)}",
        f"- Ratings risen: {len(risen)}",
        f"- Ratings fallen: {len(fallen)}",
        f"- New maps: {len(new_maps)}",
        "",
    ]

    def fmt_rating(val):
        return f"{val:.1f}/5" if val else "N/A"

    if risen:
        lines.append("## Ratings Risen")
        lines.append("")
        lines.append("| # | Map | YN before | YN after | Stars before | Stars after |")
        lines.append("|---|-----|-----------|----------|--------------|-------------|")
        for i, r in enumerate(risen[:30], 1):
            lines.append(
                f"| {i} | {r['name'][:50]} | {fmt_rating(r['prev_yn'])} | "
                f"{fmt_rating(r['curr_yn'])} | {fmt_rating(r['prev_st'])} | "
                f"{fmt_rating(r['curr_st'])} |"
            )
        lines.append("")

    if fallen:
        lines.append("## Ratings Fallen")
        lines.append("")
        lines.append("| # | Map | YN before | YN after | Stars before | Stars after |")
        lines.append("|---|-----|-----------|----------|--------------|-------------|")
        for i, r in enumerate(fallen[:30], 1):
            lines.append(
                f"| {i} | {r['name'][:50]} | {fmt_rating(r['prev_yn'])} | "
                f"{fmt_rating(r['curr_yn'])} | {fmt_rating(r['prev_st'])} | "
                f"{fmt_rating(r['curr_st'])} |"
            )
        lines.append("")

    # Top 10
    sorted_stars = sorted(current, key=lambda x: x.get("stars_avg", 0), reverse=True)
    lines.append("## Top 10 by 5-Star Rating")
    lines.append("")
    lines.append("| # | Map | 5-Star Avg | Total Votes | YN Rating |")
    lines.append("|---|-----|------------|-------------|-----------|")
    for i, m in enumerate(sorted_stars[:10], 1):
        lines.append(
            f"| {i} | {m['name'][:50]} | {fmt_rating(m.get('stars_avg', 0))} | "
            f"{int(m.get('stars_total', 0))} | {fmt_rating(m.get('yn_rating', 0))} |"
        )
    lines.append("")

    report = "\n".join(lines)
    BASE_DIR = Path(__file__).parent.parent.resolve()
    with open(BASE_DIR / "vote_report.md", "w") as f:
        f.write(report)

    # Save snapshot
    history.setdefault("snapshots", []).append({
        "timestamp": now,
        "maps": current,
    })
    if len(history["snapshots"]) > 90:
        history["snapshots"] = history["snapshots"][-90:]
    DATA_DIR.mkdir(exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    log(f"Report saved ({len(risen)} risen, {len(fallen)} fallen)")
    return True


# ── Action: validate ────────────────────────────────────────────────────────

def action_validate():
    """Run data quality checks."""
    log("=== VALIDATE ===")

    errors = []

    # Check feedback cache
    if FEEDBACK_CACHE.exists():
        with open(FEEDBACK_CACHE) as f:
            feedback = json.load(f)
        log(f"Feedback: {len(feedback)} maps")

        # Check YN vs 5-Star are different where both exist
        both_nonzero = sum(1 for m in feedback if m.get("yn_rating", 0) > 0 and m.get("stars_avg", 0) > 0)
        same = sum(1 for m in feedback if m.get("yn_rating", 0) > 0 and m.get("yn_rating") == m.get("stars_avg"))
        log(f"  Maps with both YN+Stars: {both_nonzero}, identical values: {same}")

        # Check UIDs are unique
        uids = [m["uid"] for m in feedback]
        if len(uids) != len(set(uids)):
            errors.append("Duplicate UIDs in feedback cache")

        # Check for empty names
        empty_names = sum(1 for m in feedback if not m.get("name"))
        log(f"  Empty names: {empty_names}")

        # YN distribution
        from collections import Counter
        yn_dist = Counter()
        for m in feedback:
            r = m.get("yn_rating", 0)
            if r > 0:
                yn_dist[int(r)] += 1
        log(f"  YN rating distribution: {dict(sorted(yn_dist.items()))}")

        st_dist = Counter()
        for m in feedback:
            r = m.get("stars_avg", 0)
            if r > 0:
                st_dist[int(round(r * 2)) / 2] += 1
        log(f"  Stars rating distribution: {dict(sorted(st_dist.items()))}")
    else:
        log("No feedback cache found. Run 'sync' first.")

    # Check GAS connectivity
    try:
        gas_url = get_gas_url()
        req = urllib.request.Request(gas_url + "?action=ping")
        resp = urllib.request.urlopen(req, timeout=10)
        ping = json.loads(resp.read().decode("utf-8"))
        log(f"GAS status: {ping}")
    except Exception as e:
        log(f"GAS not reachable: {e}")
        errors.append("GAS Web App not reachable")

    if errors:
        log(f"ERRORS: {errors}")
    else:
        log("All checks passed!")

    return len(errors) == 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pursuit Maps Pipeline")
    parser.add_argument(
        "--action",
        choices=["sync", "votes", "report", "validate", "missing", "all"],
        default="all",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"Pursuit Maps Pipeline")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    ok = True
    if args.action in ("sync", "all"):
        ok = action_sync() and ok
    if args.action in ("votes", "all"):
        ok = action_votes() and ok
    if args.action in ("report", "all"):
        ok = action_report() and ok
    if args.action == "validate":
        ok = action_validate() and ok
    if args.action == "missing":
        ok = action_missing() and ok

    if ok:
        print("\nDone!")
    else:
        print("\nCompleted with errors.")
        sys.exit(1)


# ── Action: missing ─────────────────────────────────────────────────────────

def action_missing():
    """Find maps in feedback that are NOT in sheet (need MX enrichment)."""
    log("=== MISSING MAPS REPORT ===")

    # Load feedback
    if FEEDBACK_CACHE.exists():
        with open(FEEDBACK_CACHE) as f:
            feedback = json.load(f)
    else:
        feedback = fetch_feedback()
    if not feedback:
        return False

    log(f"Feedback: {len(feedback)} maps")

    # Fetch current sheet UIDs
    raw = http_get(SHEET_API)
    sheet_uids = set()
    if raw:
        try:
            data = json.loads(raw.split("(", 1)[1].rsplit(");", 1)[0])
            rows = data.get("table", {}).get("rows", [])
            for row in rows:
                cells = row.get("c", [])
                if len(cells) > 5 and cells[5]:
                    v = cells[5].get("v")
                    if v:
                        sheet_uids.add(str(v).strip())
        except:
            pass

    log(f"Sheet: {len(sheet_uids)} UIDs")

    # Find missing
    missing = [m for m in feedback if m["uid"] not in sheet_uids]
    log(f"Missing from sheet: {len(missing)}")

    if not missing:
        log("All feedback maps are in sheet!")
        return True

    # Try to enrich with MX for better info
    log("Enriching missing maps with MX...")
    for i, m in enumerate(missing):
        uid = m.get("uid", "")
        if uid:
            mx = fetch_mx(uid)
            if mx:
                m["author"] = clean(mx.get("AuthorLogin", ""))
                m["env"] = clean(mx.get("EnvironmentName", ""))
                raw_mt = clean(mx.get("MapType", ""))
                m["mx_maptype"] = raw_mt
                uploaded_raw = clean(mx.get("UploadedAt", ""))
                if not uploaded_raw:
                    uploaded_raw = clean(mx.get("Uploaded", ""))
                if uploaded_raw:
                    uploaded_raw = uploaded_raw.replace("T", " ").replace("Z", "")
                    if "." in uploaded_raw:
                        uploaded_raw = uploaded_raw.split(".")[0]
                    m["uploaded"] = uploaded_raw
            time.sleep(0.15)
        if (i + 1) % 50 == 0:
            log(f"  MX [{i+1}/{len(missing)}]")

    # Save report
    report_lines = [
        f"# Missing Maps Report - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Total in feedback: {len(feedback)}",
        f"In sheet: {len(sheet_uids)}",
        f"MISSING: {len(missing)}",
        "",
        "| # | Name | UID | Author | Env | MapType | YN | 5★ | Uploaded |",
        "|---|------|-----|--------|-----|---------|----|-----|----------|",
    ]

    for i, m in enumerate(missing, 1):
        yn = f"{m.get('yn_rating', 0):.1f}/5" if m.get('yn_rating') else "N/A"
        st = f"{m.get('stars_avg', 0):.1f}/5" if m.get('stars_avg') else "N/A"
        report_lines.append(
            f"| {i} | {m['name']} | {m['uid']} | {m.get('author', '')} | "
            f"{m.get('env', '')} | {m.get('mx_maptype', '')} | {yn} | {st} | {m.get('uploaded', '')} |"
        )

    # Also save as JSON for easy processing
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "missing_maps.json", "w") as f:
        json.dump(missing, f, ensure_ascii=False, indent=2)

    report_path = BASE_DIR / "missing_maps_report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))

    log(f"Report saved to {report_path}")
    log(f"JSON saved to {DATA_DIR / 'missing_maps.json'}")
    return True


if __name__ == "__main__":
    main()
