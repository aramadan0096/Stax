# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['E:/Scripts/Stax/main.py'],
    pathex=['E:/Scripts/Stax'],
    binaries=[],
    datas=[
        ('E:/Scripts/Stax/resources', 'resources'),
        ('E:/Scripts/Stax/config', 'config'),
        ('E:/Scripts/Stax/examples', 'examples'),
        ('E:/Scripts/Stax/bin/ffmpeg', 'bin/ffmpeg'),
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
    icon='E:/Scripts/Stax/resources/logo.ico',
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
