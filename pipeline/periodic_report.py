#!/usr/bin/env python3
"""
Pursuit Maps - Periodic (Lunar-phase) Report Generator
=======================================================

Generates comprehensive community-facing reports on a lunar cadence:
one report every ~4 moon phases (~7 days = new moon, first quarter,
full moon, last quarter). The report surfaces NEW characteristics of the
map pool that the daily vote_report does not:

  * How ratings changed over time (needs >= 2 vote_history snapshots)
  * Which maps are best / most popular / most improved / most declined
  * Which maps are being actively rated right now ("commonly played"
    proxy = fastest-growing vote counts, since raw play logs are unavailable)
  * Distribution by environment, author and map type (with ASCII charts)
  * 5-Star / YN rating histograms
  * New maps that appeared since the previous periodic report

DATA SOURCE: the Google Sheet via the public gviz API (source of truth,
includes all maps + author/env/maptype/notes + YN and 5-Star votes).
The script ALSO appends a snapshot to data/vote_history.json on every run
so the time-series for "how ratings changed" grows automatically.

No third-party dependencies (pure stdlib). Charts are ASCII bars so the
markdown renders anywhere (GitHub, chat, Sheet).

Usage:
    python3 periodic_report.py                 # generate now (weekly cadence)
    python3 periodic_report.py --cadence weekly
    python3 periodic_report.py --cadence monthly
    python3 periodic_report.py --auto          # only generate if due
    python3 periodic_report.py --no-snapshot   # don't append to vote_history
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
CURATED = DATA_DIR / "feedback_full.json"
HISTORY_PATH = DATA_DIR / "vote_history.json"
REPORTS_DIR = BASE_DIR / "reports" / "periodic"
LATEST_PATH = BASE_DIR / "reports" / "latest_periodic.md"
LAST_RUN_PATH = DATA_DIR / "last_periodic_run.json"
LAST_REPORT_PATH = DATA_DIR / "last_periodic_report.json"

# ── Sheet (gviz, public read) ─────────────────────────────────────────────────
SHEET_ID = "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ"
SHEET_GID = 763170857
SHEET_API = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
             f"/gviz/tq?gid={SHEET_GID}&tqx=out:json&headers=1")

WEEK_SECONDS = 7 * 24 * 3600
MONTH_SECONDS = 28 * 24 * 3600
MIN_VOTES = 20  # ignore low-sample noise in "best map" rankings

# Known new moon (UTC) for phase computation.
NEWMOON_REF = datetime(2000, 1, 6, 18, 14, 0, tzinfo=timezone.utc)
SYNODIC = 29.53058867  # days


# ── Helpers ──────────────────────────────────────────────────────────────────
def now_utc():
    return datetime.now(timezone.utc)


def moon_phase_name(dt):
    days = (dt - NEWMOON_REF).total_seconds() / 86400.0
    frac = (days % SYNODIC) / SYNODIC
    candidates = [(0.0, "New Moon"), (0.25, "First Quarter"),
                  (0.5, "Full Moon"), (0.75, "Last Quarter")]
    best = min(candidates, key=lambda c: min(abs(frac - c[0]),
                                              abs(frac - (c[0] + 1))))
    return best[1]


def http_get(url, timeout=30, retries=2):
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PursuitMaps-Report/1.0)"})
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        except Exception:
            time.sleep(1)
    return None


def fetch_sheet_maps():
    """Fetch all maps from the Sheet via gviz. Returns list of dicts.

    NOTE: the Sheet has an inconsistent column layout across rows (some rows
    have extra inserted columns, shifting YN/5-Star values). We therefore do
    NOT rely on fixed column indices for the vote columns — we parse each row
    by value shape:
        * a cell matching  "N.N/5"  is a rating (YN first, then 5-Star avg)
        * a plain number    is a vote count (YN votes first, then 5-Star total)
    UID / name / author / env / maptype / notes still come from fixed positions
    (those are stable).
    """
    raw = http_get(SHEET_API)
    if not raw:
        return None
    try:
        data = json.loads(raw.split("(", 1)[1].rsplit(");", 1)[0])
    except (IndexError, json.JSONDecodeError):
        return None

    rating_re = re.compile(r"^\d{1,2}(\.\d+)?/5$")

    def gc(cells, i):
        if i < len(cells) and cells[i]:
            v = cells[i].get("v")
            if v is None:
                return ""
            if isinstance(v, str):
                return v.strip()
            return v
        return ""

    out = []
    for row in data.get("table", {}).get("rows", []):
        cells = row.get("c", [])
        if len(cells) < 6:
            continue
        uid = gc(cells, 5)
        if not uid:
            continue

        # Date cells come back as Date(2015,2,8,...) -> normalize
        uploaded = gc(cells, 4)
        if isinstance(uploaded, str) and uploaded.startswith("Date("):
            m = re.match(r"Date\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)", uploaded)
            if m:
                y, mo, d, hh, mm, ss = (int(x) for x in m.groups())
                uploaded = f"{y}-{mo+1:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"

        # ── Value-shape parsing of the vote columns (idx >= 7) ──
        ratings, ints = [], []
        for v in cells[7:]:
            if not v:
                continue
            sval = v.get("v")
            if sval is None:
                continue
            if isinstance(sval, str):
                s = sval.strip()
                if rating_re.match(s):
                    ratings.append(float(s.split("/")[0]))
                elif re.fullmatch(r"\d+(\.\d+)?", s):
                    ints.append(int(float(s)))
            elif isinstance(sval, (int, float)):
                ints.append(int(sval))

        yn_rating = ratings[0] if len(ratings) >= 1 else 0.0
        stars_avg = ratings[1] if len(ratings) >= 2 else 0.0
        yn_votes = ints[0] if len(ints) >= 1 else 0
        stars_total = ints[1] if len(ints) >= 2 else 0

        out.append({
            "uid": str(uid).strip(),
            "name": gc(cells, 1),
            "author": gc(cells, 2),
            "env": gc(cells, 3),
            "uploaded": uploaded,
            "maptype": gc(cells, 6),
            "notes": gc(cells, 11),
            "yn_rating": yn_rating,
            "yn_votes": yn_votes,
            "stars_avg": stars_avg,
            "stars_total": stars_total,
        })
    return out


def load_history():
    if not HISTORY_PATH.exists():
        return []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("snapshots", [])


def append_snapshot(maps):
    """Append current maps to vote_history.json (keeps last 180 snapshots)."""
    history = {"snapshots": []}
    if HISTORY_PATH.exists():
        try:
            history = json.load(open(HISTORY_PATH, encoding="utf-8"))
        except Exception:
            history = {"snapshots": []}
    snaps = history.get("snapshots", [])
    if snaps:
        last = {m["uid"]: m for m in snaps[-1]["maps"]}
        # skip if identical to last snapshot (avoid daily noise flooding history)
        same = all(
            m["uid"] in last and
            abs((m.get("stars_avg", 0) or 0) - (last[m["uid"]].get("stars_avg", 0) or 0)) < 0.001 and
            int(m.get("stars_total", 0) or 0) == int(last[m["uid"]].get("stars_total", 0) or 0) and
            abs((m.get("yn_rating", 0) or 0) - (last[m["uid"]].get("yn_rating", 0) or 0)) < 0.001 and
            int(m.get("yn_votes", 0) or 0) == int(last[m["uid"]].get("yn_votes", 0) or 0)
            for m in maps if m["uid"] in last
        )
        if same and len(last) == len(maps):
            return len(snaps)  # unchanged, don't append
    # minimal snapshot to keep file small
    slim = [{
        "uid": m["uid"], "name": m["name"],
        "yn_rating": m.get("yn_rating", 0) or 0,
        "yn_votes": int(m.get("yn_votes", 0) or 0),
        "stars_avg": m.get("stars_avg", 0) or 0,
        "stars_total": int(m.get("stars_total", 0) or 0),
    } for m in maps]
    snaps.append({"timestamp": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "maps": slim})
    if len(snaps) > 180:
        snaps = snaps[-180:]
    history["snapshots"] = snaps
    DATA_DIR.mkdir(exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return len(snaps)


def ascii_bar(value, max_value, width=28, label=""):
    if max_value <= 0:
        filled = 0
    else:
        filled = max(1, int(round(width * value / max_value))) if value > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    return f"{label:<24s} {bar} {value}"


def fmt_r(v):
    return f"{v:.1f}/5" if v else "—"


def is_due(cadence):
    if not LAST_RUN_PATH.exists():
        return True
    try:
        last = json.load(open(LAST_RUN_PATH, encoding="utf-8"))["ts"]
        elapsed = (now_utc().timestamp() - last)
    except Exception:
        return True
    limit = WEEK_SECONDS if cadence == "weekly" else MONTH_SECONDS
    return elapsed >= limit


# ── Report builders ──────────────────────────────────────────────────────────
def top_by_stars(maps, n=10):
    ranked = [m for m in maps if (m.get("stars_total", 0) or 0) >= MIN_VOTES]
    ranked.sort(key=lambda x: (-(x.get("stars_avg", 0) or 0),
                                -(x.get("stars_total", 0) or 0)))
    return ranked[:n]


def most_voted(maps, n=10):
    ranked = sorted(maps, key=lambda x: -(x.get("stars_total", 0) or 0))
    return ranked[:n]


def top_by_yn(maps, n=10):
    ranked = [m for m in maps if (m.get("yn_votes", 0) or 0) >= MIN_VOTES]
    ranked.sort(key=lambda x: (-(x.get("yn_rating", 0) or 0),
                                -(x.get("yn_votes", 0) or 0)))
    return ranked[:n]


def most_active(maps, prev_snap, n=10):
    """Maps with the biggest increase in total votes vs previous snapshot.

    This is the best available proxy for 'commonly played right now' —
    we have no raw play logs, but a map people are actively choosing will
    keep gaining votes between snapshots.
    """
    if not prev_snap:
        # fallback: newest maps with the most votes already accumulated
        recent = [m for m in maps if (m.get("stars_total", 0) or 0) >= MIN_VOTES]
        recent.sort(key=lambda x: -(x.get("stars_total", 0) or 0))
        return [(m, 0) for m in recent[:n]], "newest maps with most votes (no history yet)"
    prev = {m["uid"]: m for m in prev_snap}
    movers = []
    for m in maps:
        p = prev.get(m["uid"])
        if not p:
            continue
        d = (int(m.get("stars_total", 0) or 0) - int(p.get("stars_total", 0) or 0))
        d += (int(m.get("yn_votes", 0) or 0) - int(p.get("yn_votes", 0) or 0))
        if d > 0:
            movers.append((m, d))
    movers.sort(key=lambda x: -x[1])
    note = "biggest vote growth since previous snapshot (proxy for 'actively played/rated')"
    return [(m, d) for m, d in movers[:n]], note


def rating_histogram(maps, key):
    buckets = {i / 2: 0 for i in range(11)}
    for m in maps:
        v = m.get(key, 0) or 0
        if v <= 0:
            continue
        b = round(v * 2) / 2
        b = min(5.0, max(0.0, b))
        buckets[b] += 1
    return buckets


def count_by(maps, key):
    counts = {}
    for m in maps:
        v = m.get(key, "") or "Unknown"
        counts[v] = counts.get(v, 0) + 1
    return counts


def trend_movers(snapshots):
    if len(snapshots) < 2:
        return [], []
    first = {m["uid"]: m for m in snapshots[0]["maps"]}
    last = {m["uid"]: m for m in snapshots[-1]["maps"]}
    improved, declined = [], []
    for uid, lm in last.items():
        fm = first.get(uid)
        if not fm:
            continue
        d = ((lm.get("stars_avg", 0) or 0) - (fm.get("stars_avg", 0) or 0)) + \
            ((lm.get("yn_rating", 0) or 0) - (fm.get("yn_rating", 0) or 0)) * 0.5
        if abs(d) < 0.1:
            continue
        improved.append(({"name": lm["name"], "delta": d,
                           "prev_st": fm.get("stars_avg", 0), "curr_st": lm.get("stars_avg", 0),
                           "prev_yn": fm.get("yn_rating", 0), "curr_yn": lm.get("yn_rating", 0)}, d)) \
            if d > 0 else declined.append(({"name": lm["name"], "delta": d,
                           "prev_st": fm.get("stars_avg", 0), "curr_st": lm.get("stars_avg", 0),
                           "prev_yn": fm.get("yn_rating", 0), "curr_yn": lm.get("yn_rating", 0)}, d))
    improved.sort(key=lambda x: -x[1])
    declined.sort(key=lambda x: x[1])
    return [e for e, _ in improved], [e for e, _ in declined]


def build_report(cadence, do_snapshot=True):
    dt = now_utc()
    phase = moon_phase_name(dt)
    maps = fetch_sheet_maps()
    if not maps:
        # fall back to curated cache
        if CURATED.exists():
            maps = json.load(open(CURATED, encoding="utf-8"))
        if not maps:
            print("ERROR: cannot fetch sheet and no cache", file=sys.stderr)
            sys.exit(1)
    snaps = load_history()
    if do_snapshot:
        ns = append_snapshot(maps)
    else:
        ns = len(snaps)

    total_yn_votes = sum(int(m.get("yn_votes", 0) or 0) for m in maps)
    total_star_votes = sum(int(m.get("stars_total", 0) or 0) for m in maps)
    rated = [m for m in maps if (m.get("stars_avg", 0) or 0) > 0]
    avg_star = (sum(m["stars_avg"] for m in rated) / len(rated)) if rated else 0
    rated_yn = [m for m in maps if (m.get("yn_rating", 0) or 0) > 0]
    avg_yn = (sum(m["yn_rating"] for m in rated_yn) / len(rated_yn)) if rated_yn else 0

    cadence_word = "Weekly" if cadence == "weekly" else "Monthly"
    L = []
    L.append(f"# 🌙 {cadence_word} Pursuit Maps Report — {dt.strftime('%Y-%m-%d')}")
    L.append("")
    L.append(f"_Generated {dt.strftime('%Y-%m-%d %H:%M UTC')} · Moon phase: **{phase}** · "
             f"Reports every 4 moon phases (~weekly)_")
    L.append("")

    # ── Summary ──
    L.append("## 📊 Snapshot")
    L.append("")
    L.append(f"- Total maps tracked: **{len(maps)}**")
    L.append(f"- Maps with a 5-Star rating: **{len(rated)}**")
    L.append(f"- Maps with a YES/NO rating: **{len(rated_yn)}**")
    L.append(f"- Total YES/NO votes cast: **{total_yn_votes:,}**")
    L.append(f"- Total 5-Star votes cast: **{total_star_votes:,}**")
    L.append(f"- Average 5-Star rating: **{avg_star:.2f}/5**")
    L.append(f"- Average YES/NO rating: **{avg_yn:.2f}/5**")
    L.append(f"- Vote-history snapshots on file: **{ns}**")
    L.append("")

    # ── Best maps ──
    L.append("## 🏆 Best Maps (by 5-Star, min. " + str(MIN_VOTES) + " votes)")
    L.append("")
    L.append("| # | Map | 5★ Avg | Votes | YN |")
    L.append("|---|-----|--------|-------|----|")
    for i, m in enumerate(top_by_stars(maps), 1):
        L.append(f"| {i} | {m['name'][:48]} | {fmt_r(m.get('stars_avg'))} | "
                 f"{int(m.get('stars_total',0) or 0)} | {fmt_r(m.get('yn_rating'))} |")
    L.append("")

    L.append("## 🔥 Most Popular (by 5-Star vote count)")
    L.append("")
    L.append("| # | Map | 5★ Votes | 5★ Avg |")
    L.append("|---|-----|----------|--------|")
    for i, m in enumerate(most_voted(maps), 1):
        L.append(f"| {i} | {m['name'][:48]} | {int(m.get('stars_total',0) or 0)} | "
                 f"{fmt_r(m.get('stars_avg'))} |")
    L.append("")

    L.append("## ✅ Community Favourites (by YES/NO, min. " + str(MIN_VOTES) + " votes)")
    L.append("")
    tbyn = top_by_yn(maps)
    if tbyn:
        L.append("| # | Map | YN Rating | YN Votes |")
        L.append("|---|-----|-----------|----------|")
        for i, m in enumerate(tbyn, 1):
            L.append(f"| {i} | {m['name'][:48]} | {fmt_r(m.get('yn_rating'))} | "
                     f"{int(m.get('yn_votes',0) or 0)} |")
    else:
        L.append("_No maps have enough YES/NO votes yet._")
    L.append("")

    # ── How maps are being rated / played right now ──
    L.append("## 🎮 How Maps Are Being Rated Right Now")
    L.append("")
    L.append("_We don't have raw play logs, so 'commonly played' is inferred from "
             "vote activity: maps whose vote counts grow fastest between snapshots "
             "are the ones people are actively choosing and rating._")
    L.append("")
    prev_snap = snaps[-2]["maps"] if len(snaps) >= 2 else None
    active, note = most_active(maps, prev_snap)
    L.append(f"**{note}**")
    L.append("")
    if active:
        L.append("| # | Map | 5★ Total | YN Votes | Recent vote growth |")
        L.append("|---|-----|----------|----------|--------------------|")
        for i, (m, d) in enumerate(active, 1):
            L.append(f"| {i} | {m['name'][:44]} | {int(m.get('stars_total',0) or 0)} | "
                     f"{int(m.get('yn_votes',0) or 0)} | +{d} |")
    else:
        L.append("_No vote growth detected yet between snapshots. This section "
                 "fills in once history accumulates._")
    L.append("")

    # ── Distributions with charts ──
    L.append("## 🌍 Maps by Environment")
    L.append("")
    env_counts = dict(sorted(count_by(maps, "env").items(), key=lambda x: -x[1]))
    mx = max(env_counts.values()) if env_counts else 0
    for k, v in env_counts.items():
        L.append(ascii_bar(v, mx, label=k or "Unknown"))
    L.append("")

    L.append("## 🎯 Maps by Mode (MapType)")
    L.append("")
    mt = {k.replace("TrackMania\\", ""): v
          for k, v in count_by(maps, "maptype").items()}
    mt_counts = dict(sorted(mt.items(), key=lambda x: -x[1]))
    mx = max(mt_counts.values()) if mt_counts else 0
    for k, v in mt_counts.items():
        L.append(ascii_bar(v, mx, label=k or "Unknown"))
    L.append("")

    L.append("## 👤 Top Authors (by map count, top 12)")
    L.append("")
    auth_counts = dict(sorted(count_by(maps, "author").items(),
                              key=lambda x: -x[1])[:12])
    mx = max(auth_counts.values()) if auth_counts else 0
    for k, v in auth_counts.items():
        L.append(ascii_bar(v, mx, label=k or "Unknown"))
    L.append("")

    L.append("## ⭐ 5-Star Rating Distribution")
    L.append("")
    hist = rating_histogram(maps, "stars_avg")
    mx = max(hist.values()) if hist else 0
    for k in sorted(hist):
        L.append(ascii_bar(hist[k], mx, label=f"{k:.1f}"))
    L.append("")

    # ── Time trend ──
    L.append("## 📈 How Ratings Changed Over Time")
    L.append("")
    if len(snaps) >= 2:
        L.append(f"_Comparing first snapshot ({snaps[0].get('timestamp','?')}) "
                 f"with latest ({snaps[-1].get('timestamp','?')})._")
        L.append("")
        improved, declined = trend_movers(snaps)
        if improved:
            L.append("**▲ Most improved**")
            L.append("")
            L.append("| # | Map | 5★ before→after | YN before→after |")
            L.append("|---|-----|-----------------|-----------------|")
            for i, e in enumerate(improved[:10], 1):
                L.append(f"| {i} | {e['name'][:44]} | {fmt_r(e['prev_st'])}→{fmt_r(e['curr_st'])} | "
                         f"{fmt_r(e['prev_yn'])}→{fmt_r(e['curr_yn'])} |")
            L.append("")
        if declined:
            L.append("**▼ Most declined**")
            L.append("")
            L.append("| # | Map | 5★ before→after | YN before→after |")
            L.append("|---|-----|-----------------|-----------------|")
            for i, e in enumerate(declined[:10], 1):
                L.append(f"| {i} | {e['name'][:44]} | {fmt_r(e['prev_st'])}→{fmt_r(e['curr_st'])} | "
                         f"{fmt_r(e['prev_yn'])}→{fmt_r(e['curr_yn'])} |")
            L.append("")
        if not improved and not declined:
            L.append("_No significant rating changes between snapshots yet._")
            L.append("")
    else:
        L.append(f"_Time-series not available yet — only **{ns}** snapshot(s) on file "
                 f"(this run just created one)._")
        L.append("Each periodic run appends a snapshot, so this section populates "
                 "automatically as history builds up (a few weeks of runs).")
        L.append("")

    # ── New maps since last periodic report ──
    L.append("## 🆕 New Since Last Report")
    L.append("")
    current_uids = {m["uid"] for m in maps}
    prev = {}
    if LAST_REPORT_PATH.exists():
        try:
            prev = json.load(open(LAST_REPORT_PATH, encoding="utf-8"))
        except Exception:
            prev = {}
    prev_uids = set(prev.get("uids", []))
    new_uids = current_uids - prev_uids
    if prev_uids and new_uids:
        L.append(f"**{len(new_uids)}** map(s) added since the last periodic report "
                 f"({prev.get('date', '?')}):")
        L.append("")
        L.append("| # | Map | Author | Env | 5★ Avg |")
        L.append("|---|-----|--------|-----|--------|")
        for i, uid in enumerate(sorted(new_uids), 1):
            m = next((x for x in maps if x["uid"] == uid), None)
            if not m:
                continue
            L.append(f"| {i} | {m['name'][:44]} | {m.get('author','') or '—'} | "
                     f"{m.get('env','') or '—'} | {fmt_r(m.get('stars_avg'))} |")
        L.append("")
    elif not prev_uids:
        L.append("_This is the first periodic report, so all tracked maps form the "
                 "baseline for future 'new maps' comparisons._")
        L.append("")
    else:
        L.append("_No new maps since the previous periodic report._")
        L.append("")

    report = "\n".join(L)

    # Persist state
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    dated = REPORTS_DIR / f"{dt.strftime('%Y-%m-%d')}.md"
    dated.write_text(report, encoding="utf-8")
    LATEST_PATH.write_text(report, encoding="utf-8")
    json.dump({"ts": dt.timestamp(), "date": dt.strftime("%Y-%m-%d"),
               "cadence": cadence, "phase": phase},
              open(LAST_RUN_PATH, "w", encoding="utf-8"), indent=2)
    json.dump({"date": dt.strftime("%Y-%m-%d"), "uids": sorted(current_uids)},
              open(LAST_REPORT_PATH, "w", encoding="utf-8"), indent=2)
    return report, dated


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Pursuit Maps periodic report")
    ap.add_argument("--cadence", choices=["weekly", "monthly"], default="weekly")
    ap.add_argument("--auto", action="store_true",
                    help="Only generate if enough time passed since last run")
    ap.add_argument("--force", action="store_true", help="Ignore due-check")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="Don't append to vote_history.json")
    args = ap.parse_args()

    if args.auto and not args.force and not is_due(args.cadence):
        print("Periodic report not due yet (cadence=%s). Skipping." % args.cadence)
        return 0

    report, path = build_report(args.cadence, do_snapshot=not args.no_snapshot)
    print(f"Report written: {path}")
    print(f"Length: {len(report)} chars, {report.count(chr(10))+1} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
