# NMS Tracker
**Publisher:** Shadowskeep LLC · **Version:** 1.0.0

A desktop companion for No Man's Sky: track the materials you need, see what everything
turns into, and work through ship repairs.

## Features
- **Collect List** — every material your open goals and ship repairs need, minus what you have.
  Switch between *Raw materials* (crafted parts broken down to what you gather) and
  *As listed in game*. Crafted parts you already own are counted first.
- **Materials & Recipes** — 2,300+ items and 1,600+ recipes. For any item: how to make it,
  what it refines or cooks into, what it crafts, and what it repairs.
- **Goals** — pick anything to build or stockpile. "Built it" removes the ingredients from your inventory.
- **Ship Repairs** — add a ship, click its broken components (all 16 damaged starship components
  plus engines, weapons and shields), and tick repairs off. The app tells you when you hold
  everything for a repair, and when a ship is flight ready.
- **Import from Save** — reads your No Man's Sky save (Steam or GOG version) to
  fill in what you own and to list every damaged slot on your ships. Press "Sync now" again
  after playing and anything you repaired in game is ticked off automatically.
  The save is opened read-only and is never modified; the running game is never touched.
- Runs offline. Item icons load from the Assistant for NMS CDN and are cached after first view.

## Run (development)
```
pip install -r requirements.txt
python tools\build_data.py      # only needed once, or after refreshing source-data
python qt_host\main.py
```

## Build the app and the installer
```
build.bat
```
Generates the icon and game data, builds with PyInstaller, signs, compiles the Inno Setup
installer and signs it. Needs Inno Setup 6 once: `winget install JRSoftware.InnoSetup`.

| Output | Path |
|---|---|
| App folder | `dist\NMS Tracker\` |
| Installer | `dist\installer\NMSTracker-Setup-<version>.exe` |

Signing uses the same self-signed "Shadowskeep LLC" certificate as the other Shadowskeep apps.
Set `SHADOWSKEEP_SIGN_THUMBPRINT` to use a purchased certificate instead.

## Your data
Saved to `%LOCALAPPDATA%\ShadowskeepLLC\NMSTracker\nms-tracker.db`
(in development: `instance\nms-tracker.db`). Uninstalling keeps it unless you choose otherwise.

## Updating the game data after a game patch
```
python tools\build_data.py --download
```
This re-downloads the source JSON and rebuilds `app\data\gamedata.json`. It also refreshes
`app\data\save_mapping.json`, which the save importer needs after big game updates.

## Project structure
```
nms-tracker/
├── app/
│   ├── gamedata.py      Loads game data, recipe indexes, requirement maths
│   ├── services.py      Collect list, inventory, repair readiness
│   ├── savefile.py      Read-only save decoder (LZ4 + key mapping)
│   ├── saveimport.py    Save -> inventory and ship damage, sync logic
│   ├── models.py        Inventory, Goal, Ship, Repair
│   ├── routes/          Pages and JSON API
│   ├── templates/       Jinja2 pages
│   ├── static/          CSS, JS, fonts, icon, splash.html
│   └── data/            gamedata.json (generated)
├── qt_host/             PyQt6 desktop shell (splash, 125% UI scale, tray)
├── source-data/         Raw JSON the game data is compiled from
├── tools/               build_data.py, make_icon.py, sign.ps1
├── installer/           Inno Setup script
└── build.bat
```

## Credits and licence notes
- Game data and item icons come from the open-source **Assistant for No Man's Sky**
  (github.com/AssistantNMS/App, GPL-3.0), which extracts them from the game files.
  That is fine for personal use. If you distribute this app, the GPL terms of that data apply.
- Save-file key names come from MBINCompiler's `mapping.json` (github.com/monkeyman192/MBINCompiler).
- No Man's Sky is © Hello Games. This is an unofficial fan tool.
- Font: Rajdhani (SIL Open Font License, see `app/static/fonts/OFL.txt`).
