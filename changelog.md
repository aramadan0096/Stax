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

### Changed
- Updated `requirements.txt` to include notes for Python 3 development

### Fixed
- N/A

## [0.1.0] - 2025-11-15

### Added
- Repository scaffolding and initial instructions document.
- Initial roadmap and changelog files.



> Notes:
> - Update the Unreleased section while working on changes. When cutting a release, move Unreleased entries under a new version heading with the release date.
> - Link issues or pull requests where applicable using the format: `[#123](https://github.com/your/repo/pull/123)`.
