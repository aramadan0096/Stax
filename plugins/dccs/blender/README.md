# StaX Blender Plugin

This is the StaX plugin for Blender, implementing the architecture described in the StaX DCC Plugin Integration Plan. It provides a complete integration of the StaX asset management system into Blender.

## Features

- **Two-Stage Loading**: Minimal initialization on startup, full UI loaded on demand
- **IPC Communication**: Remote command execution from StaX Core application
- **OS-Level Window Re-Parenting**: Seamless integration into Blender's UI
- **Non-Blocking Event Loop**: Qt event processing synchronized with Blender's main loop
- **Thread-Safe Command Execution**: All DCC API calls marshaled to main thread
- **Reference Management**: Prevents widget garbage collection
- **Cross-Platform Support**: Windows, Linux, and macOS (with platform-specific implementations)

## Architecture Components

### 1. IPC Server (`ipc_server.py`)
- TCP-based communication between StaX Core and Blender
- Thread-safe command queue with main thread marshaling
- Automatic port assignment based on process ID

### 2. DCC Base Mixin (`dcc_base.py`)
- Universal base class for DCC integrations
- Reference Manager to prevent widget garbage collection
- Dynamic Qt binding detection (PySide/PySide2, Shiboken/Shiboken2)

### 3. Blender Integration (`integration.py`)
- OS-level window handle retrieval (Windows/Linux/macOS)
- Window re-parenting using platform-specific APIs
- Non-blocking event loop using Blender's timer system
- Input filter to preserve Blender navigation shortcuts

### 4. Blender Bridge (`bridge.py`)
- Abstraction layer for Blender API operations
- Mock mode for development/testing
- Mesh and image import functions

### 5. Blender Panel (`panel.py`)
- Main UI panel implementation
- Full StaX functionality (ingestion, search, browsing)
- Integration with Blender scene operations

## Installation

### Prerequisites

1. **Blender 2.80+** (tested with 2.80, 2.90, 3.0+)
2. **Python 2.7 or 3.x** (depending on Blender version)
3. **PySide2** (bundled or system-installed)
4. **Platform-specific dependencies**:
   - **Windows**: `pywin32` (for window handle manipulation)
   - **Linux**: `python-xlib` (for X11 window management)
   - **macOS**: PyObjC (for Cocoa window management) - *not yet implemented*

### Installation Steps

1. **Copy the plugin to Blender's addons directory:**
   ```bash
   # Windows
   %APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\stax_blender\
   
   # Linux
   ~/.config/blender/<version>/scripts/addons/stax_blender/
   
   # macOS
   ~/Library/Application Support/Blender/<version>/scripts/addons/stax_blender/
   ```

2. **Or install as a zip file:**
   - Package the `plugins/dccs/blender/` directory as a zip
   - In Blender: Edit > Preferences > Add-ons > Install from File
   - Select the zip file

3. **Enable the addon:**
   - In Blender: Edit > Preferences > Add-ons
   - Search for "StaX"
   - Enable the "StaX Asset Manager" addon

4. **Configure dependencies:**
   - Ensure PySide2 is available in Blender's Python environment
   - If using bundled dependencies, set `STAX_PLUGIN_ROOT` environment variable
   - Install platform-specific dependencies (win32gui, python-xlib, etc.)

## Usage

### Opening the Panel

1. **Via Menu**: Window > StaX > Open Browser
2. **Via Operator**: Press `F3` (Search), type "Open StaX"
3. **Via IPC**: Send command from StaX Core application

### Features

- **Browse Assets**: Navigate stacks, lists, and elements
- **Search**: Advanced search with filters
- **Ingest Files**: Add files to StaX library
- **Insert Elements**: Double-click elements to import into Blender scene
- **Favorites**: Quick access to favorited assets
- **Playlists**: Organize assets into playlists

### IPC Commands

The plugin accepts remote commands via IPC:

```python
from plugins.dccs.blender.ipc_server import IPCClient

# Find Blender's port
port = IPCClient.find_blender_port()

# Send command
response = IPCClient.send_command(
    "stax.blender.gui.launch_browser_panel",
    port=port
)

# Insert element
response = IPCClient.send_command(
    "stax.blender.gui.insert_element",
    args=[element_id],
    port=port
)
```

## Technical Details

### Two-Stage Loading

**Stage 1 (Initialization):**
- Minimal imports
- IPC server startup
- Menu registration
- No heavy PySide imports

**Stage 2 (Deferred Load):**
- Triggered on first user action
- Full PySide imports
- UI creation
- Event loop setup

### Event Loop Synchronization

The plugin uses Blender's modal timer operator to process Qt events:

```python
# Registered as: wm.stax_event_loop
# Runs at 100Hz (10ms intervals)
# Calls: QApplication.processEvents(QEventLoop.AllEvents, 1)
```

This ensures GUI responsiveness without blocking Blender's main thread.

### Window Re-Parenting

**Windows:**
- Uses `win32gui.SetParent()` and `SetWindowLong()`
- Converts widget to child window style

**Linux:**
- Uses X11 `XReparentWindow()` API
- Requires Xlib Python bindings

**macOS:**
- *Not yet implemented* (requires PyObjC/Cocoa integration)

### Thread Safety

All IPC commands are queued and executed on Blender's main thread:

1. IPC server thread receives command
2. Command enqueued to thread-safe queue
3. Main thread processes queue via `process_commands()`
4. Result returned to IPC client

## Troubleshooting

### Panel doesn't appear
- Check Blender console for errors
- Verify PySide2 is available: `import PySide2` in Blender's Python console
- Check addon is enabled in Preferences

### Window re-parenting fails
- **Windows**: Install `pywin32`: `pip install pywin32`
- **Linux**: Install `python-xlib`: `pip install python-xlib`
- Verify Blender window is visible and not minimized

### IPC server not responding
- Check port file exists: `%TEMP%\stax_blender_port_<PID>.txt`
- Verify firewall allows localhost connections
- Check Blender console for IPC server errors

### Event loop not working
- Verify modal timer operator is registered: `bpy.ops.wm.stax_event_loop`
- Check Blender console for timer errors
- Ensure QApplication instance exists

## Development

### Testing Outside Blender

The plugin can run in mock mode for development:

```python
# Set environment variable
import os
os.environ['BLENDER_MOCK_MODE'] = '1'

# Import and test
from plugins.dccs.blender.panel import StaXBlenderPanel
panel = StaXBlenderPanel()
```

### Debugging

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check console output for:
- `[blender_panel]` - Panel initialization
- `[BlenderIntegration]` - Integration operations
- `[IPCServer]` - IPC communication
- `[ReferenceManager]` - Widget lifecycle

## Future Enhancements

- [ ] macOS window re-parenting implementation
- [ ] Native Blender panel integration (without re-parenting)
- [ ] Blender-specific asset types (materials, shaders, etc.)
- [ ] Scene export to StaX library
- [ ] Batch import operations
- [ ] Performance optimizations for large asset libraries

## References

- [StaX DCC Plugin Integration Plan](../../../examples/StaX%20DCC%20Plugin%20Integration%20Plan.md)
- [Blender Python API Documentation](https://docs.blender.org/api/current/)
- [PySide2 Documentation](https://doc.qt.io/qtforpython/)

