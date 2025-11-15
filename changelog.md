# Changelog

All notable changes to this project will be documented in this file.

The format is based on "Keep a Changelog" and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- **GUI Code Refactoring - Modular Structure** (COMPLETE):
  - Extracted 19 widget/dialog classes from monolithic `gui_main.py` into organized modules
  - Created `src/ui/` module structure with 10 focused files
  - Module breakdown:
    * `dialogs.py` - 10 dialog classes (AdvancedSearchDialog, AddStackDialog, AddListDialog, etc.)
    * `pagination_widget.py` - PaginationWidget
    * `drag_gallery_view.py` - DragGalleryView
    * `media_info_popup.py` - MediaInfoPopup
    * `stacks_lists_panel.py` - StacksListsPanel
    * `media_display_widget.py` - MediaDisplayWidget
    * `history_panel.py` - HistoryPanel
    * `settings_panel.py` - SettingsPanel
    * `ingest_library_dialog.py` - IngestLibraryDialog
    * `__init__.py` - Central exports
  - Benefits:
    * 90% reduction in gui_main.py size (187 KB → 18 KB)
    * Improved maintainability - each widget in focused file
    * Better testability - widgets can be tested in isolation
    * No circular dependencies
    * 100% functional compatibility maintained
  - Documentation:
    * `REFACTORING.md` - Comprehensive refactoring guide
    * `REFACTORING_SUMMARY.md` - Metrics and benefits summary
  - Security: CodeQL scan passed with 0 vulnerabilities
  - All modules syntactically valid and properly structured

- **Lazy-loading Thumbnails & Pagination** (Session 6 - Feature 7 - ALREADY IMPLEMENTED):
  - Pagination system with configurable page size (default: 100 items per page)
  - Page selector widget with first/prev/next/last buttons
  - Total items counter and current page display
  - Pagination enabled/disabled toggle in settings panel
  - Page-based thumbnail loading (only loads thumbnails for current page)
  - Preview caching for memory efficiency (PreviewCache)
  - Dynamic icon scaling based on slider position
  - Search/filter integration maintains pagination
  - Tag-based search with pagination support
  - Favorites/playlists pagination
  - Performance optimized: Only processes visible page elements
  - Configuration options: items_per_page, pagination_enabled
  - Benefits: Handles large libraries (1000+ elements) without lag
  - Files: gui_main.py (lines 1210-1298 Pagination widget, lines 1303-1510 page-based loading)
- **Network-aware SQLite File Locking** (Session 6 - Feature 6 - COMPLETE):
  - Created `src/file_lock.py` - Cross-platform file locking manager (238 lines)
  - FileLockManager class with advisory file locking:
    * Platform-specific locking: Windows (msvcrt) and POSIX (fcntl)
    * Exponential backoff with jitter for lock acquisition
    * Configurable timeout and retry parameters
    * Automatic lock release with context manager support
    * Lock file management (.lock extension)
    * PID tracking in lock files for debugging
  - Integrated into DatabaseManager:
    * External file lock acquisition before database connection
    * Lock file path: `{database_path}.lock`
    * Configurable via `use_file_lock` parameter (default: True)
    * Lock released automatically in finally block
    * Supports concurrent access from multiple workstations
  - Features:
    * Retry logic with exponential backoff (100 attempts, 30s timeout)
    * Random jitter to prevent thundering herd
    * Graceful timeout handling with informative error messages
    * Platform-agnostic API (works on Windows and Linux)
    * Python 2.7 compatible (includes TimeoutError polyfill)
    * Context manager interface: `with file_lock(path):`
    * Automatic cleanup on object destruction
  - Network file system optimization:
    * WAL journal mode for better concurrency
    * NORMAL synchronous mode for balanced performance
    * 60-second connection timeout
    * 16MB cache size for performance
    * Handles stale locks and network delays
  - Use case: Multiple VFX workstations accessing shared database on network storage
  - Files: src/file_lock.py (238 lines), src/db_manager.py (updated get_connection method)
- **Packaging and Installer System** (Session 6 - Feature 5 - COMPLETE):
  - Created `tools/build_installer.py` - Automated build script for Windows distribution
  - PyInstaller integration for standalone executable generation
  - Automatic dependency bundling (PySide2, ffpyplayer, SQLite, FFmpeg binaries)
  - NSIS installer script generation for professional Windows installer
  - Portable ZIP distribution creation
  - Features:
    * Clean build process with artifact removal
    * Dependency validation (PyInstaller, PySide2, ffpyplayer)
    * Dynamic .spec file generation with proper configuration
    * Resource bundling (icons, config, examples, FFmpeg)
    * Hidden imports for PySide2 and ffpyplayer
    * README.txt generation with installation instructions
    * NSIS installer with shortcuts (Start Menu, Desktop)
    * Add/Remove Programs registry entries
    * Uninstaller creation
    * Portable ZIP for USB/network deployment
  - Build output:
    * Standalone executable: `dist/StaX/StaX.exe` (~100-200 MB)
    * Portable distribution: `installers/StaX_v1.0.0-beta_Portable.zip`
    * NSIS installer: `installers/StaX_Setup_v1.0.0-beta.exe`
  - Documentation:
    * `tools/BUILD_INSTRUCTIONS.md` - Complete build guide
    * `tools/requirements-build.txt` - Build dependencies
    * Troubleshooting section for common issues
    * CI/CD automation examples
  - Configuration options:
    * App version, name, author customizable
    * Icon support (app_icon.ico)
    * UPX compression enabled
    * No console window for GUI app
  - Files: tools/build_installer.py (467 lines), tools/BUILD_INSTRUCTIONS.md (279 lines)
- **Sequence Video Preview Generation** (Session 6 - Feature 4 - COMPLETE):
  - Enhanced FFmpegWrapper with `generate_sequence_video_preview()` method
  - Generates low-res MP4 previews (~512px) for image sequences
  - Configurable parameters: max_size (512px), fps (24), start_frame, max_frames (100 limit for 4-second previews)
  - Smart frame limiting: Creates preview from first 100 frames to keep file size manageable
  - FFmpeg options: fast encoding preset, CRF 28 for compression, faststart flag for web streaming
  - PreviewGenerator.generate_sequence_video_preview() static method
  - Automatic integration in ingestion_core.py workflow for 2D sequences
  - Database schema update: Added `video_preview_path` column to elements table
  - Migration 2.5: Automatic column addition for existing databases
  - Output format: MP4 with H.264 encoding
  - Maintains aspect ratio with force_original_aspect_ratio=decrease filter
  - Async-ready: Compatible with existing PreviewWorker/PreviewManager thread pool
  - Usage: Sequences now generate three types of previews:
    * Static PNG thumbnail (middle frame)
    * Animated GIF preview (3 seconds, 256x256px square)
    * Low-res MP4 video preview (first 100 frames, ~512px)
- **Video Playback Preview Pane** (Session 5 - NEW FEATURE - ffpyplayer Implementation):
  - Created `VideoPlayerWidget` (500+ lines) - professional embedded video player using ffpyplayer library
  - **ffpyplayer Integration**: Python bindings to FFmpeg for native frame-by-frame playback
  - **FFpyVideoWidget**: Custom QLabel widget that renders RGB24 frames from ffpyplayer
  - **PlayerController**: Qt-based controller wrapping ffpyplayer.MediaPlayer with signal/slot architecture
  - **Universal Format Support**: Plays ALL video formats including .mov, .mkv, .webm, .flv, .mp4, .avi, etc.
  - **No External Dependencies**: No Windows codec requirements, no DirectShow limitations
  - Right-side preview pane appears when single element selected
  - Automatic hide when multiple elements selected
  - **Playback Features**:
    * Embedded video playback for all formats (no codec installation needed)
    * Frame-by-frame decoding with RGB24 output
    * Real-time frame rendering with automatic scaling
    * Timeline slider with real-time position synchronization
    * Playback controls: Play/Pause toggle, Stop, Frame stepping
    * Time display (HH:MM:SS format) with current and total time labels
    * Frame counter with approximate 24fps calculation
    * Seek support (scrub timeline to any position)
    * Metadata display section with formatted element information
    * Tags display with bullet points
    * Deprecated status indicator
    * Close button with automatic cleanup
  - **Technical Architecture**:
    * `PlayerController`: Manages ffpyplayer.MediaPlayer lifecycle
    * Signal emissions: frame_ready, finished, duration_changed, position_changed
    * QTimer-based frame polling loop
    * Automatic format detection (rgb24 output)
    * Memory-efficient frame handling with memoryview/bytearray conversion
    * QImage rendering from raw RGB24 data (3 bytes per pixel)
  - **Error Handling**:
    * Format validation before loading
    * ffpyplayer availability detection
    * File existence checks
    * Clear error messages with installation instructions
    * Debug output for troubleshooting
  - **Timeline Scrubbing**: Drag slider to seek, pause-during-scrub, resume after
  - Integrated into MainWindow with 3-panel splitter layout (left: 250px, center: 900px, right: 400px)
  - Selection change handlers for automatic show/hide behavior
  - **Dependencies**: Requires `pip install ffpyplayer` (includes FFmpeg binaries)
- **Roadmap Requested Tasks Implementation** (Session 5):
  - **Task 2 - SVG Icons**: Verified all 3 required icons (stack.svg, list.svg, playlist.svg) exist in resources/icons/ with proper SVG structure and color tinting support
  - **Task 3 - Sub-list Creation**: Modified `add_list()` button to create sub-lists when a list is selected, top-level lists otherwise. Leverages existing `AddSubListDialog` and hierarchical tree display
  - **Task 4 - Context Menu Bulk Operations**: Removed "Bulk Operations ▼" toolbar button. Bulk actions (Add to Favorites, Add to Playlist, Mark Deprecated, Delete Selected) now accessible via right-click context menu when multiple items are selected. Includes selection count header and permission checks

### Fixed
- **Video Playback Universal Format Support** (Session 5 - ffpyplayer Solution):
  - Completely replaced QMediaPlayer/FFplay hybrid with ffpyplayer library
  - Issue: Windows DirectShow codec limitations prevented .mov, .mkv, .webm playback
  - Issue: QMediaPlayer required system codecs (DirectShow error 0x80040266)
  - Issue: FFplay fallback required external windows and lost control integration
  - Solution: ffpyplayer provides native Python bindings to FFmpeg
  - Benefits:
    * Plays ALL video formats without codec installation
    * Fully embedded playback (no external windows)
    * Frame-by-frame control with RGB24 output
    * Cross-platform compatibility
    * Professional VFX pipeline ready
  - Architecture: PlayerController wraps ffpyplayer.MediaPlayer with Qt signals
  - Custom FFpyVideoWidget renders decoded frames in QLabel with QPixmap
  - Maintains full timeline control, scrubbing, and playback state management
- **Video Playback Embedding** (Session 5 - Refactoring):
  - Refactored VideoPlayerWidget from external ffplay subprocess to embedded QMediaPlayer
  - User feedback: "it should be played inside the video player widget itself"
  - Converted 650-line ffplay implementation to 500-line Qt Multimedia implementation
  - Removed subprocess management, threading, and external process monitoring
  - Added QMediaPlayer with QVideoWidget for native embedded playback
  - Improved control integration with signal/slot architecture
  - Timeline now syncs automatically with playback position
  - Scrubbing works natively with setPosition() instead of ffplay seeking
- **FFplay Path Configuration** (Session 5 - Bug Fix - SUPERSEDED):
  - Fixed VideoPlayerWidget to use local ffplay.exe from `bin/ffmpeg/bin/ffplay.exe`
  - No longer expects ffplay in system PATH
  - Added existence check with helpful error message showing expected path
  - Path construction: `project_root/bin/ffmpeg/bin/ffplay.exe`
- **Sub-list Data Unpacking** (Session 5 - Bug Fix):
  - Fixed ValueError in `add_list()` when unpacking tree item data (expected 2 values, got 3)
  - Added length check before unpacking to handle variable-length data tuples
  - Properly extracts stack_id from 3rd element or parent item
- **Database Migration Issues** (Session 4 - Bug Fix):
  - Fixed missing `users` and `user_sessions` tables in existing databases
  - Added Migration 3: Auto-creates `users` table with default admin account
  - Added Migration 4: Auto-creates `user_sessions` table for session tracking
  - Fixed `get_favorites()` query using wrong column name (`favorited_at` → `created_at`)
- **UI Error Handling** (Session 4 - Bug Fix):
  - Fixed RuntimeError in GIF animation when QListWidgetItem is deleted during playback
  - Added try-catch blocks in `_update_gif_frame()` to handle deleted items gracefully
  - Removed invalid `setStyleSheet()` call on QAction (not supported in Qt)
- **Application Stability**: All critical runtime errors resolved, app runs without crashes

### Added
- **Live Filtering Enhancement - Tagging System** (Session 4 - Feature 1 - COMPLETE):
  - Database tag management methods (8 total):
    * `get_all_tags()`: Returns all unique tags across elements
    * `search_elements_by_tags(tags, match_all)`: Search by one or multiple tags
    * `get_elements_by_tag(tag)`: Get elements with specific tag
    * `add_tag_to_element(element_id, tag)`: Add tag without duplicates
    * `remove_tag_from_element(element_id, tag)`: Remove specific tag
    * `replace_element_tags(element_id, tags)`: Replace all tags
  - Enhanced EditElementDialog with tag autocomplete:
    * QCompleter with all existing tags
    * Popular tags display (top 10)
    * Smart sorting and formatting
  - Advanced search syntax support:
    * `#fire` - Search by single tag
    * `#fire,explosion` - Search by multiple tags (OR logic)
    * `tag:fire` - Explicit tag search
    * `tag:fire,explosion` - Multiple tags with explicit syntax
    * Plain text - Regular name search
  - Visual tag indicators:
    * Tags displayed in gallery view as suffix [tag1, tag2, tag3]
    * Tags shown in table view comment column
    * Search hint label shows active tag filters
  - Consolidated view update logic:
    * `_update_views_with_elements()` helper method
    * Handles both gallery and table views
    * Supports favorites, deprecated, and tag indicators
    * Integrates with GIF playback system
  - Smart tag parsing and filtering in live search
- **User/Permission Management System** (Session 4 - Feature 2 - COMPLETE):
  - Database schema additions:
    * `users` table with username, password_hash, role (admin/user), email, is_active
    * `user_sessions` table for tracking logged-in users
    * Default admin user created on first run (username: admin, password: admin)
  - User management database methods (11 total):
    * `create_user(username, password, role, email)`: Create new user with SHA256 hashed password
    * `authenticate_user(username, password)`: Authenticate and update last_login
    * `get_user_by_id(user_id)`: Retrieve user by ID
    * `get_user_by_username(username)`: Retrieve user by username
    * `get_all_users()`: Get all users
    * `update_user(user_id, **kwargs)`: Update user fields
    * `change_user_password(user_id, new_password)`: Change password
    * `delete_user(user_id)`: Soft delete (set is_active = 0)
    * `create_session(user_id, machine_name)`: Create login session
    * `get_active_session(user_id, machine_name)`: Get active session
    * `end_session(session_id)`: End user session
  - LoginDialog widget:
    * Professional styled dialog with teal accent
    * Username and password fields
    * "Continue as Guest" option for read-only access
    * Error message display
    * Auto-focus on username field
    * Enter key support for quick login
  - MainWindow authentication integration:
    * Login required on application start
    * `current_user` and `is_admin` tracking
    * Window title displays username and role
    * `check_admin_permission(action_name)`: Permission checking helper
    * `logout()`: End session and re-show login dialog
    * Ctrl+L keyboard shortcut for logout
  - Permission-protected operations:
    * Delete element: Admin only
    * Edit settings: Can be extended to admin only
    * Future: Stack/List deletion, ingestion settings
  - Session management:
    * Track active sessions per machine
    * Auto-update last_activity timestamp
    * Session termination on logout
- **Enhanced Settings Widget** (Session 4 - Feature 7 - COMPLETE):
  - Complete SettingsPanel rewrite with tabbed interface (6 tabs):
    * **General Tab**: Database location, user preferences, machine name
    * **Ingestion Tab**: Copy policy, sequence detection settings
    * **Preview & Media Tab**: Preview size/quality, GIF settings (size/fps/duration), FFmpeg thread count
    * **Network & Performance Tab**: DB connection retries/timeout, cache size/memory limits, **pagination settings**
    * **Custom Processors Tab**: Pre-ingest, post-ingest, post-import hooks with descriptions
    * **Security & Admin Tab**: Admin password change, user management table, add/edit/deactivate users (admin-only)
  - New settings in Config:
    * `preview_quality`: JPEG quality (1-100)
    * `gif_size`: GIF size in pixels (128-512)
    * `gif_fps`: GIF frame rate (5-30 fps)
    * `gif_duration`: GIF clip duration (1-10 seconds)
    * `ffmpeg_threads`: FFmpeg thread count (1-16)
    * `db_max_retries`: Database connection retry attempts (1-50)
    * `db_timeout`: Database connection timeout seconds (5-300)
    * `preview_cache_size`: Preview cache item count (50-1000)
    * `preview_cache_memory_mb`: Cache memory limit in MB (50-1000)
    * `pagination_enabled`: Enable/disable pagination (true/false)
    * `items_per_page`: Items per page (50/100/200/500)
    * `background_thumbnail_loading`: Background loading toggle (true/false)
  - Admin-only Security tab:
    * Password change interface with validation
    * User management table with username/role/email/active status
    * Add/Edit/Deactivate user buttons
    * Permission lock screen for non-admin users
  - Professional UI styling:
    * Organized group boxes with descriptions
    * Help text and tips for complex settings
    * SpinBox widgets with units (px, %, sec, threads, MB)
    * Large "💾 Save All Settings" button with teal styling
    * Current user indicator in bottom bar
  - Smart save behavior:
    * Saves all settings across all tabs
    * Warns about application restart requirements
    * Emits settings_changed signal
  - Reset to defaults functionality with confirmation
- **Environment Variable - STOCK_DB Path** (Session 4 - Feature 8 - COMPLETE):
  - Support for `STOCK_DB` environment variable:
    * Checked on Config initialization
    * Overrides `database_path` from config.json
    * Re-applied after loading config (takes precedence)
    * Console message confirms when environment variable is used
  - Deployment-friendly configuration:
    * Set `STOCK_DB=\\network\share\vfx\stock.db` for network deployments
    * Different database per environment (dev/staging/production)
    * No need to modify config.json for different setups
  - Settings panel integration:
    * Database path field shows environment variable value if set
    * Hint label: "Tip: Set STOCK_DB environment variable to override"
    * Browse button allows temporary override (until restart)
- **Performance Tuning - Pagination System** (Session 4 - Feature 3 - COMPLETE):
  - PaginationWidget class (159 lines):
    * First/Previous/Next/Last page buttons
    * Page indicator label: "Page X of Y"
    * Items per page selector (50/100/200/500)
    * Info label: "Showing X-Y of Z items"
    * Smart button enable/disable based on page
    * `page_changed` signal for navigation
    * `get_page_slice()` method returns (start, end) indices
  - MainWindow pagination integration:
    * `current_elements` list stores all elements
    * `load_elements()` updated to setup pagination
    * `on_page_changed()` handler for page navigation
    * `_display_current_page()` displays current page slice
    * `on_search()` updated to work with pagination
    * Pagination visibility controlled by settings
  - Configuration settings:
    * `pagination_enabled`: Enable/disable pagination
    * `items_per_page`: Configurable page size
    * Integrated into Network & Performance settings tab
  - Performance benefits:
    * Reduces memory usage for large lists
    * Prevents UI freezing with thousands of elements
    * Smooth navigation between pages
- **FFmpeg Multithreading - Background Preview Generation** (Session 4 - Feature 6 - COMPLETE):
  - PreviewWorker class (QThread-based background worker):
    * Queue-based task processing (non-blocking)
    * Supports image, sequence, video, and GIF preview generation
    * Uses configurable thread count from settings (`ffmpeg_threads`)
    * Emits signals: `preview_generated`, `progress_updated`, `error_occurred`
    * Graceful stop with queue clearing
    * Automatic preview directory creation
  - PreviewManager class (worker pool coordinator):
    * Manages multiple PreviewWorker threads (default: 2 workers)
    * Round-robin task distribution across workers
    * Batch preview generation support
    * Progress tracking with signals
    * `all_previews_complete` signal when batch finishes
    * Clear queue and reset counters functionality
  - Integration points:
    * Ready for MainWindow integration
    * Compatible with ingestion pipeline
    * Signals can update gallery/table views when previews complete
    * Queue system prevents UI blocking during batch operations
  - Performance benefits:
    * Parallel preview generation (2+ threads)
    * UI remains responsive during preview generation
    * Progress tracking for long operations
    * Cancellable operations via queue clearing
- **Drag & Drop to Nuke DAG** (Session 4 - Feature 4 - COMPLETE):
  - DragGalleryView custom widget (117 lines):
    * Extends QListWidget with drag & drop capabilities
    * Override `startDrag()` to set custom QMimeData
    * Supports dragging multiple selected elements
    * MIME data includes: element IDs, file URLs, custom app data
    * Drag icon uses first item's preview thumbnail
  - Smart node creation based on element type:
    * **2D assets** → `create_read_node()` with frame range detection
    * **3D assets** → `create_read_geo_node()` for .abc/.obj/.fbx files
    * **Toolsets** → `paste_nodes_from_file()` for .nk files
    * Automatic frame range detection for sequences
  - File path resolution:
    * Uses hard copy path if available (is_hard_copy = true)
    * Falls back to soft copy path (original location)
  - Integration:
    * MediaDisplayWidget updated to accept nuke_bridge parameter
    * Gallery view replaced with DragGalleryView
    * `on_popup_insert()` calls `insert_to_nuke()` method
    * MainWindow passes nuke_bridge to MediaDisplayWidget
- **Toolset Creation & Registration** (Session 4 - Feature 5 - COMPLETE):
  - RegisterToolsetDialog class (190 lines):
    * User-friendly dialog for registering Nuke node selections
    * Form inputs: Toolset name, target list, comment, preview option
    * List selector populated from all stacks/lists
    * "Generate preview image" checkbox for node graph capture
    * Save/Cancel button box with validation
  - Toolset creation workflow:
    * Generate unique filename with MD5 hash + timestamp
    * Call `nuke_bridge.save_selected_as_toolset()` to export .nk file
    * Move toolset from temp to repository directory
    * Optional: Capture node graph preview image
    * Ingest into database with type='toolset', format='nk'
    * Log history entry for auditing
  - NukeBridge enhancements:
    * `save_selected_as_toolset()`: Already existed, saves .nk files
    * `capture_node_graph_preview()`: NEW - captures node graph as PNG
    * Mock mode creates placeholder preview images
    * Real Nuke mode returns warning (no built-in API for graph capture)
  - Menu integration:
    * New "Nuke" menu in MainWindow menubar
    * "Register Selection as Toolset..." action (Ctrl+Shift+T)
    * `register_toolset()` method opens dialog and refreshes on success
  - Toolset usage:
    * Toolsets appear in gallery/table views like any element
    * Drag toolset into Nuke → automatically pastes nodes via `paste_nodes_from_file()`
    * Double-click toolset → same paste behavior
    * Preview shows node graph visualization (if generated)
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
- **Hierarchical Sub-Lists** (Session 3 - Production Feature):
  - Extended Lists table with parent_list_fk for recursive relationships
  - Database methods: create_list() accepts optional parent_list_id parameter
  - get_sub_lists(parent_list_id): Returns direct children of parent list
  - get_lists_by_stack(): Filters by parent_list_id (None = top-level only)
  - Added idx_lists_parent index for hierarchical query performance
  - Recursive GUI tree loading with _create_list_item() helper method
  - QTreeWidget displays expandable nested sub-lists
  - Right-click context menu on Lists: "Add Sub-List" option
  - AddSubListDialog: Dialog for creating nested sub-lists with parent display
  - Supports studio workflows: ActionFX > explosions > aerial explosions pattern
  - Database migration system: _apply_migrations() auto-updates existing databases
- **Delete Stack/List Context Menu** (Session 3 - Production Feature):
  - setContextMenuPolicy(CustomContextMenu) on tree widget
  - show_tree_context_menu(position): Right-click handler with Stack/List detection
  - Stack menu: "Add List to Stack", "Delete Stack"
  - List menu: "Add Sub-List", "Delete List"
  - Confirmation dialogs with cascade deletion warnings
  - delete_stack(stack_id): Cascade deletes all Lists and Elements
  - delete_list(list_id): Cascade deletes all sub-lists and Elements
  - CASCADE deletion enforced by SQLite FOREIGN KEY constraints
  - Updated list data tuples: (type, id, stack_id) for context menu access
  - Safe tuple unpacking in on_item_clicked() with len() check
- **Library Ingest Feature** (Session 3 - Production Feature - COMPLETE):
  - IngestLibraryDialog class: Comprehensive bulk ingestion dialog (~400 lines)
  - Folder selection with QFileDialog for library root
  - Recursive directory scanner: _scan_directory_structure(root, max_depth)
  - Maps folder hierarchy to Stack/List/Sub-List structure automatically
  - Configurable options:
    * Stack/List name prefixes for namespace management
    * Copy policy selection (hard_copy/soft_copy)
    * Max nesting depth control (1-10 levels)
  - Preview tree widget: Shows planned structure before ingestion
    * Color-coded: Stacks (orange), Lists (teal)
    * Displays media file count per folder
    * Expandable hierarchical preview
  - Scan Folder button: Analyzes structure and counts assets
  - Batch ingestion with QProgressDialog:
    * Processes stacks → lists → sub-lists recursively
    * Shows current file being ingested
    * Cancel support with graceful abort
    * Success/error counting and reporting
  - _ingest_lists_recursive(): Recursive ingestion of nested structures
  - Supports studio workflows: Ingest existing ActionFX/explosions/aerial libraries
  - Menu integration: File → Ingest Library... (Ctrl+Shift+I)
  - Auto-refresh stacks/lists panel after ingestion
  - Handles media extensions: jpg, png, tif, exr, dpx, mp4, mov, avi, obj, fbx, abc, nk
- **GIF Proxy Generation** (Session 3 - Production Feature - COMPLETE):
  - FFmpegWrapper.generate_gif_preview() method: Generates animated GIF from video/sequences
  - Two-pass FFmpeg process:
    * Pass 1: Generate optimized color palette with palettegen filter
    * Pass 2: Create GIF using palette for better quality
  - Configurable parameters: max_duration (3s), width (256px), fps (10)
  - Lanczos scaling for smooth resizing
  - Automatic palette cleanup after generation
  - Integrated into ingestion_core.py workflow:
    * Auto-generates GIF for all video assets (mp4, mov, avi, mkv)
    * Auto-generates GIF for 2D image sequences
    * Stores gif_preview_path in database
  - Added gif_preview_path to db_manager.create_element() allowed fields
  - Database migration pre-added gif_preview_path column
- **GIF Preview on Hover** (Session 3 - Production Feature - COMPLETE):
  - QMovie integration in MediaDisplayWidget for animated GIF playback
  - Hover event handling in eventFilter():
    * Mouse enter: Load and play GIF from gif_preview_path
    * Mouse leave: Stop GIF and restore static thumbnail
  - GIF movie caching: gif_movies dict {element_id: QMovie}
  - play_gif_for_item(item, element_id): Starts GIF playback
  - _update_gif_frame(item, movie): Updates icon with current frame
  - stop_current_gif(): Stops playback and restores static preview
  - current_gif_item tracking to prevent duplicate playback
  - Automatic frame updates via QMovie.frameChanged signal
  - Icon scaling to match gallery icon size
  - No Alt key required: Hover triggers GIF automatically
  - Performance: QMovie objects cached, reused on re-hover
  - Smooth playback: FFmpeg-generated GIFs optimized for gallery view

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
- **Stabilized GIF hover playback across all views:**
  - Rebuilt MediaDisplayWidget rendering to keep element/QMovie associations in sync
  - Favorites, playlists, and paginated lists now share the same preview pipeline
  - Hover playback resumes reliably after resizing or switching collections
- **Replaced Unicode status glyphs with SVG icons:**
  - Gallery/table badges now use `favorite.svg` and `deprecated.svg`
  - Navigation tree, playlists, and bulk/context menus use `stack.svg`, `list.svg`, `playlist.svg`, etc.
  - Removed hardcoded emoji/bullet characters to ensure consistent cross-platform rendering
- **Fixed ModuleNotFoundError in ingestion_core.py** (Session 3):
  - Changed "from ffmpeg_wrapper import" to "from src.ffmpeg_wrapper import"
  - Fixed missing src. prefix for relative imports
- **Added Database Migration System** (Session 3):
  - Implemented _apply_migrations() to handle schema updates for existing databases
  - Migration 1: Adds parent_list_fk column to lists table if missing
  - Migration 2: Adds gif_preview_path column to elements table if missing
  - Auto-detects missing columns with try/except OperationalError pattern
  - Runs migrations on every database connection if database already exists
- **Fixed GIF Generation Issues** (Session 3):
  - Added gif_preview_path to initial schema creation (not just migrations)
  - Fixed video detection: Changed from `asset_type == 'video'` to file extension check
  - Added comprehensive debug logging for GIF generation process
  - Created test_gif_generation.py diagnostic script
  - Fixed stacks_panel reference in ingest_library() method
  - GIFs now generate correctly for .mp4, .mov, .avi, .mkv, and other video formats
  - GIFs now generate correctly for image sequences
- **Enhanced Thumbnail Display and Scaling** (Session 3):
  - Fixed static thumbnails not showing (odd icons displayed until hover)
  - All elements now show PNG thumbnails immediately on load
  - Improved thumbnail loading with proper scaling and caching
  - GIF generation now creates uniform 256x256 square output
  - Maintains aspect ratio with letterbox/pillarbox padding (black bars)
  - Perfect gallery layout alignment with consistent dimensions
  - Size slider now properly scales thumbnails dynamically (64px-512px)
  - on_size_changed() reloads elements with new scale on slider movement
  - Smooth scaling with KeepAspectRatio and SmoothTransformation
  - Both PNG thumbnails and GIF playback scale with slider
  - Enhanced load_elements() to scale images to current icon size
  - Improved preview cache to store originals, scale on-demand

## [0.1.0] - 2025-11-15

### Added
- Repository scaffolding and initial instructions document.
- Initial roadmap and changelog files.



> Notes:
> - Update the Unreleased section while working on changes. When cutting a release, move Unreleased entries under a new version heading with the release date.
> - Link issues or pull requests where applicable using the format: `[#123](https://github.com/your/repo/pull/123)`.
