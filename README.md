# 🏎️ Pursuit Maps Pipeline

**Automated pipeline** that tracks maps from [ManiaPlanet Feedback (page 106)](https://feedback.prod.live.maniaplanet.com/votes/display/106) and syncs them to Google Sheets.

**Main goal**: when a new map appears on feedback — it's automatically added to Sheets, no manual work.

## ✨ What it does

- 🔍 **New map detection** — compares feedback with Sheets, finds missing maps
- 📥 **Auto-add** — new maps pushed to Sheets via GAS Web App
- 📊 **Vote tracking** — YES/NO rating, 5-Star avg, vote counts — refreshed daily
- 📈 **Change reports** — what changed in votes, which maps rose/fell
- 🌙 **Periodic community reports** — weekly (~every 4 moon phases) digest: best/popular/most-improved maps, how ratings shift over time, which maps are being actively rated ("commonly played" proxy via vote growth), plus environment/mode/author breakdowns with ASCII charts
- 🕐 **Full automation** — GitHub Actions at 5:00 UTC daily, zero manual work
- 📅 **Sequential numbering** — column A renumbered after each sync, new maps appended at end

## 🗂️ Structure

```
pursuit-maps/
├── pipeline/                    # 🚀 Main script
│   ├── pipeline.py              # 🔧 sync + votes + report + validate + missing
│   ├── gas_runner.py            # 📡 GAS Web App client
│   └── gas-webapp/
│       ├── PursuitMaps.gs       # ⚡ Deploy once in Sheet (Apps Script)
│       └── README.md            # 📖 GAS setup guide
├── data/                        # 💾 Cache and history
│   ├── feedback_full.json       # Feedback cache (253 maps)
│   ├── feedback_full_json       # Pipeline feedback cache (no dot)
│   ├── vote_history.json        # Vote snapshots (time-series for trends)
│   ├── missing_maps.json        # Missing maps report
│   └── vote_report.md           # Change report
├── reports/                     # 🌙 Periodic community reports
│   ├── periodic/                # Dated reports (YYYY-MM-DD.md)
│   └── latest_periodic.md       # Always the newest report
├── docs/                        # 📖 Documentation
├── assets/thumbnails/           # 🖼️ 248 map thumbnails
└── .github/workflows/
    └── pipeline.yml             # ⏰ Cron: daily 5:00 UTC
```

## 🚀 Usage

```bash
python3 pipeline/pipeline.py                     # Full pipeline (sync + votes + report)
python3 pipeline/pipeline.py --action sync       # Add new maps + update votes
python3 pipeline/pipeline.py --action votes      # Update votes only
python3 pipeline/pipeline.py --action report     # Generate vote change report
python3 pipeline/pipeline.py --action missing    # Report missing maps
python3 pipeline/pipeline.py --action validate   # Data quality checks
python3 pipeline/periodic_report.py --cadence weekly   # Generate weekly community report
python3 pipeline/periodic_report.py --auto             # Only if due (use in CI)
```

## ⚡ GAS Setup (once)

1. Open Sheet → Extensions → Apps Script
2. Paste `pipeline/gas-webapp/PursuitMaps.gs`
3. Deploy → New deployment → Web app
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Save the Web App URL:
   - Local: `pipeline/gas_url.txt`
   - GitHub: Secret `GAS_WEBAPP_URL`

## 📋 Sheet Columns

| Column | Name | Source |
|--------|------|--------|
| A | # | Auto-numbering |
| B | Map name | Feedback |
| C | Author login | ManiaExchange |
| D | Environment | ManiaExchange |
| E | Uploaded at | ManiaExchange |
| F | UID | Feedback |
| G | MapType | ManiaExchange |
| H | Notes | Manual |
| I | YN Rating | Feedback YES/NO |
| J | YN Votes | Feedback YES/NO |
| K | 5-Star Avg | Feedback 5 STARS |
| L | 5-Star Total | Feedback 5 STARS |

## 📄 License

MIT — see [LICENSE](LICENSE)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## 🔒 Security

See [SECURITY.md](SECURITY.md)
