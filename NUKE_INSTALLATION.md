# StaX Nuke Plugin Installation Guide

This guide explains how to install and use StaX as a Nuke plugin.

## Overview

StaX can run in two modes:
1. **Standalone Application** - Run `main.py` for independent usage
2. **Nuke Plugin** - Integrated panel within Foundry Nuke

## Nuke Plugin Files

The following files enable Nuke integration:

```
modern-stock-browser/
├── init.py              # Nuke startup script (sets plugin paths)
├── menu.py              # Nuke menu configuration
├── nuke_launcher.py     # Nuke panel implementation
├── main.py              # Standalone launcher (kept separate)
└── src/                 # Core modules (shared by both modes)
```

## Installation Methods

### Method 1: User Directory (Single User)

1. **Locate your Nuke user directory:**
   - **Windows:** `C:\Users\<username>\.nuke`
   - **macOS:** `/Users/<username>/.nuke`
   - **Linux:** `/home/<username>/.nuke`

2. **Copy StaX files:**
   ```bash
   # Copy the entire modern-stock-browser folder to .nuke directory
   cp -r modern-stock-browser ~/.nuke/StaX
   ```

3. **Update your `.nuke/init.py`:**
   ```python
   # Add to ~/.nuke/init.py
   import nuke
   import os
   
   # Add StaX plugin path
   stax_path = os.path.join(os.path.dirname(__file__), 'StaX')
   if os.path.isdir(stax_path):
       nuke.pluginAddPath(stax_path)
       print("[StaX] Plugin loaded from: {}".format(stax_path))
   ```

4. **Restart Nuke**

### Method 2: Network Repository (Multi-User)

For VFX studios with shared network storage:

1. **Copy StaX to network location:**
   ```bash
   # Example: Copy to shared storage
   cp -r modern-stock-browser //server/share/nuke_plugins/StaX
   ```

2. **Set environment variable:**
   
   **Windows (PowerShell):**
   ```powershell
   [Environment]::SetEnvironmentVariable("NUKE_PATH", "\\server\share\nuke_plugins\StaX", "User")
   ```
   
   **Linux/macOS (bash):**
   ```bash
   export NUKE_PATH=/server/share/nuke_plugins/StaX
   # Add to ~/.bashrc or ~/.zshrc for persistence
   ```

3. **Alternative: Update facility init.py:**
   ```python
   # In facility-wide init.py (e.g., /opt/nuke/plugins/init.py)
   import nuke
   nuke.pluginAddPath('//server/share/nuke_plugins/StaX')
   ```

4. **Restart Nuke**

### Method 3: NUKE_PATH Environment Variable

1. **Set NUKE_PATH before launching Nuke:**
   
   **Windows:**
   ```powershell
   $env:NUKE_PATH="D:\Scripts\modern-stock-browser"
   & "C:\Program Files\Nuke15.0v1\Nuke15.0.exe"
   ```
   
   **Linux/macOS:**
   ```bash
   export NUKE_PATH="/path/to/modern-stock-browser"
   /usr/local/Nuke15.0v1/Nuke15.0
   ```

## Verification

1. **Launch Nuke**

2. **Check Script Editor output:**
   ```
   [StaX] Plugin paths initialized:
     - Root: /path/to/StaX
   [StaX] Ready to load. Menu will be available after startup.
   [StaX] Menu installed successfully. Press Ctrl+Alt+S to open StaX panel.
   ```

3. **Verify menu exists:**
   - Look for **StaX** menu in the main menu bar
   - Should be between standard Nuke menus

4. **Test plugin path:**
   ```python
   # In Nuke Script Editor:
   import nuke
   print(nuke.pluginPath())
   # Should include StaX directory
   ```

## Usage

### Opening StaX Panel

**Method 1: Keyboard Shortcut**
- Press `Ctrl+Alt+S` (Windows/Linux) or `Cmd+Alt+S` (macOS)

**Method 2: Menu**
- Navigate to: **StaX → Open StaX Panel**

**Method 3: Script Editor**
```python
import nuke_launcher
nuke_launcher.show_stax_panel()
```

### Panel Features

Once the panel is open:

1. **Login:** Enter credentials or continue as guest
2. **Browse Assets:** Navigate Stacks → Lists → Elements
3. **Drag & Drop:** 
   - Drag elements from StaX panel directly into Node Graph
   - Creates Read/ReadGeo nodes automatically with correct frame ranges
4. **Double-Click:** Double-click element to insert into DAG
5. **Preview:** Select element to see preview in right pane
6. **Search:** Use toolbar search button or `Ctrl+F`

### Quick Actions (via Menu)

Available in **StaX** menu:

- **Quick Ingest...** (`Ctrl+Shift+I`) - Ingest files immediately
- **Register Toolset...** (`Ctrl+Shift+T`) - Save selected nodes as toolset
- **Advanced Search...** (`Ctrl+F`) - Search by properties

### Real Nuke Integration

When running in Nuke (not mock mode):

```python
# nuke_launcher.py automatically detects Nuke and disables mock mode
NUKE_MODE = True  # Detected automatically
self.config.set('nuke_mock_mode', False)  # Real Nuke API calls
```

**Features:**
- Creates actual Read/ReadGeo nodes in DAG
- Registers real toolsets from selected nodes
- Pastes node graphs from .nk files
- Automatic frame range detection
- Post-import processor hooks execute

## Configuration

### Database Location

**Option 1: Environment Variable (Recommended for studios)**
```bash
# Set before launching Nuke
export STOCK_DB="//server/share/vfx/stax_production.db"
```

**Option 2: Config File**
```json
// Edit config/config.json
{
  "database_path": "//server/share/vfx/stax_production.db",
  "default_repository_path": "//server/share/repository",
  "nuke_mock_mode": false
}
```

### Nuke-Specific Settings

In Settings panel (Ctrl+3):

- **Custom Processors → Post-Import Hook:**
  - Script executed after inserting nodes into DAG
  - Example: Auto-apply OCIO colorspace
  - Example: Set default expressions

- **Ingestion → Auto-register Renderings:**
  - Hook into Write node callbacks (future feature)
  - Auto-ingest renders when complete

## Troubleshooting

### Panel Doesn't Appear

1. **Check Script Editor for errors:**
   ```python
   # Look for import errors or missing modules
   ```

2. **Verify plugin path:**
   ```python
   import nuke
   print(nuke.pluginPath())
   # Should include StaX directory
   ```

3. **Check init.py executed:**
   ```python
   # Should see [StaX] messages in output
   ```

### Import Errors

**Error:** `ImportError: No module named src.config`

**Solution:** Ensure `src` directory is in plugin path:
```python
# In init.py
nuke.pluginAddPath('./src')
```

### PySide2 Not Available

**Error:** `ImportError: No module named PySide2`

**Solution:** Install PySide2 in Nuke's Python environment:
```bash
# Find Nuke's Python
/path/to/Nuke15.0/python -m pip install PySide2
```

### Database Lock Errors

**Error:** `database is locked`

**Solution:** 
1. Close other StaX instances
2. Check `.lock` file isn't stale
3. Increase timeout in Settings → Network & Performance

### Drag & Drop Not Working

**Symptom:** Dragging elements doesn't create nodes

**Causes:**
1. Running in mock mode (check `nuke_mock_mode` setting)
2. No elements selected
3. Nuke import failed

**Debug:**
```python
# In Nuke Script Editor
import nuke_launcher
panel = nuke_launcher.show_stax_panel()
print("Nuke mode:", nuke_launcher.NUKE_MODE)
print("Mock mode:", panel.config.get('nuke_mock_mode'))
```

## Standalone vs Nuke Mode

| Feature | Standalone (`main.py`) | Nuke Plugin (`nuke_launcher.py`) |
|---------|----------------------|----------------------------------|
| **Launch** | `python main.py` | `Ctrl+Alt+S` in Nuke |
| **Window Type** | QMainWindow with menubar | QWidget panel (dockable) |
| **Mock Mode** | Enabled by default | Disabled (real Nuke API) |
| **Node Creation** | Simulated | Real Read/ReadGeo nodes |
| **Toolset Registration** | Placeholder .nk files | Real node graph export |
| **Use Case** | Asset browsing, management | Live Nuke integration |

**Recommendation:** 
- Use standalone for asset management tasks
- Use Nuke plugin for production work requiring DAG integration

## Advanced Configuration

### Custom Post-Import Processor

Create a script to run after inserting elements:

```python
# ~/.nuke/StaX/processors/post_import.py
"""
Executed after element is inserted into Nuke DAG.
Context: {'element': dict, 'nodes': list, 'nuke': module}
"""

def process(context):
    element = context['element']
    nodes = context['nodes']
    nuke = context['nuke']
    
    # Auto-set colorspace for EXR files
    if element.get('format') == '.exr':
        for node in nodes:
            if node.Class() == 'Read':
                node['colorspace'].setValue('linear')
                print("[Post-Import] Set linear colorspace for: {}".format(element['name']))
    
    return {'success': True}
```

Configure in Settings → Custom Processors → Post-Import Hook.

### Facility-Wide Deployment

For large studios:

1. **Create facility init.py:**
   ```python
   # /opt/nuke_facility/init.py
   import nuke
   import os
   
   # Add facility plugins
   nuke.pluginAddPath('/opt/nuke_facility/plugins')
   
   # Add StaX from shared storage
   stax_path = '//render_farm/tools/StaX'
   if os.path.isdir(stax_path):
       nuke.pluginAddPath(stax_path)
   
   # Set shared database
   os.environ['STOCK_DB'] = '//render_farm/database/stax_prod.db'
   ```

2. **Set NUKE_PATH globally:**
   ```bash
   # In /etc/profile.d/nuke.sh (Linux)
   export NUKE_PATH=/opt/nuke_facility
   ```

3. **Deploy to render farm:**
   - Ensure StaX accessible from render nodes
   - Database on high-speed storage (NAS/SAN)
   - Test file locking under load

## Examples

### Example 1: Quick Asset Insert

```python
# In Nuke Script Editor
import nuke_launcher

# Show panel
panel = nuke_launcher.show_stax_panel()

# Programmatically insert element by ID
panel.nuke_integration.insert_element(element_id=42)
```

### Example 2: Batch Insert from Playlist

```python
# Get all elements from a playlist
playlist_id = 5
elements = panel.db.get_playlist_items(playlist_id)

# Insert all as Read nodes
for item in elements:
    panel.nuke_integration.insert_element(item['element_fk'])
```

### Example 3: Register Custom Toolset

```python
# Select nodes in Node Graph, then:
import nuke_launcher
panel = nuke_launcher.show_stax_panel()
panel.register_toolset()
# Dialog opens to configure name, list, comment
```

## Support

- **Documentation:** See `instructions.md` and `Roadmap.md`
- **Issues:** Report in GitHub Issues
- **Changelog:** See `changelog.md` for version history

## See Also

- [Foundry Nuke Python Developer Guide](https://learn.foundry.com/nuke/developers/)
- [StaX Copilot Instructions](.github/copilot-instructions.md)
- [Build Instructions](tools/BUILD_INSTRUCTIONS.md)
