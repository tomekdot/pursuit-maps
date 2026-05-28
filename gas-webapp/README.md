# GAS Web App Setup (jednorazowo)

## Krok 1: Deploy Google Apps Script
1. Otwórz Sheet: https://docs.google.com/spreadsheets/d/1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ/edit#gid=763170857
2. Extensions (Rozszerzenia) → Apps Script
3. Usun wszystko z edytora i wklej zawartosc `PursuitMaps.gs`
4. Zapisz (Ctrl+S) - nazwij projekt "Pursuit Maps Sync"
5. Kliknij **Deploy** → **New deployment**
6. Ikona uzupelnienia (gear) → **Web app**
7. Ustawienia:
   - Description: `Pursuit Maps Sync`
   - Execute as: **Me** (Twoje konto)
   - Who has access: **Anyone** (lub bez dla bezpieczenstwa)
8. Kliknij **Deploy**
9. Zezwól na uprawnienia (Authorize)
10. Skopiuj **Web app URL** (wyglada jak `https://script.google.com/macros/s/AX.../exec`)
11. Wklej URL do pliku `gas_url.txt` w tym folderze

## Krok 2: Test
```bash
cd gas-webapp
python3 gas_runner.py --test
python3 gas_runner.py --setup      # dodaj nagłówki kolumn I-L
python3 gas_runner.py --dry-run    # podgląd
python3 gas_runner.py              # pełny sync
```

## Krok 3: GitHub Actions
1. Wejdź na repo → Settings → Secrets → Actions
2. Dodaj secret: `GAS_WEBAPP_URL` = URL z kroku 1
3. GitHub Actions uruchomi się automatycznie o 5:00 UTC

## Użycie ręczne
```bash
# Tylko sync (dodaj nowe mapy, uzupełnij puste)
python3 gas_runner.py --action sync

# Tylko głosy (zaktualizuj kolumny I-L)
python3 gas_runner.py --action votes

# Wszystko
python3 gas_runner.py

# Podgląd bez zapisu
python3 gas_runner.py --dry-run
```
