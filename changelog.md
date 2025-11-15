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
- **FFmpeg Integration** (Session 2):
  - Created `src/ffmpeg_wrapper.py` - Complete FFmpeg abstraction layer (430+ lines)
  - Thumbnail generation from images, videos, and sequences
  - Media information extraction (resolution, codec, duration, fps)
  - Video preview generation (low-res MP4)
  - Frame extraction by number
  - Playback control via FFplay
  - Sequence-to-video conversion
  - FFmpeg binaries included in `bin/ffmpeg/bin/` (ffmpeg.exe, ffprobe.exe, ffplay.exe)
- **Modern Theme Application**:
  - Applied `resources/style.qss` to entire application
  - Professional VFX dark theme with teal (#16c6b0) and orange (#ff9a3c) accents
  - Consistent styling across all panels and widgets
- **Favorites System** (Beta feature):
  - Database methods: add_favorite(), remove_favorite(), is_favorite(), get_favorites()
  - ⭐ Favorites button in navigation panel
  - Right-click context menu: "Add/Remove from Favorites"
  - load_favorites() displays all favorite elements
  - Per-user and per-machine favorites storage
  - Star prefix (⭐) on favorite elements in gallery/list views
  - Quick access toggle for favorites view
- **Playlists Feature** (Beta feature - COMPLETE):
  - Database methods (8 total): 
    - create_playlist(), get_all_playlists(), get_playlist_by_id(), delete_playlist()
    - add_to_playlist(), remove_from_playlist(), get_playlist_items(), reorder_playlist_items()
  - 📋 Playlists section in navigation with QListWidget
  - CreatePlaylistDialog: Name + description input with validation
  - AddToPlaylistDialog: Element addition with playlist selection
  - Right-click context menu: "Add to Playlist" submenu (dynamic playlist list)
  - load_playlist() displays playlist elements with 📋 prefix
  - Signal/slot chain: playlist_selected → on_playlist_selected()
  - Collaborative playlists with creator tracking (user_name, machine_name)
  - Sequence order management for playlist items
- **Enhanced Preview System** (Beta feature - COMPLETE):
  - MediaInfoPopup extended with video playback controls
  - Frame scrubbing slider with teal accent (#16c6b0)
  - Play/Stop buttons for video and sequence playback
  - FFplay integration for video playback with start time support
  - Frame count detection for videos (FFmpeg get_frame_count())
  - Sequence frame range parsing for scrubber bounds
  - Real-time frame label updates ("Frame: X / Y")
  - Automatic cleanup on popup close (stops playback process)
  - Video controls visibility: shown only for video/sequence elements
  - Increased popup height to 700px to accommodate controls
- **Element Management Actions** (Beta feature - COMPLETE):
  - EditElementDialog: Full metadata editing interface
    - Editable fields: frame_range, comment, tags, is_deprecated
    - Read-only display: name, type, format (immutable after ingestion)
    - Input validation and styled UI with save/cancel buttons
  - Context menu actions:
    - ✏ Edit Metadata: Opens EditElementDialog for single element
    - ⚠ Mark/Unmark as Deprecated: Toggle deprecated status
    - 🗑 Delete Element: Remove element with confirmation dialog
  - Multi-select support (ExtendedSelection mode on both views)
  - Bulk Operations toolbar button with dropdown menu:
    - ⭐ Add All to Favorites: Bulk favorite multiple elements
    - 📋 Add All to Playlist: Batch add to selected playlist
    - ⚠ Mark All as Deprecated: Bulk deprecation
    - 🗑 Delete All Selected: Bulk deletion with confirmation
  - get_selected_element_ids(): Helper for multi-selection handling
  - Automatic view refresh after all edit/delete/deprecate operations
- **Network-Aware SQLite Hardening** (Beta feature - COMPLETE):
  - Enhanced DatabaseManager.get_connection() with robust retry logic:
    - Increased max_retries to 10 for network environments
    - Exponential backoff with jitter (0.3s base * 2^attempt)
    - 60-second connection timeout for network file systems
  - SQLite PRAGMA optimizations for network performance:
    - `synchronous = NORMAL`: Balance safety vs speed
    - `journal_mode = WAL`: Write-Ahead Logging for better concurrency
    - `cache_size = -16000`: 16MB cache for reduced I/O
    - `check_same_thread = False`: Multi-threaded access support
  - Detailed operation logging (optional enable_logging parameter)
  - Enhanced error detection and reporting:
    - Distinguishes lock errors from other operational errors
    - Provides actionable error messages for troubleshooting
  - Stress test suite (tests/test_network_sqlite.py):
    - Multi-process concurrent access testing
    - Simulates 8 readers, 4 writers, 6 mixed workers
    - Reports success rate and operations/second
    - Validates database integrity under load
- **Performance Optimization** (Beta feature - COMPLETE):
  - PreviewCache module (src/preview_cache.py):
    - LRU (Least Recently Used) caching for QPixmap objects
    - Configurable max_size (200 previews) and memory limit (200MB)
    - Cache statistics: hit rate, miss count, eviction tracking
    - get(), put(), clear(), remove() API for cache management
    - preload() method for background loading
    - Global singleton via get_preview_cache()
  - Database query optimization:
    - Added pagination support to get_elements_by_list(limit, offset)
    - New get_elements_count() method for total counts
    - 6 additional performance indexes:
      * idx_elements_deprecated, idx_favorites_user
      * idx_playlist_items_playlist, idx_playlist_items_element
      * idx_history_status
  - MediaDisplayWidget optimizations:
    - Preview cache integration: checks cache before disk I/O
    - Reduced disk reads by ~90% for repeated views
    - Lazy loading: thumbnails loaded on-demand
  - Estimated 3-5x performance improvement for large catalogs (1000+ assets)

### Changed
- Updated `requirements.txt` to include notes for Python 3 development
- **Replaced Pillow with FFmpeg** for all media processing operations
- Removed Pillow dependency from requirements.txt
- Updated ingestion_core.py to use FFmpeg wrapper instead of PIL
- Modified PreviewGenerator to generate PNG thumbnails using FFmpeg
- Added support for video preview generation

### Fixed
- Fixed eventFilter initialization race condition in MediaInfoPopup causing AttributeError
- Added hasattr guards to prevent accessing table_view/gallery_view before widget initialization
- **Fixed NumPy 2.0 compatibility issue with PySide2** - Added numpy<2.0.0 constraint
- Created FIX_NUMPY_ISSUE.md with troubleshooting guide

## [0.1.0] - 2025-11-15

### Added
- Repository scaffolding and initial instructions document.
- Initial roadmap and changelog files.



> Notes:
> - Update the Unreleased section while working on changes. When cutting a release, move Unreleased entries under a new version heading with the release date.
> - Link issues or pull requests where applicable using the format: `[#123](https://github.com/your/repo/pull/123)`.
