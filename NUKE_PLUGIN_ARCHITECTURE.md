# StaX Nuke Plugin Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         NUKE APPLICATION                                   │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                       Nuke Menu Bar                                   │ │
│  │  File  Edit  Render  Comp  StaX  Windows  Help                       │ │
│  │                              ▲                                        │ │
│  │                              │                                        │ │
│  │                              └─── Added by menu.py                    │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────┬─────────────────────────────────────────────┐  │
│  │   Node Graph         │   StaX Panel (Ctrl+Alt+S)                   │  │
│  │                      │                                              │  │
│  │  ┌─────┐             │  ┌──────────────────────────────────────┐  │  │
│  │  │Read1│             │  │ [↑][📁][🔍] User: admin     [Logout]│  │  │
│  │  └─────┘             │  ├──────────────────────────────────────┤  │  │
│  │     ▲                │  │ ┌───────┬────────────┬──────────┐   │  │  │
│  │     │ Created by     │  │ │Stacks │  Gallery   │ Preview  │   │  │
│  │     │ drag & drop    │  │ │ Lists │   View     │  Pane    │   │  │
│  │     │                │  │ │       │            │          │   │  │
│  │  ┌─────┐             │  │ │  📁   │  🖼️🖼️🖼️  │  ▶️      │   │  │
│  │  │Read2│◄────────────┼──┼─┤  📁   │  🖼️🖼️🖼️◄─┼──────────┤   │  │
│  │  └─────┘ Double-click│  │ │  📁   │  🖼️🖼️🖼️  │ Video    │   │  │
│  │                      │  │ │       │            │ Preview  │   │  │
│  │                      │  │ └───────┴────────────┴──────────┘   │  │
│  │                      │  │ Status: Ready                        │  │
│  │                      │  └──────────────────────────────────────┘  │  │
│  │                      │         ▲                                   │  │
│  │                      │         │                                   │  │
│  │                      │         └─── Registered by                 │  │
│  │                      │              nuke_launcher.py               │  │
│  └──────────────────────┴─────────────────────────────────────────────┘  │
│                                                                            │
└───────────────────────────────────────────────────────────────────────────┘
```

## Component Interaction Flow

```
1. NUKE STARTUP
   ↓
   Loads ~/.nuke/StaX/init.py
   ↓
   Adds plugin paths:
   - StaX root
   - src/
   - resources/
   ↓
   Loads ~/.nuke/StaX/menu.py
   ↓
   Creates "StaX" menu with commands

2. USER ACTION: Press Ctrl+Alt+S
   ↓
   Menu command executes:
   import nuke_launcher
   nuke_launcher.show_stax_panel()
   ↓
   Creates StaXPanel(QWidget)
   ↓
   Registers with nukescripts.panels
   ↓
   Panel appears as dockable pane

3. USER ACTION: Drag element from StaX to Node Graph
   ↓
   DragGalleryView.startDrag()
   ↓
   Sets QMimeData with element info
   ↓
   Node Graph receives drop event
   ↓
   nuke_bridge.create_read_node()
   ↓
   Real Read node created with frame range

4. USER ACTION: Double-click element
   ↓
   MediaDisplayWidget emits signal
   ↓
   StaXPanel.on_element_double_clicked()
   ↓
   nuke_integration.insert_element()
   ↓
   Creates node at current cursor position
```

## File Loading Sequence

```
Nuke Launch
  │
  ├─► init.py (Startup - All modes)
  │    │
  │    ├─► nuke.pluginAddPath(StaX_root)
  │    ├─► nuke.pluginAddPath('./src')
  │    └─► nuke.pluginAddPath('./resources')
  │
  ├─► menu.py (Startup - GUI mode only)
  │    │
  │    └─► Creates StaX menu
  │         └─► Adds commands with shortcuts
  │
  └─► User presses Ctrl+Alt+S
       │
       └─► nuke_launcher.py loads
            │
            ├─► Imports src.config
            ├─► Imports src.db_manager
            ├─► Imports src.nuke_bridge
            ├─► Imports src.ui modules
            │
            ├─► Creates StaXPanel instance
            │    │
            │    ├─► Disables mock mode
            │    ├─► Creates toolbar
            │    ├─► Creates panels
            │    └─► Shows login dialog
            │
            └─► Registers panel with Nuke
                 └─► Panel docks in pane system
```

## Database & File System Architecture

```
Network Storage (Shared)
  │
  ├─► //server/share/stax_prod.db ◄─── STOCK_DB env variable
  │     │
  │     ├─── Users table
  │     ├─── Stacks table
  │     ├─── Lists table
  │     ├─── Elements table
  │     └─── History table
  │
  ├─► //server/share/repository/ ◄─── Hard copies
  │     │
  │     ├─── stack_001/
  │     │     └─── list_001/
  │     │           └─── element_001.exr
  │     └─── stack_002/
  │
  └─► //server/share/previews/ ◄─── Generated previews
        │
        ├─── element_001.png (thumbnail)
        ├─── element_001.gif (animation)
        └─── element_001.mp4 (video preview)

Multiple Workstations Access
  │
  ├─► Workstation 1 (Artist A)
  │     └─► Nuke + StaX Panel
  │           └─► Database connection with file lock
  │
  ├─► Workstation 2 (Artist B)
  │     └─► Nuke + StaX Panel
  │           └─► Waits for lock, then connects
  │
  └─► Workstation 3 (Coordinator)
        └─► Standalone StaX (main.py)
              └─► Manages assets independently
```

## Data Flow: Element Insertion

```
User Action: Drag element "explosion.exr" from StaX to Node Graph
  │
  ├─► 1. MediaDisplayWidget detects drag start
  │     │
  │     └─► DragGalleryView.startDrag()
  │          │
  │          └─► Creates QMimeData
  │               ├─ element_id: 42
  │               ├─ element_type: "2D"
  │               └─ filepath: "//server/repo/explosion.1001-1150.exr"
  │
  ├─► 2. Node Graph receives drop
  │     │
  │     └─► Nuke processes drop event
  │          └─► Extracts element data from MIME
  │
  ├─► 3. StaXPanel.on_element_double_clicked(42)
  │     │
  │     └─► nuke_integration.insert_element(42)
  │          │
  │          ├─► db.get_element_by_id(42)
  │          │    └─► Returns element dict
  │          │
  │          ├─► Determine element type: "2D"
  │          │
  │          ├─► nuke_bridge.create_read_node()
  │          │    │
  │          │    └─► nuke.createNode("Read")
  │          │         ├─ file: "//server/repo/explosion.####.exr"
  │          │         ├─ first: 1001
  │          │         ├─ last: 1150
  │          │         └─ colorspace: "linear"
  │          │
  │          └─► Post-import processor (if configured)
  │               └─► Custom script executes
  │                    └─► Sets OCIO, adds expressions, etc.
  │
  └─► 4. Result
       │
       └─► Read node appears in Node Graph
            └─► Connected to current selection (if any)
```

## Code Module Dependencies

```
nuke_launcher.py (Nuke Panel)
  │
  ├─► PySide2.QtWidgets (UI framework)
  │
  ├─► nuke (Nuke Python API)
  │    └─► Only if NUKE_MODE = True
  │
  ├─► nukescripts (Nuke scripting)
  │    └─► panels.registerWidgetAsPanel()
  │
  ├─► src.config (Config)
  │    └─► Reads config.json, env variables
  │
  ├─► src.db_manager (DatabaseManager)
  │    └─► SQLite operations with file locking
  │
  ├─► src.ingestion_core (IngestionCore)
  │    └─► File operations, preview generation
  │
  ├─► src.nuke_bridge (NukeBridge, NukeIntegration)
  │    │
  │    ├─► NukeBridge: Node creation API
  │    │    └─► create_read_node()
  │    │    └─► create_read_geo_node()
  │    │    └─► paste_nodes_from_file()
  │    │
  │    └─► NukeIntegration: High-level operations
  │         └─► insert_element()
  │
  ├─► src.extensibility_hooks (ProcessorManager)
  │    └─► Executes custom user scripts
  │
  ├─► src.icon_loader (get_icon)
  │    └─► Loads SVG icons from resources/
  │
  ├─► src.video_player_widget (VideoPlayerWidget)
  │    └─► ffpyplayer-based video preview
  │
  └─► src.ui (All UI Widgets)
       │
       ├─── StacksListsPanel (Tree navigation)
       ├─── MediaDisplayWidget (Gallery/Table views)
       ├─── HistoryPanel (Ingestion log)
       ├─── SettingsPanel (Configuration UI)
       └─── Dialogs (Login, Search, Ingest, etc.)
```

## Comparison: Standalone vs Nuke Plugin

```
┌─────────────────────────────────────────────────────────────────────┐
│                     STANDALONE (main.py)                             │
├─────────────────────────────────────────────────────────────────────┤
│  QMainWindow                                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ File  Search  Nuke  View  Help                          [_ □ X] │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │ ┌─────────┬────────────────┬────────────┐                     │  │
│  │ │ Stacks  │    Gallery     │   Video    │                     │  │
│  │ │ Lists   │     View       │  Preview   │                     │  │
│  │ └─────────┴────────────────┴────────────┘                     │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │ Status: Ready                                                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Dockable Panels:                                                   │
│  ┌──────────────┐  ┌──────────────┐                               │
│  │   History    │  │   Settings   │                               │
│  │   (Ctrl+2)   │  │   (Ctrl+3)   │                               │
│  └──────────────┘  └──────────────┘                               │
│                                                                      │
│  Features:                                                          │
│  ✓ Full menubar with 5 menus                                       │
│  ✓ Dockable panels (QDockWidget)                                   │
│  ✓ Status bar (QStatusBar)                                         │
│  ✓ Independent window                                              │
│  ✓ Mock Nuke mode (simulated nodes)                                │
│  ✓ Minimize/Maximize/Close buttons                                 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              NUKE PLUGIN (nuke_launcher.py)                          │
├─────────────────────────────────────────────────────────────────────┤
│  QWidget (Dockable Panel)                                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ [↑][📁][🔍][+][⏱][⚙]  User: admin (Admin)  [Logout]          │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │ ┌─────────┬────────────────┬────────────┐                     │  │
│  │ │ Stacks  │    Gallery     │   Video    │                     │  │
│  │ │ Lists   │     View       │  Preview   │                     │  │
│  │ └─────────┴────────────────┴────────────┘                     │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │ Status: Ready                                                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Modal Dialogs:                                                     │
│  ┌──────────────┐  ┌──────────────┐                               │
│  │   History    │  │   Settings   │                               │
│  │   Dialog     │  │   Dialog     │                               │
│  └──────────────┘  └──────────────┘                               │
│                                                                      │
│  Features:                                                          │
│  ✓ Toolbar with icon buttons                                       │
│  ✓ Modal dialogs (QDialog)                                         │
│  ✓ Status label (QLabel)                                           │
│  ✓ Dockable in Nuke panes                                          │
│  ✓ Real Nuke API (creates actual nodes)                            │
│  ✓ Drag & drop into Node Graph                                     │
│  ✓ Opens with Ctrl+Alt+S                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## Summary

The Nuke plugin architecture seamlessly integrates StaX into the Nuke environment while maintaining complete feature parity with the standalone application. Key design decisions:

1. **QWidget vs QMainWindow**: Panel can dock in Nuke's pane system
2. **Toolbar vs Menubar**: Consistent with Nuke's UI patterns
3. **Modal Dialogs vs Dockable**: Simpler for panel context
4. **Shared Modules**: 95% code reuse through src/ modules
5. **Mock Mode Toggle**: Automatic based on environment detection

This architecture allows studios to:
- Deploy both modes simultaneously
- Use same database and repository
- Switch between modes seamlessly
- Scale from single workstations to render farms
