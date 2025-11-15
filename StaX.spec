# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['D:/Scripts/modern-stock-browser/gui_main.py'],
    pathex=['D:/Scripts/modern-stock-browser'],
    binaries=[],
    datas=[
        ('D:/Scripts/modern-stock-browser/resources', 'resources'),
        ('D:/Scripts/modern-stock-browser/config', 'config'),
        ('D:/Scripts/modern-stock-browser/examples', 'examples'),
        ('D:/Scripts/modern-stock-browser/bin/ffmpeg', 'bin/ffmpeg'),
    ],
    hiddenimports=[
        'PySide2.QtCore',
        'PySide2.QtGui',
        'PySide2.QtWidgets',
        'ffpyplayer',
        'ffpyplayer.player',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.testing'],
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
    name='StaX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window for GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StaX',
)
