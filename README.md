# StaX

**Professional stock footage and asset management system for VFX pipelines**

StaX is an advanced media browser and asset management tool designed specifically for integration with Foundry Nuke. It provides powerful features for organizing, searching, and deploying visual effects assets with intelligent sequence detection, automated preview generation, and extensible pipeline hooks.

![StaX graph](assets\seq-animated.gif)



</details>
---

## Table of Contents

- [What is StaX?](#what-is-stax)
- [How StaX Works](#how-stax-works)
   - [Organization Hierarchy](#organization-hierarchy)
   - [Asset Ingestion](#asset-ingestion)
   - [Copy Policies](#copy-policies)
   - [Searching and Filtering](#searching-and-filtering)
   - [Favorites and Playlists](#favorites-and-playlists)
- [Installation](#installation)
   - [Standalone Desktop Application](#standalone-desktop-application)
   - [Nuke Plugin Installation](#nuke-plugin-installation)
   - [Building the Windows installer (NSIS)](#building-the-windows-installer-nsis)
   - [Method 2: Network Repository (Studio/Multi-User)](#method-2-network-repository-studio-multi-user)
- [Nuke Plugin Usage](#nuke-plugin-usage)
   - [Opening StaX in Nuke](#opening-stax-in-nuke)
   - [Inserting Assets into Nuke](#inserting-assets-into-nuke)
   - [Registering Toolsets](#registering-toolsets)
   - [Quick Actions](#quick-actions)
- [Keyboard Shortcuts](#keyboard-shortcuts)
   - [Global Shortcuts](#global-shortcuts)
   - [Nuke Plugin Shortcuts](#nuke-plugin-shortcuts)
   - [Navigation Shortcuts](#navigation-shortcuts)
- [Configuration](#configuration)
   - [Database Location](#database-location)
   - [Settings Panel](#settings-panel)
   - [Custom Processors (Pipeline Integration)](#custom-processors-pipeline-integration)
- [Advanced Features](#advanced-features)
   - [Pagination](#pagination)
   - [Preview System](#preview-system)
   - [Network-Aware Database](#network-aware-database)
   - [Tags and Metadata](#tags-and-metadata)
- [Troubleshooting](#troubleshooting)
   - [Nuke Plugin Not Loading](#nuke-plugin-not-loading)
   - [Database Lock Errors](#database-lock-errors)
   - [Drag & Drop Not Working in Nuke](#drag--drop-not-working-in-nuke)
- [Documentation](#documentation)
- [Project Status](#project-status)
- [Contributing](#contributing)
- [License](#license)

## What is StaX?

StaX helps VFX artists and studios manage large collections of stock footage, 3D assets, and Nuke toolsets through:

- **Hierarchical Organization**: Organize assets into Stacks → Lists → Elements with support for nested sub-lists
- **Smart Ingestion**: Automatic image sequence detection, frame range discovery, and metadata extraction
- **Dual-Path Storage**: Choose between hard copies (physical repository) or soft copies (reference links)
- **Rich Previews**: Automatic thumbnail, GIF, and video preview generation for quick asset review
- **Nuke Integration**: Drag and drop assets directly into Nuke's Node Graph with automatic Read/ReadGeo node creation
- **Network-Ready**: SQLite database with file locking for multi-user workstation access
- **Extensible**: Custom Python processors for pre-ingest validation, post-ingest hooks, and post-import node configuration

![StaX graph](assets\StaX-mian-standalone.png)

---

## How StaX Works

![StaX graph](assets\StaX-ingestion-standalone.png)

### Organization Hierarchy

StaX uses a three-level hierarchy to organize assets:

```
Stacks (Primary Categories)
  └─ Lists (Sub-Categories)
      └─ Sub-Lists (Optional nested categories)
          └─ Elements (Individual Assets)
```

**Example structure:**
```
📦 Plates
  └─ 🗂 Explosions
      └─ 🗂 Aerial Explosions
          └─ 🎬 explosion_aerial_001.mov
          └─ 🎬 explosion_aerial_002.mov
  └─ 🗂 Cityscapes
      └─ 🖼 NYC_skyline_####.exr (frames 1001-1150)

📦 3D Assets
  └─ 🗂 Characters
      └─ 🎨 hero_model.abc
  └─ 🗂 Props
      └─ 🎨 vehicle_rig.fbx
```

### Asset Ingestion

**Single File Ingestion:**
1. Go to **File → Ingest Files** (or press `Ctrl+I`)
2. Select files to ingest
3. Choose target Stack and List
4. Select copy policy (hard copy or soft copy)
5. StaX automatically:
   - Detects image sequences and frame ranges
   - Copies files to repository (if hard copy selected)
   - Generates thumbnail, GIF, and video previews
   - Extracts metadata (resolution, format, duration, etc.)
   - Creates database entry

**Library Ingestion (Bulk):**
1. Go to **File → Ingest Library** (or press `Ctrl+Shift+I`)
2. Select a root folder
3. StaX scans the folder structure and maps folders to Stacks/Lists
4. Preview the structure and configure options
5. Ingest entire library in one operation

### Copy Policies

- **Hard Copy**: Physical files are copied to the repository directory. Assets remain accessible even if original files move.
- **Soft Copy**: Only file path references are stored. Useful for large assets on network storage.

### Searching and Filtering

![StaX graph](assets\StaX-search-standalone.png)

**Live Filter:**
- Type in the search box to instantly filter elements by name
- Use `#tagname` to search by tags (e.g., `#fire` or `#fire,explosion`)

**Advanced Search** (`Ctrl+F`):
- Search by property: name, format, type, comment, tags
- Choose match type: loose (partial match) or strict (exact match)
- Results displayed in sortable table

### Favorites and Playlists

- **Favorites**: Click the ⭐ button or right-click → "Add to Favorites" for quick access to frequently used assets
- **Playlists**: Create collaborative collections with **+ Playlist** button. Add multiple elements to playlists for organized workflows.

---

## Installation

<details>
<summary><strong>Installation Details</strong></summary>

### Standalone Desktop Application

**Requirements:**
- Python 2.7 or Python 3.x
- PySide2
- ffpyplayer (for video playback)

**Setup:**

```bash
# Clone repository
git clone https://github.com/aramadan0096/Stax.git
cd Stax

# Create virtual environment (Python 3 recommended)
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install PySide2 ffpyplayer
```

**Run Standalone:**

```bash
python main.py
```

On first launch, StaX will:
1. Create the database in `./data/stax.db`
2. Create directories for previews (`./previews`) and repository (`./repository`)
3. Show the login dialog (default admin credentials: admin/admin)

### Nuke Plugin Installation

#### Method 1: User Directory (Single User)

1. **Locate your Nuke user directory:**
   - **Windows:** `C:\Users\<username>\.nuke`
   - **macOS:** `/Users/<username>/.nuke`
   - **Linux:** `/home/<username>/.nuke`

2. **Copy StaX to the plugins folder:**
   ```bash
   # Copy entire Stax folder to .nuke directory
   cp -r Stax ~/.nuke/StaX
   ```

3. **Update your `.nuke/init.py`:**
   ```python

### Building the Windows installer (NSIS)

This project includes a build helper script that prepares a PyInstaller spec and supporting artifacts, then generates an NSIS installer script you can compile into a Windows installer. The script is located at `tools/build_installer.py` and automates most steps. Below is a full guide to build the installer on Windows using PowerShell.

Prerequisites
- Python (the same version you used to develop / package the app)
- PyInstaller (pip install pyinstaller)
- PySide2 installed in the packaging environment
- NSIS (makensis) installed to compile the .nsi into an installer — download from https://nsis.sourceforge.io/Download
- (Optional) ffpyplayer if you want video playback bundled

Step-by-step (PowerShell)

1. Open a PowerShell prompt and activate your virtualenv (if using one):

```powershell
# From project root (E:\Scripts\Stax)
.venv\Scripts\Activate
```

2. Install build dependencies (if not already installed):

```powershell
pip install -r tools/requirements.txt
# or explicitly
pip install pyinstaller PySide2
```

3. Run the build helper script which will:
- clean previous build/dist folders
- create a PyInstaller .spec (`StaX.spec`)
- run PyInstaller to generate the `dist\StaX` folder
- produce `installers\StaX_installer.nsi` and a portable ZIP

```powershell
   import nuke
   import os
   

4. Compile the NSIS script into an installer using makensis. Typical NSIS install locations:
- 64-bit Windows: C:\Program Files (x86)\NSIS\makensis.exe

Run:

```powershell
   # Add StaX plugin path
   stax_path = os.path.join(os.path.dirname(__file__), 'StaX')
   if os.path.isdir(stax_path):
       nuke.pluginAddPath(stax_path)
       print("[StaX] Plugin loaded from: {}".format(stax_path))
   ```

5. After compilation you'll find the generated installer in the `installers` folder (the .nsi OutFile controls the installer name). Run it to test installation.

Customization notes
- Icon: `tools/build_installer.py` sets ICON_PATH at the top. By default it expects `resources/icons/app_icon.ico`. If you prefer to use `resources/logo.ico`, update the `ICON_PATH` variable in `tools/build_installer.py` before running the build script.
- Examples: The build script will include a `examples` folder. If missing, the script now creates an empty `examples` dir automatically. You can add sample processor scripts or examples there prior to packaging.
- Spec edits: The script generates `StaX.spec` in the project root — you can edit this file to add or exclude datas, hiddenimports, or binaries before running PyInstaller.

Troubleshooting
- PyInstaller errors: run PyInstaller manually to get verbose output, e.g. `pyinstaller --clean --noconfirm StaX.spec`.
- Missing modules at runtime: add them to `hiddenimports` in the spec or in `tools/build_installer.py`'s spec template.
- EXE icon not showing: make sure the `.ico` file exists and is referenced by `ICON_PATH` when creating the spec; also set the EXE icon in your packaging tool if needed.
- NSIS errors: open the .nsi file and inspect paths. NSIS reports helpful line numbers when compilation fails.

Code signing and distribution
- If you publish the installer, consider code signing the EXE with a trusted certificate. NSIS supports calling signing tools during or after build.
- Test the built installer on a clean VM to validate runtime dependencies and runtime behavior.

What the build script creates
- `dist\StaX\StaX.exe` — standalone executable generated by PyInstaller
- `installers\StaX_v{version}_Portable.zip` — portable ZIP
- `installers\StaX_installer.nsi` — NSIS script (compile with makensis)

If you want, I can update `tools/build_installer.py` to point its `ICON_PATH` to `resources/logo.ico` by default and/or add a small sample file into the `examples` folder that will be included in the build.



4. **Restart Nuke**

#### Method 2: Network Repository (Studio/Multi-User)

For VFX studios with shared network storage:

1. **Copy StaX to network location:**
   ```bash
   # Copy to shared storage
   cp -r Stax //server/share/nuke_plugins/StaX
   ```

2. **Set environment variable before launching Nuke:**
   
   **Windows (PowerShell):**
   ```powershell
   $env:NUKE_PATH="\\server\share\nuke_plugins\StaX"
   & "C:\Program Files\Nuke15.0\Nuke15.0.exe"
   ```
   
   **Linux/macOS (bash):**
   ```bash
   export NUKE_PATH=/server/share/nuke_plugins/StaX
   /usr/local/Nuke15.0/Nuke15.0
   ```

3. **Configure shared database** (recommended for studios):
   
   Set the `STOCK_DB` environment variable to point to a shared database:
   ```bash
   # Windows
   set STOCK_DB=\\server\share\vfx\stax_production.db
   
   # Linux/macOS
   export STOCK_DB=/server/share/vfx/stax_production.db
   ```


---
</details>

## Nuke Plugin Usage

![StaX graph](assets\StaX-mian-nuke.png)

### Opening StaX in Nuke

**Keyboard Shortcut:**
- Press `Ctrl+Alt+S` (Windows/Linux) or `Cmd+Alt+S` (macOS)

**Menu:**
- Navigate to **StaX → Open StaX Panel**

**Script Editor:**
```python
import nuke_launcher
nuke_launcher.show_stax_panel()
```

### Inserting Assets into Nuke

**Method 1: Drag and Drop**
1. Select element(s) in the StaX panel
2. Drag them into the Node Graph
3. StaX automatically creates:
   - **Read nodes** for 2D images/sequences with correct frame ranges
   - **ReadGeo nodes** for 3D assets (.abc, .obj, .fbx)
   - **Node graphs** for toolsets (.nk files)

**Method 2: Double-Click**
- Double-click any element to insert it into the DAG at the current position

**Method 3: Insert Button**
- Hover over an element while holding `Alt` to show the Media Info Popup
- Click the **"Insert into Nuke"** button

### Registering Toolsets

Save your Nuke node setups as reusable assets:

1. Select nodes in the Node Graph
2. Press `Ctrl+Shift+T` or go to **StaX → Register Toolset**
3. Enter toolset name, select target list, add comment
4. Optional: Generate preview image of node graph
5. StaX saves the .nk file and catalogs it as an element

Toolsets can then be dragged back into any Nuke session.

### Quick Actions

Available in the **StaX** menu:

- **Quick Ingest** (`Ctrl+Shift+I`): Ingest files immediately without opening full dialog
- **Register Toolset** (`Ctrl+Shift+T`): Save selected nodes as toolset
- **Advanced Search** (`Ctrl+F`): Open advanced search dialog

---

## Keyboard Shortcuts

### Global Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+I` | Open Ingest Files dialog |
| `Ctrl+Shift+I` | Open Ingest Library dialog / Quick Ingest |
| `Ctrl+F` | Open Advanced Search |
| `Ctrl+2` | Toggle History Panel |
| `Ctrl+3` | Toggle Settings Panel |
| `Ctrl+L` | Logout |

### Nuke Plugin Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Alt+S` | Open StaX Panel |
| `Ctrl+Shift+T` | Register Selection as Toolset |
| `Ctrl+F` | Advanced Search in StaX Panel |

### Navigation Shortcuts

| Key | Action |
|-----|--------|
| `Alt + Hover` | Show Media Info Popup with preview and metadata |
| `Double-Click` | Insert element into Nuke DAG |
| `Right-Click` | Context menu (Edit, Delete, Add to Favorites/Playlist) |

---

## Configuration

![StaX graph](assets\StaX-settings-standalone.png)

### Database Location

**Environment Variable (Recommended for Studios):**
```bash
# Set before launching Nuke or standalone app
export STOCK_DB=/path/to/shared/database.db
```

**Config File:**

Edit `config/config.json`:
```json
{
    "database_path": "./data/stax.db",
    "default_repository_path": "./repository",
    "preview_dir": "./previews",
    "default_copy_policy": "soft",
    "nuke_mock_mode": false
}
```

### Settings Panel

Open with `Ctrl+3` to configure:

- **General**: Database location, user preferences
- **Ingestion**: Copy policy, sequence detection settings
- **Preview & Media**: Thumbnail size, GIF settings, video preview options
- **Network & Performance**: Database retries/timeout, cache settings, pagination
- **Custom Processors**: Pre-ingest, post-ingest, and post-import hook scripts
- **Security & Admin**: User management, password changes (admin only)

### Custom Processors (Pipeline Integration)

StaX supports custom Python scripts at three points in the workflow:

1. **Pre-Ingest Processor**: Runs before files are copied (validation, naming enforcement)
2. **Post-Ingest Processor**: Runs after cataloging (metadata injection, external system notifications)
3. **Post-Import Processor**: Runs after Nuke node creation (OCIO setup, expression application)

**Example Pre-Ingest Hook:**
```python
# processors/validate_naming.py
import re

# Context contains: {'name': str, 'filepath': str, 'element_data': dict}
if not re.match(r'^[A-Z]{3}_\d{4}', context['name']):
    result = {
        'continue': False,
        'message': 'File name must match pattern: XXX_####'
    }
else:
    result = {'continue': True}
```

Configure processor paths in Settings → Custom Processors tab.

---

## Advanced Features

### Pagination

For large libraries (1000+ assets), enable pagination in Settings → Network & Performance:
- Set items per page (50, 100, 200, 500)
- Navigate with First/Previous/Next/Last buttons
- Improves performance and reduces memory usage

### Preview System

StaX generates three types of previews:
- **Static Thumbnail**: PNG image for quick display
- **Animated GIF**: 3-second loop for hover preview
- **Video Preview**: Low-res MP4 for playback in preview pane (standalone mode)

Hover over elements in gallery view to play GIF previews automatically.

### Network-Aware Database

For multi-user studios:
- SQLite database with file locking prevents conflicts
- Supports concurrent access from multiple workstations
- WAL (Write-Ahead Logging) journal mode for better concurrency
- Configurable retry logic and timeouts

### Tags and Metadata

- Add tags to elements for better searchability (comma-separated)
- Edit metadata: frame range, comment, tags, deprecated status
- Right-click → "Edit Metadata" to update element properties

---

## Troubleshooting

### Nuke Plugin Not Loading

**Check Script Editor output:**
```python
import nuke
print(nuke.pluginPath())
# Should include StaX directory
```

**Verify init.py executed:**
- Look for `[StaX] Plugin loaded from:` message

**Common issues:**
- Missing `PySide2`: Install in Nuke's Python environment
- Wrong `NUKE_PATH`: Verify environment variable points to StaX folder
- Permission errors: Check read/write access to StaX directory

### Database Lock Errors

**Symptoms:**
- "database is locked" error messages

**Solutions:**
1. Close other StaX instances on the same machine
2. Check for stale `.lock` files in database directory
3. Increase retry timeout in Settings → Network & Performance

### Drag & Drop Not Working in Nuke

**Causes:**
1. Running in mock mode (check `nuke_mock_mode` setting)
2. Real Nuke API not detected
3. No elements selected

**Debug:**
```python
# In Nuke Script Editor
import nuke_launcher
print("Nuke mode:", nuke_launcher.NUKE_MODE)
```

---

## Documentation

- **[instructions.md](instructions.md)**: Complete technical specification and architecture
- **[Roadmap.md](Roadmap.md)**: Development phases, milestones, and feature roadmap
- **[changelog.md](changelog.md)**: Version history and release notes

---

## Project Status

**Current Phase:** Beta  
**Python Version:** 2.7 / 3.x (dual compatibility)  
**GUI Framework:** PySide2

**Completed Features:**
- ✅ Database layer with network-aware file locking
- ✅ Ingestion engine with sequence detection
- ✅ Nuke integration (standalone and plugin modes)
- ✅ Extensibility hooks (custom processors)
- ✅ Complete GUI with gallery/list views
- ✅ Preview generation (thumbnails, GIFs, videos)
- ✅ User/permission management
- ✅ Favorites and playlists
- ✅ Advanced search and filtering
- ✅ Drag & drop to Nuke DAG
- ✅ Toolset registration

See [Roadmap.md](Roadmap.md) for planned features and [changelog.md](changelog.md) for recent updates.

---

## Contributing

StaX is under active development. Contributions, bug reports, and feature requests are welcome through GitHub Issues and Pull Requests.

## License

Copyright (c) 2025 Ahmed Ramadan

This project is provided for non-commercial use under the following terms:

- You are free to use, modify, and distribute the software for personal, educational, or non-commercial research and development purposes.
- Commercial use (including distribution, sale, or incorporation into a commercial product or service) is NOT permitted without prior written permission from the copyright holder.

To request commercial licensing or permission, contact the author at the address listed in the project metadata or open an issue on the repository describing your intended commercial use.

If you require a standard open-source license instead (MIT, Apache, GPL, etc.), please contact the maintainer to discuss relicensing options.
