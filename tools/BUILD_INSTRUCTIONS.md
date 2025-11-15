# Building StaX Installer

This document describes how to build standalone installers for StaX on Windows.

## Prerequisites

### Required Software
1. **Python 2.7 or 3.x** (tested with Python 3.8+)
2. **PyInstaller** - `pip install pyinstaller`
3. **NSIS 3.x** (optional, for creating Windows installer)
   - Download from: https://nsis.sourceforge.io/Download
   - Install to default location (C:\Program Files (x86)\NSIS)

### Required Python Packages
```bash
# Install build dependencies
pip install -r tools/requirements-build.txt

# Install runtime dependencies
pip install -r requirements.txt
```

## Build Process

### Step 1: Automated Build Script
The easiest way to build is using the automated script:

```bash
python tools/build_installer.py
```

This script will:
1. Clean previous build artifacts
2. Check all dependencies
3. Create PyInstaller .spec file
4. Build standalone executable
5. Create README.txt
6. Generate NSIS installer script
7. Create portable ZIP distribution

### Step 2: Manual PyInstaller Build (Alternative)
If you prefer manual control:

```bash
# Create spec file
pyi-makespec --onedir --windowed --name StaX --icon resources/icons/app_icon.ico gui_main.py

# Edit StaX.spec to add resources and data files
# (See tools/build_installer.py for reference configuration)

# Build executable
pyinstaller --clean --noconfirm StaX.spec
```

### Step 3: Create Windows Installer (Optional)
After building the executable:

```bash
# Compile NSIS script
cd installers
makensis StaX_installer.nsi
```

Or right-click `installers/StaX_installer.nsi` and select "Compile NSIS Script"

## Output Files

After successful build:

### Executable
- **Location**: `dist/StaX/`
- **Main file**: `StaX.exe`
- **Size**: ~100-200 MB (includes all dependencies)

### Portable Distribution
- **Location**: `installers/StaX_v1.0.0-beta_Portable.zip`
- **Contents**: Fully self-contained, extract and run
- **Use case**: No installation required, run from USB drive

### Installer
- **Location**: `installers/StaX_Setup_v1.0.0-beta.exe`
- **Type**: NSIS installer with uninstaller
- **Features**:
  - Installs to Program Files
  - Creates Start Menu shortcuts
  - Creates desktop shortcut
  - Registers in Add/Remove Programs
  - Includes uninstaller

## Testing the Build

### Test Standalone Executable
```bash
cd dist/StaX
./StaX.exe
```

### Test Installer
1. Run `installers/StaX_Setup_v1.0.0-beta.exe`
2. Follow installation wizard
3. Launch from Start Menu or desktop shortcut
4. Verify all features work correctly
5. Test uninstaller

### Test Portable ZIP
1. Extract `installers/StaX_v1.0.0-beta_Portable.zip`
2. Run `StaX/StaX.exe`
3. Verify it runs without installation

## Common Issues

### Issue: PyInstaller fails with import errors
**Solution**: Add missing modules to `hiddenimports` in .spec file

### Issue: FFmpeg/ffpyplayer not bundled correctly
**Solution**: Verify bin/ffmpeg directory is included in `datas` section of .spec file

### Issue: Qt platform plugin error
**Solution**: Ensure PySide2 plugins are bundled:
```python
datas=[
    ('path/to/PySide2/plugins', 'PySide2/plugins'),
]
```

### Issue: NSIS not found
**Solution**: 
1. Install NSIS from official website
2. Add to PATH: `C:\Program Files (x86)\NSIS`
3. Or use full path: `"C:\Program Files (x86)\NSIS\makensis.exe" StaX_installer.nsi`

### Issue: Large executable size
**Solution**: This is expected due to:
- PySide2 Qt libraries (~50 MB)
- ffpyplayer with FFmpeg binaries (~40 MB)
- Python runtime (~20 MB)
- Consider using UPX compression (already enabled in .spec)

## File Structure After Build

```
dist/
  StaX/
    StaX.exe           # Main executable
    _internal/         # Python runtime and libraries
    resources/         # Icons, stylesheets, etc.
    config/            # Configuration templates
    examples/          # Example processor scripts
    bin/
      ffmpeg/          # FFmpeg binaries
    README.txt         # User documentation

build/                 # Temporary build files (can be deleted)

installers/
  StaX_v1.0.0-beta_Portable.zip      # Portable distribution
  StaX_Setup_v1.0.0-beta.exe         # Windows installer
  StaX_installer.nsi                 # NSIS source script
```

## Distribution

### For End Users
Provide two options:

1. **Installer (Recommended)**:
   - `StaX_Setup_v1.0.0-beta.exe`
   - Automatic installation with shortcuts
   - Registered in Windows

2. **Portable**:
   - `StaX_v1.0.0-beta_Portable.zip`
   - Extract and run
   - No installation required

### For Developers/Testing
Use the `dist/StaX/` folder directly for quick testing.

## Customization

### Change Version Number
Edit `tools/build_installer.py`:
```python
APP_VERSION = "1.0.0-beta"  # Change this
```

### Add Custom Icon
1. Create/obtain app_icon.ico (Windows ICO format)
2. Place in: `resources/icons/app_icon.ico`
3. Rebuild with `python tools/build_installer.py`

### Bundle Additional Files
Edit .spec file `datas` section:
```python
datas=[
    ('your_folder', 'destination_folder'),
    ('your_file.txt', '.'),
]
```

## Automation

For CI/CD pipelines, create a build script:

```bash
# build.bat
@echo off
echo Building StaX Installer...
python tools/build_installer.py
if %ERRORLEVEL% NEQ 0 goto error

echo Building NSIS installer...
cd installers
makensis StaX_installer.nsi
if %ERRORLEVEL% NEQ 0 goto error

echo Build complete!
goto end

:error
echo Build failed!
exit /b 1

:end
```

## Notes

- Build time: 3-5 minutes on average hardware
- Executable is **not signed** by default (requires code signing certificate)
- For production releases, consider code signing to avoid Windows SmartScreen warnings
- Test on clean Windows VM before distribution
- Keep installer archives for version history

## Support

For build issues:
1. Check PyInstaller documentation: https://pyinstaller.org/
2. Check NSIS documentation: https://nsis.sourceforge.io/Docs/
3. Review logs in `build/StaX/warn-StaX.txt`
