# Blender Plugin Implementation Summary

## Overview
A new Blender plugin has been implemented for StaX, using native Blender UI (`bpy.types.Panel`) instead of PySide2. This removes the dependency on PySide2/Qt inside Blender.

## Components

### 1. Plugin Structure (`plugins/dccs/blender/StaX/`)
- **`__init__.py`**: Registers the addon, preferences, and initializes the UI.
- **`ui.py`**: Implements the native Blender UI (Panel, Operators, Properties).
- **`bridge.py`**: `BlenderBridge` class that abstracts `bpy` operations.

### 2. Features
- **Native Blender UI**:
  - **StaX Browser Panel**: Located in the 3D View Sidebar (N-panel) under "StaX".
  - **Search**: Filter assets by name.
  - **Stacks & Lists**: Dropdowns to navigate the library.
  - **Asset Grid**: Displays thumbnails using `template_icon_view`.
- **Import**:
  - "Import Selected" button imports the selected asset into the scene.
  - Supports `.abc`, `.obj`, `.fbx`, `.glb`.
- **Add to Library**:
  - "Add Selection to Library" button opens a native dialog.
  - Exports selected objects as Alembic (`.abc`) for the "mesh" (hard copy).
  - Registers the asset in the SQLite database.
  - Automatically generates GLB preview (via background process if configured).

## Usage
1. **Install**: Install the `StaXBlenderAddon.zip` via Preferences > Add-ons.
2. **Configure**: In Add-on Preferences, set the "StaX Root Directory" if not auto-detected.
3. **Open**: Press `N` in the 3D Viewport to open the Sidebar, click the "StaX" tab.
4. **Browse**: Select a Stack and List to view assets.
5. **Import**: Select an asset thumbnail and click "Import Selected".
6. **Ingest**: Select objects in the scene, click "Add Selection to Library", fill in details, and click OK.

## Dependencies
- **StaX Core**: The plugin relies on the `src` directory of the main StaX installation.
- **No PySide2 required**: The plugin uses standard Blender API.

---

## Packaging & Installation (Detailed)

This section provides concrete steps and recommendations to package, distribute and install the StaX Blender addon.

**Recommended addon folder layout**

```
StaX/                    # The folder inside plugins/dccs/blender/
  __init__.py            # bl_info + register/unregister
  ui.py                  # Native Blender UI implementation
  bridge.py              # BlenderBridge (bpy usage)
```

**`__init__.py` requirements**
- Provide a `bl_info` dict.
- Register/Unregister `ui` module.

**Create a distributable ZIP**
- Zip the `StaX` folder.

PowerShell example (from repo root):

```powershell
Push-Location 'D:\Scripts\modern-stock-browser\plugins\dccs\blender'
$out = 'D:\Scripts\modern-stock-browser\dist\StaXBlenderAddon.zip'
if (!(Test-Path (Split-Path $out))) { New-Item -ItemType Directory -Path (Split-Path $out) | Out-Null }
Compress-Archive -Path 'StaX' -DestinationPath $out -Force
Pop-Location
```

**Install inside Blender**
- Preferences → Add-ons → Install → choose the zip → enable the addon.
- Optionally enable **Auto Run Python Scripts** under Preferences → Save & Load if your addon executes scripts automatically (warn users about security).

---

## Dependency Handling

Because Blender ships with its own Python interpreter and unique ABI, dependency handling requires care.

Options:
- **Install dependencies into Blender's Python** (works but can be brittle). See Windows steps below.
- **Vendor pure-Python packages** by copying them into `libs/` and inserting that path into `sys.path` inside `__init__.py`.
- **Run the Qt UI as an external application** (recommended for complex Qt UIs): have the Blender addon act as a lightweight bridge (IPC, local HTTP, sockets, or files). This avoids ABI and packaging issues inside Blender.

Vendorizing example (in `__init__.py`):

```python
import os, sys
here = os.path.dirname(__file__)
libs = os.path.join(here, 'libs')
if os.path.isdir(libs) and libs not in sys.path:
    sys.path.insert(0, libs)
```

### PySide2 in Blender (Windows PowerShell)

If you choose to require `PySide2` inside Blender, these are the typical steps on Windows. Replace paths with the ones reported by your Blender install.

1. Find Blender's Python executable (from Blender's Python Console):

```python
import sys
print(sys.executable)
```

2. From an elevated or user PowerShell, run (example):

```powershell
#$pythonExe must be the absolute path printed by Blender
#$pythonExe = 'C:\Program Files\Blender Foundation\Blender 3.5\3.5\python\bin\python.exe'
& $pythonExe -m ensurepip
& $pythonExe -m pip install --upgrade pip setuptools wheel
& $pythonExe -m pip install PySide2
```

Notes & common issues:
- `PySide2` prebuilt wheels may not be available for every Blender Python version; pip may try to build from source and fail unless MSVC build tools are installed.
- If `PySide2` fails, consider `PySide6` (but that is a different Qt version) or the external UI approach.

---

## Safe import patterns & runtime compatibility

- Avoid importing `bpy` or Blender-only modules at top-level when testing code outside Blender. Use a guard:

```python
try:
    import bpy
    IN_BLENDER = True
except Exception:
    IN_BLENDER = False
```

- Defer heavy imports (PySide2, web engines) until inside `register()` or an operator callback to reduce import-time failures.

---

## Exporters: Alembic & glTF

- Vanilla Blender includes Alembic and glTF exporters. Confirm availability in your target Blender build:

```python
import bpy
print(hasattr(bpy.ops.wm, 'alembic_export'))
print(hasattr(bpy.ops.export_scene, 'gltf'))
```

- Examples used by the addon:

```python
bpy.ops.wm.alembic_export(filepath='C:/out/asset.abc', selected=True, start=1, end=250)
bpy.ops.export_scene.gltf(filepath='C:/out/asset.glb', use_selection=True, export_format='GLB')
```

---

## Testing & Debugging Checklist

- Check Blender Python information: `sys.executable`, `sys.version`, `sys.path` from the Scripting console.
- Test exporter operators in the console before relying on them.
- Use **Window → Toggle System Console** to view prints and tracebacks on Windows.
- If the addon doesn't appear:
  - Confirm `__init__.py` exists and `bl_info` is valid.
  - Look for traceback in the system console — common cause: imports performed at module import time.
- To validate PySide2 availability in Blender's runtime, open the Python Console and run `import PySide2`.

---

## Security & Deployment Notes

- Installing packages into Blender's Python may be disallowed in locked-down environments. Provide clear instructions and an alternative (external UI).
- Recommend users review code before enabling **Auto Run Python Scripts**.

---

## Recommended approach for StaX

- For reliability and lower support burden, run the full Qt-based StaX UI as an external application (bundled with PySide2 in a portable environment or installed in a separate venv). Use the Blender addon as a small bridge that sends commands to the external UI (for ingestion, import, or preview launches). This avoids fighting compiled wheel compatibility across Blender versions and platforms.

---

## Next steps
- Add a `plugins/dccs/blender/INSTALL.md` with the above commands and troubleshooting steps.
- Optionally create a build script (`tools/build_blender_addon.ps1`) that zips the addon into `dist/`.

