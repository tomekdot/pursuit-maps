# 🏎️ Pursuit Maps Pipeline

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Pipeline that fetches map data from ManiaPlanet Feedback + ManiaExchange
and syncs it to Google Sheets.

## 🗂️ Structure

```
pursuit-maps/
├── pipeline/           ← 🚀 Main entry point
│   ├── pipeline.py     ← 🔧 Single script: sync + votes + report + validate
│   ├── gas_runner.py   ← 📡 Send data to GAS Web App
│   ├── all_maps.tsv    ← 📄 All 249 maps with vote data
│   └── gas-webapp/
│       ├── PursuitMaps.gs  ← ⚡ Deploy once in Sheet
│       └── README.md       ← 📖 GAS setup guide
├── data/               ← 💾 Data files
│   ├── feedback_full.json  ← Cached feedback
│   ├── vote_history.json   ← Vote snapshots
│   └── vote_report.md      ← Generated reports
├── docs/               ← 📖 Setup guides
├── scripts/legacy/     ← 📁 Old scripts (reference only)
├── assets/thumbnails/  ← 🖼️ 248 map thumbnails
└── .github/workflows/
    └── pipeline.yml    ← ⏰ Daily 5:00 UTC auto-sync
```

## 🚀 Quick Start

```bash
python3 pipeline/pipeline.py --action validate  # Validate data quality
python3 pipeline/pipeline.py                     # Full pipeline (sync + votes + report)
python3 pipeline/pipeline.py --action sync       # Sync new maps only
python3 pipeline/pipeline.py --action votes      # Update votes only
python3 pipeline/pipeline.py --action report     # Generate report only
```

## ⚡ GAS Setup (one-time)

1. Open Sheet → Extensions → Apps Script
2. Paste `pipeline/gas-webapp/PursuitMaps.gs`
3. Deploy → New deployment → Web app
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Save the Web App URL as:
   - Local: `pipeline/gas_url.txt`
   - GitHub: Secret `GAS_WEBAPP_URL`

## 📄 License

MIT — see [LICENSE](LICENSE)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## 🔒 Security

See [SECURITY.md](SECURITY.md)
