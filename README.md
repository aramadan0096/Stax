# StaX

Advanced solution for mass production stock footage management clone designed for Foundry Nuke integration.

## Project Status

**Phase:** Alpha (MVP) - Core modules implemented  
**Python Version:** 2.7 (VFX pipeline compatibility)  
**GUI Framework:** PySide2

## Features Implemented

### ✅ Core Modules (Alpha MVP - COMPLETE)
- **Database Layer** (`db_manager.py`): SQLite with network-aware file locking
  - Stacks → Lists → Elements hierarchy
  - Favorites and Playlists support
  - Ingestion history tracking
  - Full CRUD operations

- **Ingestion Engine** (`ingestion_core.py`):
  - Automatic image sequence detection
  - Hard copy / soft copy policies
  - Metadata extraction
  - Preview thumbnail generation
  - Multi-file and folder ingestion

- **Nuke Integration** (`nuke_bridge.py`):
  - Mock mode for development without Nuke
  - Read/ReadGeo/Paste node operations
  - Toolset registration
  - Post-import processor hooks

- **Extensibility** (`extensibility_hooks.py`):
  - Pre-ingest processors
  - Post-ingest processors
  - Post-import processors
  - Safe user script execution

- **Configuration** (`config.py`):
  - JSON-based settings
  - User preferences management
  - Auto-detection of user/machine identity

- **GUI Applications**: **✅ COMPLETE (Dual-Mode)**
  
  **Standalone App** (`main.py`):
  - Full-featured desktop application with menubar
  - StacksListsPanel, MediaDisplayWidget, HistoryPanel, SettingsPanel
  - Live search and instant filtering
  - Keyboard shortcuts (Ctrl+2, Ctrl+3, Ctrl+I)
  - Mock Nuke mode for development
  - Independent of Nuke license
  
  **Nuke Plugin** (`nuke_launcher.py`): **✅ NEW**
  - Embeddable QWidget panel for Nuke integration
  - Toolbar-based interface (replaces menubar)
  - Dockable within Nuke's pane system
  - Real Nuke API integration (no mock mode)
  - Drag & drop directly into Node Graph
  - Opens with Ctrl+Alt+S in Nuke
  - All standalone features available
  - See [NUKE_INSTALLATION.md](NUKE_INSTALLATION.md)

### 🚧 In Progress (Beta)
- Drag-and-drop file ingestion from OS
- Advanced search with property/match type selection
- Favorites management UI
- Unit tests

## Quick Start

### Installation

```powershell
# Clone repository
cd d:\Scripts\modern-stock-browser

# Create virtual environment (Python 3 recommended for development)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\activate

# Install dependencies
pip install PySide2 ffpyplayer
```

### Running the Application

**Option 1: Standalone Desktop Application**

```python
# Run standalone GUI application
python main.py
```

**Option 2: Nuke Plugin Integration**

```python
# Copy StaX to Nuke plugins directory
# Windows: C:\Users\<username>\.nuke\StaX
# Linux/Mac: ~/.nuke/StaX

# In Nuke, press Ctrl+Alt+S to open StaX panel
# Or use menu: StaX → Open StaX Panel
```

See [NUKE_INSTALLATION.md](NUKE_INSTALLATION.md) for detailed Nuke setup instructions.

On first run:
1. Database and config files are auto-created
2. Click **"+ Stack"** to create your first stack
3. Click **"+ List"** to add lists to the stack
4. Use **File → Ingest Files** (Ctrl+I) to add assets

See [QUICKSTART.md](QUICKSTART.md) for detailed usage instructions.

### Testing Core Modules (No GUI)

```python
# Run example to test core modules
python example_usage.py
```

This will:
1. Initialize database with schema
2. Create example Stacks and Lists
3. Test Nuke bridge in mock mode
4. Demonstrate sequence detection
5. Show processor hook status

### Directory Structure

```
modern-stock-browser/
├── src/                    # Core Python modules
│   ├── db_manager.py       # Database operations
│   ├── ingestion_core.py   # Ingestion pipeline
│   ├── nuke_bridge.py      # Nuke API abstraction
│   ├── extensibility_hooks.py  # Custom processors
│   └── config.py           # Configuration manager
├── config/                 # Configuration files
│   └── config.json         # Application settings
├── tests/                  # Unit tests (coming soon)
├── data/                   # SQLite database (auto-created)
├── previews/               # Generated thumbnails (auto-created)
├── repository/             # Asset repository (auto-created)
├── instructions.md         # Complete technical specification
├── Roadmap.md              # Development roadmap
└── changelog.md            # Version history
```

## Configuration

Edit `config/config.json` to customize:

```json
{
    "database_path": "./data/vah.db",
    "default_repository_path": "./repository",
    "preview_dir": "./previews",
    "default_copy_policy": "soft",
    "nuke_mock_mode": true,
    "pre_ingest_processor": null,
    "post_ingest_processor": null,
    "post_import_processor": null
}
```

## Development

### Running Tests
```powershell
# Coming soon
python -m pytest tests/
```

### Architecture

The application follows a three-tier architecture:

```
┌─────────────────────────┐
│   GUI Layer (PySide2)   │  ← Coming in Beta
├─────────────────────────┤
│   Core Logic Layer      │  ← ✅ Implemented
│  - Ingestion            │
│  - Extensibility        │
│  - Nuke Bridge          │
├─────────────────────────┤
│   Data Layer (SQLite)   │  ← ✅ Implemented
└─────────────────────────┘
```

### Key Design Patterns

**Dual-Path Asset Storage:**
- `filepath_soft`: Reference to original location
- `filepath_hard`: Physical copy in repository
- `is_hard_copy`: Boolean determines which path to use

**Automatic Sequence Detection:**
- Detects patterns: `filename.####.ext` or `filename_####.ext`
- Automatically discovers frame ranges
- No manual frame range input required

**Nuke Bridge Abstraction:**
- All Nuke operations go through `nuke_bridge.py`
- Mock mode for development/testing
- Real Nuke API in production

## Extensibility

Create custom processor scripts for pipeline integration:

### Pre-Ingest Hook Example
```python
# validate_naming.py
import re

if not re.match(r'^[A-Z]{3}_\d{4}', context['name']):
    result = {
        'continue': False,
        'message': 'File name must match pattern: XXX_####'
    }
else:
    result = {'continue': True}
```

Configure in `config.json`:
```json
{
    "pre_ingest_processor": "./processors/validate_naming.py"
}
```

## Roadmap

- [x] Alpha: Core modules and data layer
- [x] Beta: Complete GUI with PySide2
- [x] RC: Tests, packaging, performance tuning
- [ ] Stable: Production deployment

See [Roadmap.md](Roadmap.md) for detailed milestones.

## Documentation

- **[instructions.md](instructions.md)**: Complete technical specification
- **[Roadmap.md](Roadmap.md)**: Development phases and milestones
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)**: AI agent guidance

## Contributing

This is a greenfield project in active development. Core modules are implemented and ready for GUI integration.

## License

[To be determined]
