"""One-off: retarget files copied from the Stardew tracker to this project. Safe to re-run."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def sub(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding='utf-8')
    for old, new in pairs:
        s = s.replace(old, new)
    p.write_text(s, encoding='utf-8')
    print('retargeted', rel)


sub('qt_host/window.py', [
    ("APP_NAME = 'Stardew Valley Tracker'", "APP_NAME = 'NMS Tracker'"),
    ('Shadowskeep LLC — Stardew Valley Tracker', "Shadowskeep LLC — NMS Tracker (No Man's Sky companion)"),
    ("BG_COLOR = '#4a2c1a'   # --brown-dark, matches the web UI shell", "BG_COLOR = '#080b14'   # --bg, matches the web UI shell"),
    ("QWebEngineProfile('stardew-tracker', self)", "QWebEngineProfile('nms-tracker', self)"),
    ("'color: #f0c040; padding: 24px;'", "'color: #ff7a5c; padding: 24px;'"),
    ("color: #c9956c;", "color: #8b9bb8;"),
    ("painter.fillRect(0, 0, 32, 32, QColor('#4a8c2a'))", "painter.fillRect(0, 0, 32, 32, QColor('#0d1220'))"),
    ("painter.fillRect(4, 4, 24, 24, QColor('#f0c040'))", "painter.fillRect(6, 6, 20, 20, QColor('#ff4f3a'))"),
    ("painter.fillRect(8, 8, 16, 16, QColor('#2d5a1b'))", "painter.fillRect(11, 11, 10, 10, QColor('#0d1220'))"),
    ('# Sizing: content at 1x needs ~884 CSS px wide; at UI_ZOOM that is ~1105.', '# Sizing: the collect table wants ~1000 CSS px; at UI_ZOOM that is ~1250.'),
])
sub('qt_host/main.py', [
    ('Stardew Valley Tracker — Desktop Entry Point', 'NMS Tracker — Desktop Entry Point'),
    ("ports=(5173, 0)", "ports=(5183, 0)"),
])
sub('qt_host/server_thread.py', [
    ('127.0.0.1:5173', '127.0.0.1:5183'),
    ('ports: Sequence[int] = (5173, 0)', 'ports: Sequence[int] = (5183, 0)'),
])
sub('nms_tracker.spec', [
    ('PyInstaller spec for Stardew Valley Tracker', 'PyInstaller spec for NMS Tracker'),
    ("        ('app/data',      'app/data'),\n", "        ('app/data/gamedata.json', 'app/data'),\n"),
    ("        'app.routes.dashboard',\n        'app.routes.tracker',\n        'app.routes.api',\n        'app.seed',\n"
     "        'app.wiki_sprites',\n        'app.collections',\n        'app.achievements',\n        'app.routes.reference',\n",
     "        'app.gamedata',\n        'app.services',\n        'app.routes.pages',\n        'app.routes.api',\n"),
    ("name='Stardew Valley Tracker'", "name='NMS Tracker'"),
])
sub('version_info.txt', [
    ('Stardew Valley Tracker', 'NMS Tracker'),
    ('Stardew Valley Community Centre', "No Man's Sky materials and ship repair"),
])
sub('installer/installer.iss', [
    ('Inno Setup script — Stardew Valley Tracker', 'Inno Setup script — NMS Tracker'),
    ('#define AppName      "Stardew Valley Tracker"', '#define AppName      "NMS Tracker"'),
    ('#define AppExe       "Stardew Valley Tracker.exe"', '#define AppExe       "NMS Tracker.exe"'),
    ('#define SourceDir    "..\\dist\\Stardew Valley Tracker"', '#define SourceDir    "..\\dist\\NMS Tracker"'),
    ('dist\\Stardew Valley Tracker\\', 'dist\\NMS Tracker\\'),
    ('StardewValleyTracker-Setup', 'NMSTracker-Setup'),
    ('AppId={{6F3C1B7E-2A54-4D0B-9E41-5D7A9C0E8B21}', 'AppId={{B2D94A61-7C3E-4F18-A5D2-91E6C4F0A37B}'),
    ('ShadowskeepLLC\\StardewTracker', 'ShadowskeepLLC\\NMSTracker'),
    ('saved progress and achievements', 'saved inventory, goals and ships'),
])
sub('build.bat', [
    ('Stardew Valley Tracker - Shadowskeep LLC', 'NMS Tracker - Shadowskeep LLC'),
    ('set "APP_EXE=dist\\Stardew Valley Tracker\\Stardew Valley Tracker.exe"', 'set "APP_EXE=dist\\NMS Tracker\\NMS Tracker.exe"'),
    ('taskkill /F /IM "Stardew Valley Tracker.exe"', 'taskkill /F /IM "NMS Tracker.exe"'),
    ('pyinstaller stardew_tracker.spec', 'pyinstaller nms_tracker.spec'),
    ('StardewValleyTracker-Setup-*.exe', 'NMSTracker-Setup-*.exe'),
    ('dist\\Stardew Valley Tracker\\', 'dist\\NMS Tracker\\'),
    ('echo [2/5] Generating app icon...\npython tools\\make_icon.py',
     'echo [2/5] Generating app icon and game data...\npython tools\\make_icon.py\nif errorlevel 1 goto :fail\npython tools\\build_data.py'),
])
sub('tools/sign.ps1', [
    ('Authenticode-sign one or more files for Stardew Valley Tracker.', 'Authenticode-sign one or more files for NMS Tracker.'),
    ('$env:SDVT_SIGN_THUMBPRINT', '$env:SHADOWSKEEP_SIGN_THUMBPRINT'),
    ('env SDVT_SIGN_THUMBPRINT', 'env SHADOWSKEEP_SIGN_THUMBPRINT'),
    ('"dist\\Stardew Valley Tracker\\Stardew Valley Tracker.exe"', '"dist\\NMS Tracker\\NMS Tracker.exe"'),
])
