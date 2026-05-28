#!/usr/bin/env python3
"""
Pursuit Maps Vote Tracker
==========================
Fetches current star ratings from ManiaPlanet Feedback, compares with previous
snapshot, and generates a report of changes.

Schedule: cron 5:00 UTC daily
Output: vote_report.md (committed to repo) + vote_history.json

Columns tracked per map:
  - YES/NO Rating + vote count
  - 5-Star Avg + total votes
  - Star distribution (5/4/3/2/1 star %)
"""

import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path = [p for p in sys.path if "Python313" not in p and "Python314" not in p]

# ── Config ────────────────────────────────────────────────────────────────────

FEEDBACK_URL = "https://feedback.prod.live.maniaplanet.com/votes/display/106"
BASE_DIR = Path(__file__).parent.parent.resolve()
HISTORY_PATH = BASE_DIR / "vote_history.json"
REPORT_PATH = BASE_DIR / "vote_report.md"


def http_get(url, timeout=30, retries=2, delay=1):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-VoteTracker/1.0)"
            })
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8")
        except Exception:
            if attempt < retries:
                time.sleep(delay)
    return None


def fetch_current_votes():
    """Fetch current vote data from ManiaPlanet Feedback."""
    import time
    html = http_get(FEEDBACK_URL)
    if not html:
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

        name_m = re.search(r'title="([^"]+)"', section)
        name = name_m.group(1).strip() if name_m else ""

        s = re.sub(r'\s+', ' ', section)

        # YES/NO
        yn_m = re.search(
            r'YES.*?NO.*?<span style="color: gold[^"]*">.*?</span>\s*([\d.]+)\s*\((\d+)\)',
            s, re.DOTALL
        )
        yn_rating = float(yn_m.group(1)) if yn_m else 0.0
        yn_votes = int(yn_m.group(2)) if yn_m else 0

        # 5 STARS
        st_m = re.search(
            r'5 STARS.*?<span style="color: gold[^"]*">.*?</span>\s*([\d.]+)\s*\((\d+)\)',
            s, re.DOTALL
        )
        stars_avg = float(st_m.group(1)) if st_m else 0.0
        stars_total = int(st_m.group(2)) if st_m else 0

        # Percentage bars
        after = s[s.find(st_m.group(0)) + len(st_m.group(0)):] if st_m else ""
        bars = re.findall(r'width:\s*(\d+)%', after[:500])
        pcts = [int(b) for b in bars[:5]]

        maps.append({
            "uid": uid,
            "name": name,
            "yn_rating": yn_rating,
            "yn_votes": yn_votes,
            "stars_avg": stars_avg,
            "stars_total": stars_total,
            "pcts": pcts,  # [5-star%, 4-star%, 3-star%, 2-star%, 1-star%]
        })

    return maps


def load_history():
    """Load previous vote snapshot."""
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"snapshots": []}


def save_history(history):
    """Save vote history."""
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def compare_and_report(current, history):
    """Compare current votes with last snapshot and generate report."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Get last snapshot
    snapshots = history.get("snapshots", [])
    if snapshots:
        last = snapshots[-1]
        last_data = {m["uid"]: m for m in last.get("maps", [])}
        last_time = last.get("timestamp", "unknown")
    else:
        last_data = {}
        last_time = "N/A (first run)"

    # Compute changes
    risen = []    # maps that went up
    fallen = []   # maps that went down
    new_maps = [] # new maps not in last snapshot
    total_yn_votes = 0
    total_stars_votes = 0

    for m in current:
        uid = m["uid"]
        total_yn_votes += m["yn_votes"]
        total_stars_votes += m["stars_total"]

        if uid in last_data:
            prev = last_data[uid]
            delta_yn = m["yn_rating"] - prev.get("yn_rating", 0)
            delta_stars = m["stars_avg"] - prev.get("stars_avg", 0)
            delta_yn_votes = m["yn_votes"] - prev.get("yn_votes", 0)
            delta_stars_votes = m["stars_total"] - prev.get("stars_total", 0)

            entry = {
                "uid": uid,
                "name": m["name"],
                "prev_yn": prev.get("yn_rating", 0),
                "curr_yn": m["yn_rating"],
                "delta_yn": delta_yn,
                "prev_yn_votes": prev.get("yn_votes", 0),
                "curr_yn_votes": m["yn_votes"],
                "prev_stars": prev.get("stars_avg", 0),
                "curr_stars": m["stars_avg"],
                "delta_stars": delta_stars,
                "prev_stars_votes": prev.get("stars_total", 0),
                "curr_stars_votes": m["stars_total"],
                "delta_stars_votes": delta_stars_votes,
            }

            if abs(delta_yn) >= 0.1 or abs(delta_stars) >= 0.1:
                if delta_yn + delta_stars > 0:
                    risen.append(entry)
                else:
                    fallen.append(entry)
        else:
            new_maps.append(m)

    # Sort by biggest change
    risen.sort(key=lambda x: -(x["delta_yn"] + x["delta_stars"]))
    fallen.sort(key=lambda x: (x["delta_yn"] + x["delta_stars"]))

    # Build report
    lines = []
    lines.append("# Vote Report - {}".format(now))
    lines.append("")
    lines.append("Generated: {} | Previous: {}".format(now, last_time))
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Total maps | {} |".format(len(current)))
    lines.append("| Total YES/NO votes | {} |".format(total_yn_votes))
    lines.append("| Total 5-Star votes | {} |".format(total_stars_votes))
    lines.append("| Maps with rating changes | {} |".format(len(risen) + len(fallen)))
    lines.append("- New maps | {} |".format(len(new_maps)))
    lines.append("| Ratings risen | {} |".format(len(risen)))
    lines.append("| Ratings fallen | {} |".format(len(fallen)))
    lines.append("")

    if risen:
        lines.append("## Ratings Risen (" + str(len(risen)) + ")")
        lines.append("")
        lines.append("| # | Map | YN before | YN after | YN delta | Stars before | Stars after | Stars delta |")
        lines.append("|---|-----|-----------|----------|----------|--------------|-------------|-------------|")
        for i, r in enumerate(risen, 1):
            yn_arrow = "↑" if r["delta_yn"] > 0 else ("↓" if r["delta_yn"] < 0 else "→")
            st_arrow = "↑" if r["delta_stars"] > 0 else ("↓" if r["delta_stars"] < 0 else "→")
            lines.append(
                "| {} | {} | {}/5 | {}/5 | {} {}{:.1f} | {}/5 | {}/5 | {} {}{:.1f} |".format(
                    i,
                    r["name"][:50],
                    r["prev_yn"], r["curr_yn"],
                    yn_arrow, "+" if r["delta_yn"] > 0 else "", r["delta_yn"],
                    r["prev_stars"], r["curr_stars"],
                    st_arrow, "+" if r["delta_stars"] > 0 else "", r["delta_stars"],
                )
            )
        lines.append("")

    if fallen:
        lines.append("## Ratings Fallen (" + str(len(fallen)) + ")")
        lines.append("")
        lines.append("| # | Map | YN before | YN after | YN delta | Stars before | Stars after | Stars delta |")
        lines.append("|---|-----|-----------|----------|----------|--------------|-------------|-------------|")
        for i, r in enumerate(fallen, 1):
            yn_arrow = "↑" if r["delta_yn"] > 0 else ("↓" if r["delta_yn"] < 0 else "→")
            st_arrow = "↑" if r["delta_stars"] > 0 else ("↓" if r["delta_stars"] < 0 else "→")
            lines.append(
                "| {} | {} | {}/5 | {}/5 | {} {}{:.1f} | {}/5 | {}/5 | {} {}{:.1f} |".format(
                    i,
                    r["name"][:50],
                    r["prev_yn"], r["curr_yn"],
                    yn_arrow, "+" if r["delta_yn"] > 0 else "", r["delta_yn"],
                    r["prev_stars"], r["curr_stars"],
                    st_arrow, "+" if r["delta_stars"] > 0 else "", r["delta_stars"],
                )
            )
        lines.append("")

    if new_maps:
        lines.append("## New Maps (" + str(len(new_maps)) + ")")
        lines.append("")
        lines.append("| # | Map | YN Rating | YN Votes | 5-Star Avg | 5-Star Total |")
        lines.append("|---|-----|-----------|----------|------------|--------------|")
        for i, m in enumerate(new_maps, 1):
            lines.append(
                "| {} | {} | {}/5 | {} | {}/5 | {} |".format(
                    i, m["name"][:50],
                    m["yn_rating"], m["yn_votes"],
                    m["stars_avg"], m["stars_total"],
                )
            )
        lines.append("")

    # Top rated maps
    sorted_by_stars = sorted(current, key=lambda x: x["stars_avg"], reverse=True)
    lines.append("## Top 10 by 5-Star Rating")
    lines.append("")
    lines.append("| # | Map | 5-Star Avg | Total Votes | YN Rating |")
    lines.append("|---|-----|------------|-------------|-----------|")
    for i, m in enumerate(sorted_by_stars[:10], 1):
        lines.append(
            "| {} | {} | {}/5 | {} | {}/5 |".format(
                i, m["name"][:50],
                m["stars_avg"], m["stars_total"],
                m["yn_rating"],
            )
        )
    lines.append("")

    # Most voted
    sorted_by_votes = sorted(current, key=lambda x: x["stars_total"], reverse=True)
    lines.append("## Top 10 by Total Votes")
    lines.append("")
    lines.append("| # | Map | Total Votes | 5-Star Avg | YN Rating |")
    lines.append("|---|-----|-------------|-----------|-----------|")
    for i, m in enumerate(sorted_by_votes[:10], 1):
        lines.append(
            "| {} | {} | {} | {}/5 | {}/5 |".format(
                i, m["name"][:50],
                m["stars_total"],
                m["stars_avg"],
                m["yn_rating"],
            )
        )
    lines.append("")

    # Overall stats
    all_stars = [m["stars_avg"] for m in current if m["stars_avg"] > 0]
    all_yn = [m["yn_rating"] for m in current if m["yn_rating"] > 0]
    lines.append("## Overall Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Avg 5-Star rating | {}/5 |".format(
        round(sum(all_stars) / max(len(all_stars), 1), 2)))
    lines.append("| Avg YES/NO rating | {}/5 |".format(
        round(sum(all_yn) / max(len(all_yn), 1), 2)))
    lines.append("| Maps with 4.5+ stars | {} |".format(
        sum(1 for s in all_stars if s >= 4.5)))
    lines.append("| Maps with 4.0+ stars | {} |".format(
        sum(1 for s in all_stars if s >= 4.0)))
    lines.append("| Maps with < 3.0 stars | {} |".format(
        sum(1 for s in all_stars if s < 3.0)))
    lines.append("")

    return "\n".join(lines)


def main():
    import time

    print("Vote Tracker - starting...", file=sys.stderr)

    # Fetch current votes
    print("Fetching feedback...", file=sys.stderr)
    current = fetch_current_votes()
    if not current:
        print("ERROR: Could not fetch feedback", file=sys.stderr)
        sys.exit(1)
    print("Got {} maps".format(len(current)), file=sys.stderr)

    # Load history
    history = load_history()
    last_time = "N/A"
    if history.get("snapshots"):
        last_time = history["snapshots"][-1].get("timestamp", "unknown")

    # Generate report
    print("Comparing with last snapshot ({})...".format(last_time), file=sys.stderr)
    report = compare_and_report(current, history)

    # Write report
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print("Report: {}".format(REPORT_PATH), file=sys.stderr)

    # Save snapshot
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    history.setdefault("snapshots", []).append({
        "timestamp": now,
        "maps": current,
    })

    # Keep only last 90 snapshots (90 days)
    if len(history["snapshots"]) > 90:
        history["snapshots"] = history["snapshots"][-90:]

    save_history(history)
    print("History saved ({} snapshots)".format(len(history["snapshots"])), file=sys.stderr)

    # Print report to stdout
    print(report)


if __name__ == "__main__":
    main()
