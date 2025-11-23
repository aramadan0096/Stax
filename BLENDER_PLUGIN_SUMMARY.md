# Blender Plugin Implementation Summary

## Overview
A new Blender plugin has been implemented for StaX, mirroring the functionality of the Nuke integration.

## Components

### 1. Plugin Structure (`plugins/dccs/blender/`)
- **`__init__.py`**: Registers the "Stax" menu in Blender's top bar and defines operators.
- **`panel.py`**: Main entry point for the Qt interface. Initializes `StaXBlenderPanel` and handles `sys.path` setup.
- **`bridge.py`**: `BlenderBridge` class that abstracts `bpy` operations. Implements `import_object`, `export_abc`, `export_glb`, and Nuke-compatible aliases (`create_read_geo_node`).
- **`ingest_dialog.py`**: `RegisterMeshDialog` for the "Add to Library" workflow.

### 2. Features
- **Drag & Drop 3D Support**: 
  - `BlenderBridge.import_object` handles `.abc`, `.obj`, `.fbx`, `.glb`.
  - `MediaDisplayWidget` uses `bridge.create_read_geo_node` (aliased to `import_object`) for drag & drop actions.
- **3D Preview Panel**:
  - Integrated `GeometryViewerWidget` (WebGL-based) into `MediaDisplayWidget`.
  - Added a collapsible `QSplitter` to show the 3D viewer when a 3D asset is selected.
  - Loads `.glb` proxies from `geometry_preview_path`.
- **Add to Library**:
  - New "Add to Library" button in the toolbar.
  - Exports selected objects as Alembic (`.abc`) for the "mesh" (hard copy).
  - Exports selected objects as GLB (`.glb`) for the "proxy" (preview).
  - Registers the asset in the SQLite database with `geometry_preview_path`.

## Usage
1. **Install**: Copy the `plugins/dccs/blender` folder to Blender's addons directory or install as a zip.
2. **Open**: Use "Window > StaX > Open Browser" or the "Stax" menu in the top bar.
3. **Ingest**: Select objects in Blender, click "Add to Library", fill in details, and click OK.
4. **Import**: Drag and drop assets from the StaX panel into the 3D Viewport.

## Dependencies
- **PySide2**: Must be installed in Blender's Python environment (optional/recommended only if running the Qt UI inside Blender).
- **StaX Core**: The plugin relies on the `src` directory of the main StaX installation.

---

## Packaging & Installation (Detailed)

This section provides concrete steps and recommendations to package, distribute and install the StaX Blender addon.

**Recommended addon folder layout**

```
StaX/                    # The folder inside plugins/dccs/blender/
  __init__.py            # bl_info + register/unregister
  panel.py               # Blender operator wrappers + Qt launcher
  bridge.py              # BlenderBridge (bpy usage)
  ingest_dialog.py       # Dialogs used from inside Blender (optional)
  resources/             # icons, viewer html, static assets
  libs/                  # vendored pure-Python dependencies (optional)
```

**`__init__.py` requirements**
- Provide a `bl_info` dict with keys: `name`, `author`, `version`, `blender` (tuple), `location`, `description`, `category`.
- Implement `register()` and `unregister()` that call `bpy.utils.register_class()` / `bpy.utils.unregister_class()` for all addon classes, and append/remove menu entries.
- Use `if __name__ == "__main__": register()` for quick local tests.

Example `bl_info` snippet:

```python
bl_info = {
    "name": "StaX Asset Manager",
    "author": "Ahmed Ramadan",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Window > StaX",
    "description": "Asset management system for VFX pipelines",
    "category": "Pipeline",
}
```

**Create a distributable ZIP**
- Blender expects the zip file to contain a single folder (e.g., `StaX/`) which contains the `__init__.py`.
- Do NOT zip the files directly at the root of the archive.
- Do NOT zip the `blender` folder if it contains other things. Zip the `StaX` folder specifically.

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

