# Changelog

All notable changes to this project will be documented in this file.

The format is based on "Keep a Changelog" and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- Initial project documentation files: `Roadmap.md`, `changelog.md`.
- Added `instructions.md` updates directing creation and maintenance of project docs.
- Created project structure with `src/`, `tests/`, `config/` directories.
- Implemented `db_manager.py` with complete SQLite schema and CRUD operations.
- Implemented `ingestion_core.py` with sequence detection, metadata extraction, and preview generation.
- Implemented `nuke_bridge.py` with mock mode for development without Nuke.
- Implemented `extensibility_hooks.py` for custom processor architecture.
- Implemented `config.py` for application configuration management.
- Added `example_usage.py` to demonstrate core module usage.
- Created `requirements.txt` with Python 2.7 compatible dependencies.
- Added `.github/copilot-instructions.md` for AI agent guidance.
- **Implemented `gui_main.py` - Complete PySide2 GUI application** (Alpha MVP complete):
  - StacksListsPanel: Tree view for navigating Stacks and Lists
  - MediaDisplayWidget: Gallery and List view modes with live search
  - HistoryPanel: Ingestion history display with CSV export
  - SettingsPanel: Configuration UI for all app settings
  - MainWindow: Complete application with menu bar, status bar, and keyboard shortcuts
  - Drag-and-drop file ingestion workflow
  - Element double-click to insert into Nuke (mock mode)
  - Toggleable panels (Ctrl+2 for History, Ctrl+3 for Settings)
- **Implemented Media Info Popup (Alt+Hover)**:
  - Non-modal popup triggered by holding Alt while hovering over elements
  - Large preview display (380x280px with aspect ratio preservation)
  - Complete metadata display: name, type, format, frames, size, path, comment
  - "Insert into Nuke" button for quick insertion
  - "Reveal in Explorer" button to open file location in OS
  - Dark themed UI with styled buttons
  - Auto-positioning near cursor with offset
  - Click-to-close behavior
- **Implemented Advanced Search Dialog** (Beta feature):
  - Property-based search: name, format, type, comment, tags
  - Match type selection: loose (LIKE) vs strict (exact)
  - Results table with sortable columns
  - Double-click to insert element into Nuke
  - Keyboard shortcut: Ctrl+F
  - Accessible via Search menu
  - Non-modal dialog for continuous searching

### Changed
- Updated `requirements.txt` to include notes for Python 3 development

### Fixed
- Fixed eventFilter initialization race condition in MediaInfoPopup causing AttributeError
- Added hasattr guards to prevent accessing table_view/gallery_view before widget initialization

## [0.1.0] - 2025-11-15

### Added
- Repository scaffolding and initial instructions document.
- Initial roadmap and changelog files.



> Notes:
> - Update the Unreleased section while working on changes. When cutting a release, move Unreleased entries under a new version heading with the release date.
> - Link issues or pull requests where applicable using the format: `[#123](https://github.com/your/repo/pull/123)`.
