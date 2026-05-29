# 🏎️ Pursuit Maps Pipeline

**Automatyczny pipeline** który śledzi mapy z [ManiaPlanet Feedback (strona 106)](https://feedback.prod.live.maniaplanet.com/votes/display/106) i synchronizuje je z Google Sheets.

**Główny cel**: kiedy nowa mapa pojawi się na stronie feedback — automatycznie dodana do Sheets, bez ręcznej pracy.

## ✨ Co robi

- 🔍 **Wykrywanie nowych map** — porównuje feedback z Sheets, znajduje brakujące
- 📥 **Automatyczne dodawanie** — nowe mapy wypychane do Sheets przez GAS Web App
- 📊 **Aktualizacja ocen** — YES/NO rating, 5-Star avg, vote counts — codziennie odświeżane
- 📈 **Raport zmian** — co się zmieniło w głosach, które mapy wzrosły/spadły
- 🕐 **Pełna automatyzacja** — GitHub Actions o 5:00 UTC (3:00 w nocy), zero ręcznej pracy
- 📅 **Sortowanie po dacie** — najnowsze mapy automatycznie na górze

## 🗂️ Struktura

```
pursuit-maps/
├── pipeline/                    # 🚀 Główny skrypt
│   ├── pipeline.py              # 🔧 sync + votes + report + validate + missing
│   ├── gas_runner.py            # 📡 Klient GAS Web App
│   └── gas-webapp/
│       ├── PursuitMaps.gs       # ⚡ Deploy raz w Sheet (Apps Script)
│       └── README.md            # 📖 Instalacja GAS
├── data/                        # 💾 Cache i historia
│   ├── feedback_full.json       # Cache feedback (249 map)
│   ├── vote_history.json        # Historia głosów
│   ├── missing_maps.json        # Raport brakujących map
│   └── vote_report.md           # Raport zmian
├── docs/                        # 📖 Dokumentacja
├── assets/thumbnails/           # 🖼️ 248 miniaturek map
└── .github/workflows/
    └── pipeline.yml             # ⏰ Cron: codziennie 5:00 UTC
```

## 🚀 Użycie

```bash
python3 pipeline/pipeline.py                     # Pełny pipeline (sync + votes + report)
python3 pipeline/pipeline.py --action sync       # Dodaj nowe mapy + aktualizuj oceny
python3 pipeline/pipeline.py --action votes      # Tylko aktualizacja głosów
python3 pipeline/pipeline.py --action report     # Raport zmian głosów
python3 pipeline/pipeline.py --action missing    # Raport brakujących map
python3 pipeline/pipeline.py --action validate   # Sprawdzenie jakości danych
```

## ⚡ Setup GAS (raz)

1. Otwórz Sheet → Extensions → Apps Script
2. Wklej `pipeline/gas-webapp/PursuitMaps.gs`
3. Deploy → New deployment → Web app
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Zapisz URL Web App:
   - Lokalnie: `pipeline/gas_url.txt`
   - GitHub: Secret `GAS_WEBAPP_URL`

## 📋 Kolumny Sheet

| Kolumna | Nazwa | Źródło |
|---------|-------|--------|
| A | # | Auto-numeracja |
| B | Map name | Feedback |
| C | Author login | ManiaExchange |
| D | Environment | ManiaExchange |
| E | Uploaded at | ManiaExchange (sortowane malejąco) |
| F | UID | Feedback |
| G | MapType | ManiaExchange |
| H | Notes | Ręczne |
| I | YN Rating | Feedback YES/NO |
| J | YN Votes | Feedback YES/NO |
| K | 5-Star Avg | Feedback 5 STARS |
| L | 5-Star Total | Feedback 5 STARS |

## 📄 Licencja

MIT — zobacz [LICENSE](LICENSE)

## 🤝 Contributing

Zobacz [CONTRIBUTING.md](CONTRIBUTING.md)

## 🔒 Security

Zobacz [SECURITY.md](SECURITY.md)
