---
name: pursuit-maps
description: "TrackMania Pursuit maps pipeline: fetches 249 maps from ManiaPlanet Feedback (star ratings, vote counts), enriches with ManiaExchange data (author, environment, map type), and syncs everything to Google Sheets via GAS Web App. Daily automated pipeline with vote change tracking."
version: 2.0.0
author: OWL
tags: ["trackmania", "pursuit", "maniaplanet", "maps", "thumbnails", "gas", "google-sheets", "pipeline"]
---

# Pursuit Maps Pipeline

Automated pipeline that collects map data from ManiaPlanet Feedback + ManiaExchange
and syncs it to Google Sheets. Runs via GitHub Actions daily at 5:00 UTC.

## What It Does

1. **Fetches 249 maps** from ManiaPlanet Feedback with:
   - YES/NO Rating (e.g. 3.5/5) + vote count
   - 5-Star Average (e.g. 4.2/5) + total votes
   - Map name, UID, thumbnail hash

2. **Enriches with ManiaExchange API** for:
   - Author login
   - Environment (Valley, Canyon, Stadium, Lagoon)
   - MapType (TrackMania\PursuitArena, TrackMania\GoalHuntArena, etc.)

3. **Compares with Google Sheets** and pushes only new/changed data via GAS Web App

4. **Tracks vote changes** daily: which maps rose, fell, or are new

## Repo Structure

```
pursuit-maps/
├── pipeline/
│   ├── pipeline.py             # Main script: sync + votes + report + validate
│   ├── gas_runner.py           # HTTP client for GAS Web App
│   ├── all_maps.tsv            # All 249 maps with votes (for manual paste)
│   └── gas-webapp/
│       ├── PursuitMaps.gs      # Deploy once in Sheet (Extensions → Apps Script)
│       └── README.md           # GAS setup guide
├── data/
│   ├── feedback_full.json      # Cached feedback data (249 maps)
│   ├── vote_history.json       # Vote snapshots (90 days)
│   └── vote_report.md          # Generated vote change report
├── docs/
│   ├── GOOGLE_SHEETS_SETUP.md
│   └── SHEETS_WRITE_SETUP.md
├── scripts/legacy/             # Old scripts (reference only)
├── assets/thumbnails/          # 248 map thumbnail JPGs
└── .github/workflows/
    └── pipeline.yml            # Daily cron 5:00 UTC
```

## Usage

```bash
# Full pipeline
python3 pipeline/pipeline.py

# Individual actions
python3 pipeline/pipeline.py --action sync      # Fetch + push new maps
python3 pipeline/pipeline.py --action votes     # Update vote columns
python3 pipeline/pipeline.py --action report    # Generate vote change report
python3 pipeline/pipeline.py --action validate  # Data quality checks
```

Requires `GAS_WEBAPP_URL` env var or `pipeline/gas_url.txt` with the GAS Web App URL.

## Data Sources

- **ManiaPlanet Feedback**: https://feedback.prod.live.maniaplanet.com/votes/display/106
  - Season 1 Episode 1 by Dommy
  - 249 maps with YES/NO votes, 5-star ratings
  - HTML parsing: two separate `<span style="color: gold">` sections per card

- **ManiaExchange API**: `https://tm.mania.exchange/api/maps/get_map_info/id/{UID}`
  - Returns: TrackID, AuthorLogin, MapType, EnvironmentName, TitlePack, etc.
  - V1 endpoint accepts UID directly (not just TrackID)
  - ~75% of Pursuit maps are indexed on MX

- **Google Sheets (read)**: gviz API, no auth needed for public sheets
  - Sheet ID: `1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ`
  - GID: `763170857` ("Pursuit Channels New" tab)

- **Google Sheets (write)**: via GAS Web App
  - Deploy `pipeline/gas-webapp/PursuitMaps.gs` once
  - Accepts HTTP POST with JSON payload
  - Executes as your account, no user interaction needed

## Sheet Columns

| Col | Name | Source |
|-----|------|--------|
| A | # | Auto-number |
| B | Map name | Feedback page |
| C | Author login | ManiaExchange |
| D | Environment | ManiaExchange |
| E | Uploaded at | ManiaExchange |
| F | UID | Feedback page |
| G | MapType | ManiaExchange |
| H | Notes | Manual |
| I | YN Rating | Feedback YES/NO section |
| J | YN Votes | Feedback YES/NO section |
| K | 5-Star Avg | Feedback 5 STARS section |
| L | 5-Star Total | Feedback 5 STARS section |

## Key Parsing Details

The Feed page has TWO separate star rating sections per map card:

1. **YES/NO section**: `<h6>YES/NO</h6>` followed by `<span style="color: gold">` with stars and `rating (count)` text
2. **5 STARS section**: `<h6>5 STARS</h6>` followed by similar gold span

These must be parsed independently — they produce different values:
- YES/NO rating reflects binary yes/no voting
- 5-Star rating reflects star-based quality rating
- ~80% of maps have 5-Star data but no YES/NO votes yet

The parser splits the HTML at each `<img src="...maps/...">` tag to isolate per-map sections, then uses regex to extract `rating (count)` from each gold span.

## URL Patterns

| Platform | Pattern |
|----------|---------|
| Thumbnail | `https://files-v4.live.maniaplanet.com/maps/{hash}/{UID}.jpg` |
| Feedback | `https://feedback.prod.live.maniaplanet.com/votes/display/106` |
| MX Map | `https://tm.mania.exchange/mapsearch?query={name}` |
| MX API | `https://tm.mania.exchange/api/maps/get_map_info/id/{UID}` |
| Sheet gviz | `https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?gid={GID}&tqx=out:json&headers=1` |

## Notable Findings

- 1 thumbnail unavailable (HTTP 403): Liminal Maze Tower by piotrunio
- GHC2 season (Goal Hunt Christmas 2) maps have UID and Name but no Author/Env/Type on MX
- MapType values from MX include backslash prefix: `TrackMania\PursuitArena`
- Sheet row 125 originally had empty Column B — filled with `[Pursuit] - Third Contribution` from feedback

## Legal

Map data and thumbnails belong to their respective authors and Nadeo/ManiaPlanet. This dataset is for research and educational purposes.

## License

MIT
