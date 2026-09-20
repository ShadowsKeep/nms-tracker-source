# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NMS Tracker — Shadowskeep LLC
import os

block_cipher = None

# Optional app icon: drop a file at app/static/img/icon.ico to use it.
ICON = 'app/static/img/icon.ico'
ICON = ICON if os.path.exists(ICON) else None

a = Analysis(
    ['qt_host/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static',    'app/static'),
        ('app/data/gamedata.json', 'app/data'),
        ('app/data/save_mapping.json', 'app/data'),
        ('app/data/wiki.json', 'app/data'),
    ],
    hiddenimports=[
        'PyQt6.sip',
        'PyQt6.QtPrintSupport',
        'flask_sqlalchemy',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'app',
        'app.models',
        'app.gamedata',
        'app.services',
        'app.savefile',
        'app.saveimport',
        'app.routes.pages',
        'app.routes.api',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NMS Tracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NMS Tracker',
)
