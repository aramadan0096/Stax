#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build Installer Script for StaX
Creates standalone Windows executable and installer package using PyInstaller
"""

import os
import sys
import shutil
import subprocess
import platform

# Project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(PROJECT_ROOT, 'dist')
BUILD_DIR = os.path.join(PROJECT_ROOT, 'build')
INSTALLER_OUTPUT = os.path.join(PROJECT_ROOT, 'installers')

# Application metadata
APP_NAME = "StaX"
APP_VERSION = "1.0.0-beta"
APP_DESCRIPTION = "Advanced VFX Asset Management for Nuke"
APP_AUTHOR = "VFX Pipeline Team"
MAIN_SCRIPT = os.path.join(PROJECT_ROOT, 'gui_main.py')
ICON_PATH = os.path.join(PROJECT_ROOT, 'resources', 'icons', 'app_icon.ico')


def clean_build_directories():
    """Remove previous build artifacts."""
    print("=" * 60)
    print("Cleaning previous build artifacts...")
    print("=" * 60)
    
    for directory in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(directory):
            print("Removing: {}".format(directory))
            shutil.rmtree(directory)
    
    print("Clean complete.\n")


def check_dependencies():
    """Check if required build tools are installed."""
    print("=" * 60)
    print("Checking dependencies...")
    print("=" * 60)
    
    try:
        import PyInstaller
        print("[OK] PyInstaller is installed: {}".format(PyInstaller.__version__))
    except ImportError:
        print("[ERROR] PyInstaller not found.")
        print("Install with: pip install pyinstaller")
        sys.exit(1)
    
    # Check for ffpyplayer
    try:
        import ffpyplayer
        print("[OK] ffpyplayer is installed")
    except ImportError:
        print("[WARNING] ffpyplayer not found. It will need to be bundled separately.")
    
    # Check for PySide2
    try:
        import PySide2
        print("[OK] PySide2 is installed: {}".format(PySide2.__version__))
    except ImportError:
        print("[ERROR] PySide2 not found.")
        print("Install with: pip install PySide2")
        sys.exit(1)
    
    print("Dependency check complete.\n")


def create_spec_file():
    """Create PyInstaller .spec file with proper configuration."""
    print("=" * 60)
    print("Creating PyInstaller spec file...")
    print("=" * 60)
    
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{main_script}'],
    pathex=['{project_root}'],
    binaries=[],
    datas=[
        ('{project_root}/resources', 'resources'),
        ('{project_root}/config', 'config'),
        ('{project_root}/examples', 'examples'),
        ('{project_root}/bin/ffmpeg', 'bin/ffmpeg'),
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
    hooksconfig={{}},
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
    name='{app_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window for GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{icon_path}',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{app_name}',
)
'''.format(
        main_script=MAIN_SCRIPT.replace('\\', '/'),
        project_root=PROJECT_ROOT.replace('\\', '/'),
        app_name=APP_NAME,
        icon_path=ICON_PATH.replace('\\', '/') if os.path.exists(ICON_PATH) else ''
    )
    
    spec_file_path = os.path.join(PROJECT_ROOT, 'StaX.spec')
    with open(spec_file_path, 'w') as f:
        f.write(spec_content)
    
    print("Spec file created: {}".format(spec_file_path))
    print()
    return spec_file_path


def build_executable(spec_file):
    """Run PyInstaller to create standalone executable."""
    print("=" * 60)
    print("Building standalone executable with PyInstaller...")
    print("=" * 60)
    
    cmd = [
        sys.executable,
        '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        spec_file
    ]
    
    print("Running: {}".format(' '.join(cmd)))
    print()
    
    result = subprocess.call(cmd, cwd=PROJECT_ROOT)
    
    if result != 0:
        print("\n[ERROR] PyInstaller build failed with exit code: {}".format(result))
        sys.exit(1)
    
    print("\n[SUCCESS] Executable built successfully!")
    print("Output directory: {}".format(DIST_DIR))
    print()


def create_readme():
    """Create README.txt for distribution."""
    print("Creating README.txt for distribution...")
    
    readme_content = '''
==============================================================
StaX - Advanced VFX Asset Management for Nuke
==============================================================

Version: {version}
Platform: Windows x64

DESCRIPTION:
StaX is a professional-grade asset management tool for VFX pipelines,
specifically designed for integration with Foundry Nuke. It provides
advanced features for cataloging, previewing, and retrieving media
assets including plates, 3D models, and toolsets.

INSTALLATION:
1. Run the installer (StaX_Setup_v{version}.exe)
2. Choose installation directory (default: C:\\Program Files\\StaX)
3. Follow installation wizard prompts
4. Launch StaX from Start Menu or desktop shortcut

SYSTEM REQUIREMENTS:
- Windows 10/11 (64-bit)
- 4 GB RAM minimum (8 GB recommended)
- 500 MB disk space for application
- Additional space for media database and previews
- Optional: Foundry Nuke (for DAG integration features)

FIRST RUN:
1. Launch StaX
2. Configure database location (Settings > Database)
3. Set up repository paths (Settings > Repository)
4. Create your first Stack and List
5. Drag & drop media to ingest

FEATURES:
- Hierarchical organization (Stacks > Lists > Elements)
- Drag & drop ingestion with automatic sequence detection
- Preview generation (thumbnails, GIFs, video previews)
- Embedded video player with ffpyplayer
- Nuke integration (drag elements into DAG)
- Toolset creation from Nuke selections
- Advanced search and filtering
- Favorites and playlists
- Custom processor hooks for pipeline integration
- Network-aware database sharing

CONFIGURATION:
Configuration files are located in: ./config/config.json
Example processor scripts: ./examples/

SUPPORT:
For issues, documentation, and updates, visit:
https://github.com/your-repo/stax

LICENSE:
Copyright (c) 2025 {author}
All rights reserved.

==============================================================
'''.format(version=APP_VERSION, author=APP_AUTHOR)
    
    readme_path = os.path.join(DIST_DIR, APP_NAME, 'README.txt')
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    print("README.txt created: {}".format(readme_path))
    print()


def create_nsis_installer_script():
    """Create NSIS installer script (requires NSIS installed separately)."""
    print("=" * 60)
    print("Creating NSIS installer script...")
    print("=" * 60)
    
    nsis_script = '''
; StaX Installer Script for NSIS
; Requires NSIS 3.x (https://nsis.sourceforge.io/)

!define APP_NAME "StaX"
!define APP_VERSION "{version}"
!define APP_PUBLISHER "{author}"
!define APP_EXE "StaX.exe"
!define APP_INSTALL_DIR "$PROGRAMFILES64\\StaX"

Name "${{APP_NAME}} ${{APP_VERSION}}"
OutFile "{installer_output}\\StaX_Setup_v{version}.exe"
InstallDir "${{APP_INSTALL_DIR}}"
RequestExecutionLevel admin

Page directory
Page instfiles

Section "Install"
    SetOutPath "$INSTDIR"
    
    ; Copy all files from dist directory
    File /r "{dist_dir}\\StaX\\*.*"
    
    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\${{APP_NAME}}"
    CreateShortcut "$SMPROGRAMS\\${{APP_NAME}}\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"
    CreateShortcut "$DESKTOP\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"
    
    ; Add to Add/Remove Programs
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "DisplayName" "${{APP_NAME}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "DisplayVersion" "${{APP_VERSION}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "Publisher" "${{APP_PUBLISHER}}"
SectionEnd

Section "Uninstall"
    ; Remove files
    RMDir /r "$INSTDIR"
    
    ; Remove shortcuts
    Delete "$DESKTOP\\${{APP_NAME}}.lnk"
    Delete "$SMPROGRAMS\\${{APP_NAME}}\\${{APP_NAME}}.lnk"
    RMDir "$SMPROGRAMS\\${{APP_NAME}}"
    
    ; Remove registry entries
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}"
SectionEnd
'''.format(
        version=APP_VERSION,
        author=APP_AUTHOR,
        installer_output=INSTALLER_OUTPUT.replace('\\', '\\\\'),
        dist_dir=DIST_DIR.replace('\\', '\\\\')
    )
    
    if not os.path.exists(INSTALLER_OUTPUT):
        os.makedirs(INSTALLER_OUTPUT)
    
    nsis_script_path = os.path.join(INSTALLER_OUTPUT, 'StaX_installer.nsi')
    with open(nsis_script_path, 'w') as f:
        f.write(nsis_script)
    
    print("NSIS script created: {}".format(nsis_script_path))
    print("\nTo build installer:")
    print("1. Install NSIS from https://nsis.sourceforge.io/")
    print("2. Right-click {} and select 'Compile NSIS Script'".format(nsis_script_path))
    print("   OR run: makensis {}".format(nsis_script_path))
    print()


def create_zip_distribution():
    """Create ZIP archive for portable distribution."""
    print("=" * 60)
    print("Creating portable ZIP distribution...")
    print("=" * 60)
    
    import zipfile
    
    if not os.path.exists(INSTALLER_OUTPUT):
        os.makedirs(INSTALLER_OUTPUT)
    
    zip_path = os.path.join(INSTALLER_OUTPUT, 'StaX_v{}_Portable.zip'.format(APP_VERSION))
    dist_folder = os.path.join(DIST_DIR, APP_NAME)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, DIST_DIR)
                zipf.write(file_path, arcname)
                print("  Adding: {}".format(arcname))
    
    print("\n[SUCCESS] ZIP created: {}".format(zip_path))
    print("Size: {:.2f} MB".format(os.path.getsize(zip_path) / (1024.0 * 1024.0)))
    print()


def main():
    """Main build process."""
    print("\n" + "=" * 60)
    print("StaX Installer Build Script")
    print("Version: {}".format(APP_VERSION))
    print("Platform: {}".format(platform.system()))
    print("=" * 60 + "\n")
    
    # Step 1: Clean
    clean_build_directories()
    
    # Step 2: Check dependencies
    check_dependencies()
    
    # Step 3: Create spec file
    spec_file = create_spec_file()
    
    # Step 4: Build executable
    build_executable(spec_file)
    
    # Step 5: Create README
    create_readme()
    
    # Step 6: Create NSIS installer script
    create_nsis_installer_script()
    
    # Step 7: Create ZIP distribution
    create_zip_distribution()
    
    # Summary
    print("\n" + "=" * 60)
    print("BUILD COMPLETE!")
    print("=" * 60)
    print("Executable: {}\\{}\\{}.exe".format(DIST_DIR, APP_NAME, APP_NAME))
    print("Portable ZIP: {}\\StaX_v{}_Portable.zip".format(INSTALLER_OUTPUT, APP_VERSION))
    print("NSIS Script: {}\\StaX_installer.nsi".format(INSTALLER_OUTPUT))
    print("\nNext steps:")
    print("1. Test the executable: {}\\{}\\{}.exe".format(DIST_DIR, APP_NAME, APP_NAME))
    print("2. Build installer: Compile NSIS script with makensis")
    print("3. Test installer: Run StaX_Setup_v{}.exe".format(APP_VERSION))
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()
