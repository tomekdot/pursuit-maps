# Pursuit Maps - TrackMania ManiaPlanet

Pipeline that fetches map data from ManiaPlanet Feedback + ManiaExchange
and syncs it to Google Sheets.

## Structure

```
pursuit-maps/
├── pipeline/           ← Main entry point
│   ├── pipeline.py     ← Single script: sync + votes + report
│   ├── gas_runner.py   ← Send data to GAS Web App
│   ├── all_maps.tsv    ← All 249 maps with vote data
│   ├── gas_sync_payload.json  ← GAS sync payload
│   └── gas-webapp/
│       ├── PursuitMaps.gs     ← Deploy once in Sheet
│       └── README.md          ← GAS setup guide
├── data/               ← Data files
│   ├── feedback_full.json    ← Feedback fetch cache
│   ├── vote_history.json     ← Vote tracking snapshots
│   ├── vote_report.md        ← Generated vote report
│   └── ...
├── docs/               ← Setup guides
├── scripts/legacy/     ← Old scripts (reference only)
├── assets/thumbnails/  ← 248 map thumbnails
└── .github/workflows/  ← GitHub Actions
    └── pipeline.yml    ← Daily 5:00 UTC auto-sync
```

## Quick Start

```bash
# Validate data quality
python3 pipeline/pipeline.py --action validate

# Full pipeline (sync + votes + report)
python3 pipeline/pipeline.py

# Just sync new maps
python3 pipeline/pipeline.py --action sync

# Just update votes
python3 pipeline/pipeline.py --action votes

# Just generate report
python3 pipeline/pipeline.py --action report
```

## GAS Setup (one-time)

1. Open Sheet → Extensions → Apps Script
2. Paste `pipeline/gas-webapp/PursuitMaps.gs`
3. Deploy → New deployment → Web app
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Save the Web App URL as:
   - Local: `pipeline/gas_url.txt`
   - GitHub: Secret `GAS_WEBAPP_URL`
