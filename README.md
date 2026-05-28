# Pursuit Maps - TrackMania ManiaPlanet Feedback S1 E1

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Complete dataset of 249 maps from **TrackMania² Pursuit Multi-environment (Season 1 Episode 1 by Dommy)** sourced from ManiaPlanet Feedback.

## What's Included

| Content | Count | Description |
|---------|-------|-------------|
| Thumbnails | 248 JPG files | Map preview images (~43-60KB each) |
| CSV Data | 2 files | Full map metadata with UIDs, names, authors, URLs |
| Scripts | Python + JS | Extraction and download automation |
| Google Sheets | 125 rows | "Pursuit Channels New" tab from public sheet |

## Quick Start

### CSV Data

```bash
# Full dataset with UIDs and all URLs
cat data/maniaplanet_feedback_106_with_uid.csv | head -5

# Columns: Lp, UID, Map name, Hash, Thumbnail URL, Map URL (tm.mania.exchange), Author URL, Feedback URL
```

### Thumbnails

```bash
# Each thumbnail named by UID
ls assets/thumbnails/ | head -10
# o7dl56rYEVeuNyLkvJgjgkvRIIj.jpg
# owfIKm3fjLoU7GL_cRqLsS9noD6.jpg
# ...
```

### Fetch a thumbnail by UID

```bash
# Direct URL (hash varies per map - see CSV for exact URL)
curl -o map.jpg "https://files-v4.live.maniaplanet.com/maps/{hash}/{UID}.jpg"
```

## Map URL Patterns

| Platform | URL Pattern |
|----------|-------------|
| Thumbnail | `https://files-v4.live.maniaplanet.com/maps/{hash}/{UID}.jpg` |
| ManiaExchange Map | `https://tm.mania.exchange/mapsearch?query={encoded_name}` |
| ManiaExchange Author | `https://tm.mania.exchange/usersearch?query={author}` |
| ManiaPlanet Feedback | `https://feedback.prod.live.maniaplanet.com/votes/display/106` |
| Google Sheets | `https://docs.google.com/spreadsheets/d/1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ/edit#gid=763170857` |

## Data Sources

1. **ManiaPlanet Feedback** - `https://feedback.prod.live.maniaplanet.com/votes/display/106`
   - Season 1 Episode 1 by Dommy
   - 249 maps with thumbnails, YES/NO votes, 5-star ratings
   - UID extracted from `<img src>` via JavaScript DOM

2. **Google Sheets (Public)** - "Pursuit Channels New" tab (GID 763170857)
   - 125 maps with metadata: #, Map name, Author, Environment, Uploaded at, UID, MapType, Notes
   - Read via Google gviz API (no auth required for public sheets)

3. **tm.mania.exchange** - Map and author links verified working
   - `https://tm.mania.exchange/mapshow/{ID}` for direct map pages
   - `https://tm.mania.exchange/usershow/{ID}` for author profiles

## Scripts

### Extract UIDs from Feedback Page (JavaScript)

Run in browser console on `https://feedback.prod.live.maniaplanet.com/votes/display/106`:

```javascript
(() => {
  const imgs = document.querySelectorAll('img');
  const maps = [];
  const h6s = document.querySelectorAll('h6');
  const names = [];
  h6s.forEach(h => {
    const t = h.textContent.trim();
    if (t && t !== 'YES/NO' && t !== '5 STARS') names.push(t);
  });
  imgs.forEach((img, i) => {
    const src = img.src || '';
    const m = src.match(/\/maps\/([a-f0-9]+)\/([a-zA-Z0-9_\-]+)\.(jpg|png)/);
    if (m) maps.push({ hash: m[1], uid: m[2], name: names[i] || '' });
  });
  return JSON.stringify(maps);
})()
```

### Download Thumbnails (Python)

```python
import urllib.request, os

maps = [("hash1", "uid1"), ("hash2", "uid2")]  # from extraction
headers = {'User-Agent': 'Mozilla/5.0'}
for hash_val, uid in maps:
    url = f"https://files-v4.live.maniaplanet.com/maps/{hash_val}/{uid}.jpg"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        with open(f"thumbnails/{uid}.jpg", 'wb') as f:
            f.write(resp.read())
```

### Read Google Sheets via gviz API (Python)

```python
import urllib.request, json

url = "https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?gid={GID}&tqx=out:json&headers=1"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=15)
raw = resp.read().decode('utf-8')
json_str = raw.split('(', 1)[1].rsplit(');', 1)[0]
data = json.loads(json_str)
for row in data['table']['rows']:
    cells = row['c']
    num = cells[0].get('v', '')
    name = cells[1].get('v', '')
    author = cells[2].get('v', '')
    uid = cells[5].get('v', '')
    print(f"{num}: {name} by {author} (UID: {uid})")
```

## Map Types

| Type | Count (approx) |
|------|---------------|
| TrackMania\PursuitArena | ~80% |
| TrackMania\GoalHuntArena | ~15% |
| TrackMania\HuntersArena | ~5% |

## Environments

Valley, Canyon, Stadium, Lagoon

## Notable Findings

- Google Sheets row 126 has empty Column B → filled with `[Pursuit] - Third Contribution` from feedback data
- 2 maps marked "missing link" in Sheets: "Pursuit - Surrounded", "Pursuit - Volley"
- 12 maps with notes (incorrect OffZone, black thumbnail, outdated mode, etc.)
- Last-Modified for all thumbnails: 2024-02-12 (batch upload date)
- 1 thumbnail unavailable (HTTP 403): Liminal Maze Tower by piotrunio

## Legal

Map data and thumbnails belong to their respective authors and Nadeo/ManiaPlanet. This dataset is for research and educational purposes.

## License

MIT License - see [LICENSE](LICENSE)
