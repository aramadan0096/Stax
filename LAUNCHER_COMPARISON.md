# StaX Launcher Comparison: Standalone vs Nuke Plugin

## Overview

StaX now supports two launching modes to accommodate different workflows:

1. **Standalone Application** (`main.py`) - Independent desktop application
2. **Nuke Plugin** (`nuke_launcher.py`) - Integrated Nuke panel

Both share the same core functionality but differ in UI presentation and integration depth.

---

## Side-by-Side Comparison

| Feature | Standalone (`main.py`) | Nuke Plugin (`nuke_launcher.py`) |
|---------|------------------------|----------------------------------|
| **Window Type** | `QMainWindow` | `QWidget` |
| **Launch Method** | `python main.py` | `Ctrl+Alt+S` in Nuke |
| **Menubar** | Full menubar (File, Search, Nuke, View, Help) | No menubar (replaced with toolbar) |
| **Toolbar** | No toolbar | Full toolbar with all actions |
| **Status Bar** | QStatusBar at bottom | QLabel status indicator |
| **Dockable Panels** | QDockWidget (History, Settings) | QDialog popups |
| **Keyboard Shortcuts** | QShortcut objects | Menu-driven shortcuts |
| **Mock Mode Default** | Enabled (True) | Disabled (False when in Nuke) |
| **Node Creation** | Simulated (logs only) | Real Nuke API calls |
| **Panel Integration** | N/A | Dockable with `nukescripts.panels` |
| **Startup** | Direct instantiation | `show_stax_panel()` function |

---

## Architecture Differences

### Standalone (`main.py`)

```python
class MainWindow(QtWidgets.QMainWindow):
    """Full-featured desktop application."""
    
    def __init__(self):
        # Traditional QMainWindow setup
        self.setWindowTitle("Stax")
        self.setup_ui()
        self.create_menus()     # Menubar
        self.setup_shortcuts()  # QShortcut objects
        
    def create_menus(self):
        """Create menubar with File, Search, Nuke, View, Help menus."""
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        # ... 5 menus with actions
```

**Key Components:**
- **Menu System:** Full menubar with dropdowns
- **Dockable Panels:** History and Settings as QDockWidgets
- **Status Bar:** QStatusBar with showMessage()
- **Window Controls:** Minimize, maximize, close

### Nuke Plugin (`nuke_launcher.py`)

```python
class StaXPanel(QtWidgets.QWidget):
    """Embeddable panel for Nuke integration."""
    
    def __init__(self, parent=None):
        # QWidget setup (no window frame)
        self.setWindowTitle("StaX")
        self.setup_ui()  # No menus, uses toolbar
        
    def create_toolbar(self):
        """Create toolbar with all actions."""
        toolbar = QtWidgets.QToolBar("Main Toolbar")
        # All actions as toolbar buttons
        return toolbar
```

**Key Components:**
- **Toolbar:** Single toolbar with icon buttons
- **Dialog Panels:** History and Settings as modal QDialogs
- **Status Label:** QLabel with setText()
- **Panel Registration:** `nukescripts.panels.registerWidgetAsPanel()`

---

## UI Layout Comparison

### Standalone Layout

```
┌─────────────────────────────────────────────────────┐
│ File  Search  Nuke  View  Help              [_ □ X] │ ← Menubar
├─────────────────────────────────────────────────────┤
│ ┌──────────┬────────────────────┬─────────────────┐ │
│ │ Stacks/  │  Media Display     │ Video Player    │ │
│ │ Lists    │  (Gallery/Table)   │ Preview Pane    │ │
│ │          │                    │                 │ │
│ │          │                    │                 │ │
│ └──────────┴────────────────────┴─────────────────┘ │
├─────────────────────────────────────────────────────┤
│ Ready                                               │ ← Status Bar
└─────────────────────────────────────────────────────┘

Optional Dockable Panels:
┌─────────────────────┐  ┌─────────────────────┐
│ History Panel       │  │ Settings Panel      │
│ (Ctrl+2)            │  │ (Ctrl+3)            │
└─────────────────────┘  └─────────────────────┘
```

### Nuke Plugin Layout

```
┌─────────────────────────────────────────────────────┐
│ [↑][📁][🔍][+][⏱][⚙]  User: admin (Admin) [Logout] │ ← Toolbar
├─────────────────────────────────────────────────────┤
│ ┌──────────┬────────────────────┬─────────────────┐ │
│ │ Stacks/  │  Media Display     │ Video Player    │ │
│ │ Lists    │  (Gallery/Table)   │ Preview Pane    │ │
│ │          │                    │                 │ │
│ │          │                    │                 │ │
│ └──────────┴────────────────────┴─────────────────┘ │
├─────────────────────────────────────────────────────┤
│ Ready                                               │ ← Status Label
└─────────────────────────────────────────────────────┘

Nuke Integration:
- Panel docks in Nuke's pane system
- Can be moved/resized alongside Node Graph
- Drag & drop directly into DAG
```

---

## Functional Differences

### 1. Nuke Integration

**Standalone:**
```python
# main.py - Mock mode enabled
self.nuke_bridge = NukeBridge(mock_mode=True)

# Node creation logs to console
def on_element_double_clicked(self, element_id):
    self.nuke_integration.insert_element(element_id)
    # Output: [NukeBridge] Mock: Would create Read node...
```

**Nuke Plugin:**
```python
# nuke_launcher.py - Mock mode disabled in Nuke
if NUKE_MODE:
    self.config.set('nuke_mock_mode', False)
self.nuke_bridge = NukeBridge(mock_mode=False)

# Node creation uses real Nuke API
def on_element_double_clicked(self, element_id):
    self.nuke_integration.insert_element(element_id)
    # Creates actual Read node in DAG
    nuke.message("Element inserted into node graph")
```

### 2. Menu Access

**Standalone:**
```
File Menu:
  ├─ Ingest Files... (Ctrl+I)
  ├─ Ingest Library... (Ctrl+Shift+I)
  ├─ Logout (Ctrl+L)
  └─ Exit (Ctrl+Q)

Search Menu:
  └─ Advanced Search... (Ctrl+F)

Nuke Menu:
  └─ Register Selection as Toolset... (Ctrl+Shift+T)

View Menu:
  ├─ History Panel (Ctrl+2)
  └─ Settings Panel (Ctrl+3)
```

**Nuke Plugin:**
```
StaX Menu (in Nuke):
  ├─ Open StaX Panel (Ctrl+Alt+S)
  ├─ Quick Ingest... (Ctrl+Shift+I)
  ├─ Register Toolset... (Ctrl+Shift+T)
  └─ Advanced Search... (Ctrl+F)

Toolbar Icons:
  [↑] Ingest Files
  [📁] Ingest Library
  [🔍] Advanced Search
  [+] Register Toolset
  [⏱] History
  [⚙] Settings
```

### 3. Panel Behavior

**Standalone - Dockable Panels:**
```python
# History panel as QDockWidget
self.history_dock = QtWidgets.QDockWidget("History", self)
self.history_dock.setVisible(False)
self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)

# Toggle visibility
def toggle_history(self):
    visible = not self.history_dock.isVisible()
    self.history_dock.setVisible(visible)
```

**Nuke Plugin - Modal Dialogs:**
```python
# History panel as QDialog
def show_history(self):
    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle("Ingestion History")
    layout = QtWidgets.QVBoxLayout(dialog)
    history_panel = HistoryPanel(self.db)
    layout.addWidget(history_panel)
    dialog.exec_()  # Modal
```

---

## Code Sharing

Both launchers share 95% of their code through the `src/` module:

### Shared Modules

```python
# Both import identical core modules
from src.config import Config
from src.db_manager import DatabaseManager
from src.ingestion_core import IngestionCore
from src.nuke_bridge import NukeBridge, NukeIntegration
from src.extensibility_hooks import ProcessorManager

# Both use same UI widgets
from src.ui import (
    StacksListsPanel,
    MediaDisplayWidget,
    HistoryPanel,
    SettingsPanel,
    # ... all dialogs
)
```

### Unique Code

**Standalone-Only:**
- `create_menus()` method
- `setup_shortcuts()` method
- QDockWidget initialization
- QStatusBar usage

**Nuke-Only:**
- `create_toolbar()` method
- `show_stax_panel()` function
- `NUKE_MODE` detection
- `nukescripts.panels.registerWidgetAsPanel()`
- User label in toolbar

---

## Use Case Recommendations

### Use Standalone When:

1. **Asset Management Focus**
   - Browsing large asset libraries
   - Bulk ingestion operations
   - Database administration
   - User management tasks

2. **Multi-Monitor Setups**
   - Dedicated screen for asset browser
   - Multiple windows open simultaneously
   - Full desktop application experience

3. **Testing & Development**
   - Developing custom processors
   - Testing ingestion workflows
   - Database migrations
   - Preview generation testing

4. **Non-Nuke Workflows**
   - Pre-production asset organization
   - Asset QC and tagging
   - Playlist curation
   - Catalog exploration

### Use Nuke Plugin When:

1. **Production Work**
   - Active compositing sessions
   - Real-time asset insertion
   - Node graph integration
   - Toolset registration from DAG

2. **Workflow Integration**
   - Drag & drop into node graph
   - Auto-frame range detection
   - Post-import processor execution
   - Nuke-specific features

3. **Space-Constrained Environments**
   - Single monitor workstations
   - Dockable panel convenience
   - Integrated within Nuke UI
   - Minimize context switching

4. **Collaborative Sessions**
   - Screen sharing (single app)
   - Pipeline demonstrations
   - Training new artists
   - Studio standardization

---

## Performance Considerations

| Aspect | Standalone | Nuke Plugin |
|--------|-----------|-------------|
| **Startup Time** | Fast (~1-2s) | Medium (~2-3s with Nuke) |
| **Memory Usage** | ~200-300 MB | ~150-250 MB (shared with Nuke) |
| **Database Access** | Direct | Shared with Nuke environment |
| **Preview Loading** | Optimized (full CPU) | Shared resources with Nuke |
| **Background Tasks** | Full threading | Must not block Nuke UI |

---

## Migration Between Modes

### From Standalone to Nuke Plugin

```python
# Standalone usage
python main.py

# ↓ Switch to Nuke plugin ↓

# In Nuke:
# 1. Copy StaX to ~/.nuke/StaX
# 2. Restart Nuke
# 3. Press Ctrl+Alt+S
```

**Benefits:**
- Same database (seamless transition)
- All stacks/lists preserved
- User sessions continue
- No data migration needed

### From Nuke Plugin to Standalone

```python
# In Nuke: Using StaX panel

# ↓ Switch to standalone ↓

# In terminal:
cd /path/to/StaX
python main.py
```

**Benefits:**
- Independent of Nuke license
- Faster for asset-only tasks
- Full window management
- Can run on different machine

---

## Summary

Both launchers provide complete StaX functionality with different UX approaches:

- **`main.py`**: Traditional desktop application with menubars and dockable panels
- **`nuke_launcher.py`**: Streamlined Nuke panel with toolbar and modal dialogs

**Key Insight:** The modular UI refactoring (Session 6) makes maintaining both launchers efficient - shared widgets in `src/ui/`, launcher-specific code in respective files.

**Recommendation for Studios:**
- Deploy both modes
- Use standalone for librarians/coordinators
- Use Nuke plugin for artists in production
- Share single database on network storage
