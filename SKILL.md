---
name: pursuit-maps
description: "TrackMania Pursuit maps from ManiaPlanet Feedback display/106 - Season 1 Episode 1 by Dommy. 248 map thumbnails with UIDs."
version: 1.0.0
author: OWL
tags: ["trackmania", "pursuit", "maniaplanet", "maps", "thumbnails"]
---

# Pursuit Maps - ManiaPlanet Feedback S1 E1

Thumbnails and UID data for 249 maps from ManiaPlanet Feedback display/106 (TrackMania² Pursuit Multi-environment Season 1 Episode 1 by Dommy).

## Folder Structure

```
pursuit-maps/
├── SKILL.md
└── assets/
    └── thumbnails/
        └── {UID}.jpg   (248 files, one per map)
```

## Data Sources

- **Feedback page**: https://feedback.prod.live.maniaplanet.com/votes/display/106
- **Google Sheets**: https://docs.google.com/spreadsheets/d/1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ/edit#gid=763170857

## File Naming Convention

Each thumbnail is named `{UID}.jpg` where UID is the unique ManiaPlanet map identifier.

Example: `pdHcfgrPuzYKYG84amT6KREpj97.jpg` → `[Pursuit] - Third Contribution`

## Map URL Patterns

- Thumbnail: `https://files-v4.live.maniaplanet.com/maps/{hash}/{UID}.jpg`
- Feedback: `https://feedback.prod.live.maniaplanet.com/votes/display/106`

Note: The `{hash}` in the thumbnail URL varies per map and is NOT the same as the UID. The UID is unique per map.

## Missing File

1 file could not be downloaded (HTTP 403):
- `xmPnj0qC1jmfw64X53VjWNXfpj.jpg` (Liminal Maze Tower by piotrunio)

## Related CSV Data

See the following files for complete map data with UIDs:
- `C:\Users\tomekdot\pursuit_channels_new_full_data.json` - Google Sheets data (125 rows, columns A-H)
- `C:\Users\tomekdot\pursuit_channels_new_data.tsv` - Sheet data + feedback matching

## Stats

- Total maps: 249
- Thumbnails downloaded: 248
- Environments: Valley, Canyon, Stadium, Lagoon
- Map types: PursuitArena, GoalHuntArena, HuntersArena
