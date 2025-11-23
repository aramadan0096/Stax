# -*- coding: utf-8 -*-
"""
StaX Nuke Panel
Nuke-specific panel launcher for StaX asset management system
Python 2.7 compatible
"""

import os
import sys

import dependency_bootstrap

dependency_bootstrap.bootstrap()

from src.debug_manager import DebugManager

DebugManager.bootstrap_from_config()

print("\n" + "="*80)
print("[nuke_launcher] Module loading started...")
print("="*80)

# Initialize logger first
logger = None
try:
    from stax_logger import get_logger
    logger = get_logger()
    logger.info("="*80)
    logger.info("nuke_launcher.py loading")
    logger.info("="*80)
    logger.info("Python version: {}".format(sys.version))
    logger.info("Python executable: {}".format(sys.executable))
    print("[nuke_launcher] [OK] Logger initialized")
except Exception as e:
    print("[nuke_launcher] [WARN] Logger initialization failed: {}".format(e))
    print("[nuke_launcher]   (Continuing without logger)")

# Import PySide2
try:
    print("[nuke_launcher] Importing PySide2...")
    from PySide2 import QtWidgets, QtCore, QtGui
    if logger:
        logger.info("PySide2 imported successfully")
    print("[nuke_launcher] [OK] PySide2 imported")
except ImportError as e:
    print("[nuke_launcher] [ERROR] CRITICAL: Failed to import PySide2: {}".format(e))
    if logger:
        logger.critical("Failed to import PySide2: {}".format(e))
    raise

# Ensure nuke module is available
NUKE_MODE = False
try:
    print("[nuke_launcher] Checking for Nuke environment...")
    import nuke
    import nukescripts
    NUKE_MODE = True
    if logger:
        logger.info("Running in Nuke environment")
        logger.info("Nuke version: {}".format(nuke.NUKE_VERSION_STRING if hasattr(nuke, 'NUKE_VERSION_STRING') else 'Unknown'))
    print("[nuke_launcher] [OK] Nuke environment detected")
except ImportError:
    NUKE_MODE = False
    if logger:
        logger.warning("Running outside Nuke environment (mock mode)")
    print("[nuke_launcher] [WARN] Warning: Running outside Nuke environment")

print("[nuke_launcher] Setting up module paths...")
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    if logger:
        logger.info("Added to sys.path: {}".format(current_dir))
    print("[nuke_launcher]   [OK] Added: {}".format(current_dir))

# Add root to sys.path
stax_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if stax_root not in sys.path:
    sys.path.insert(0, stax_root)
    if logger:
        logger.info("Added root to sys.path: {}".format(stax_root))
    print("[nuke_launcher]   [OK] Added root: {}".format(stax_root))

ffpyplayer_pkg = os.path.join(stax_root, 'dependencies', 'ffpyplayer')
if os.path.isdir(ffpyplayer_pkg):
    print("[nuke_launcher]   [OK] ffpyplayer directory detected: {}".format(ffpyplayer_pkg))
    if logger:
        logger.info("ffpyplayer directory detected: {}".format(ffpyplayer_pkg))
else:
    print("[nuke_launcher]   [WARN] ffpyplayer directory not found: {}".format(ffpyplayer_pkg))
    if logger:
        logger.warning("ffpyplayer directory not found: {}".format(ffpyplayer_pkg))

# Import core modules with error handling
print("[nuke_launcher] Importing core modules...")

try:
    from src.config import Config
    if logger:
        logger.info("Imported: src.config.Config")
    print("[nuke_launcher]   [OK] Config")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import Config: {}".format(e))
    if logger:
        logger.exception("Failed to import Config")
    raise

try:
    from src.db_manager import DatabaseManager
    if logger:
        logger.info("Imported: src.db_manager.DatabaseManager")
    print("[nuke_launcher]   [OK] DatabaseManager")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import DatabaseManager: {}".format(e))
    if logger:
        logger.exception("Failed to import DatabaseManager")
    raise

try:
    from src.ingestion_core import IngestionCore
    if logger:
        logger.info("Imported: src.ingestion_core.IngestionCore")
    print("[nuke_launcher]   [OK] IngestionCore")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import IngestionCore: {}".format(e))
    if logger:
        logger.exception("Failed to import IngestionCore")
    raise

try:
    from bridge import NukeBridge, NukeIntegration
    if logger:
        logger.info("Imported: plugins.dccs.nuke.bridge")
    print("[nuke_launcher]   [OK] NukeBridge, NukeIntegration")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import NukeBridge: {}".format(e))
    if logger:
        logger.exception("Failed to import NukeBridge")
    raise

try:
    from src.extensibility_hooks import ProcessorManager
    if logger:
        logger.info("Imported: src.extensibility_hooks.ProcessorManager")
    print("[nuke_launcher]   [OK] ProcessorManager")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import ProcessorManager: {}".format(e))
    if logger:
        logger.exception("Failed to import ProcessorManager")
    raise

try:
    from src.icon_loader import get_icon
    if logger:
        logger.info("Imported: src.icon_loader.get_icon")
    print("[nuke_launcher]   [OK] get_icon")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import get_icon: {}".format(e))
    if logger:
        logger.exception("Failed to import get_icon")
    raise

try:
    from src.video_player_widget import VideoPlayerWidget
    if logger:
        logger.info("Imported: src.video_player_widget.VideoPlayerWidget")
    print("[nuke_launcher]   [OK] VideoPlayerWidget")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import VideoPlayerWidget: {}".format(e))
    if logger:
        logger.exception("Failed to import VideoPlayerWidget")
    raise

# Import all UI widgets from ui module
print("[nuke_launcher] Importing UI modules...")
try:
    from src.ui import (
        AdvancedSearchDialog,
        AddStackDialog,
        AddListDialog,
        AddSubListDialog,
        CreatePlaylistDialog,
        AddToPlaylistDialog,
        LoginDialog,
        EditElementDialog,
        RegisterToolsetDialog,
        SelectListDialog,
        IngestLibraryDialog,
        MediaInfoPopup,
        StacksListsPanel,
        MediaDisplayWidget,
        HistoryPanel,
        SettingsPanel,
    )
    if logger:
        logger.info("Imported all UI modules from src.ui")
    print("[nuke_launcher]   [OK] All UI modules imported (16 widgets)")
except Exception as e:
    print("[nuke_launcher]   [ERROR] CRITICAL: Failed to import UI modules: {}".format(e))
    if logger:
        logger.exception("Failed to import UI modules")
    raise

print("[nuke_launcher] [OK] All imports successful")
print("="*80 + "\n")

if logger:
    logger.info("All imports completed successfully")
    logger.separator()


class StaXPanel(QtWidgets.QWidget):
    """
    StaX panel widget for embedding in Nuke.
    This is a QWidget-based version of MainWindow designed for Nuke integration.
    """
    
    def __init__(self, parent=None):
        print("\n[StaXPanel.__init__] Initialization started...")
        if logger:
            logger.info("="*80)
            logger.info("StaXPanel.__init__ starting")
            logger.info("="*80)
        
        try:
            super(StaXPanel, self).__init__(parent)
            print("[StaXPanel.__init__]   [OK] QWidget superclass initialized")
            if logger:
                logger.info("QWidget superclass initialized")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize QWidget: {}".format(e))
            if logger:
                logger.exception("Failed to initialize QWidget")
            raise
        
        # Initialize core components
        print("[StaXPanel.__init__] Initializing core components...")
        
        try:
            self.config = Config()
            print("[StaXPanel.__init__]   [OK] Config initialized")
            if logger:
                logger.info("Config initialized")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize Config: {}".format(e))
            if logger:
                logger.exception("Failed to initialize Config")
            raise
        
        try:
            self.config.ensure_directories()
            print("[StaXPanel.__init__]   [OK] Directories ensured")
            if logger:
                logger.info("Directories ensured")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to ensure directories: {}".format(e))
            if logger:
                logger.exception("Failed to ensure directories")
            raise
        
        # Set Nuke mock mode to False when running in Nuke
        if NUKE_MODE:
            print("[StaXPanel.__init__] Disabling mock mode (running in Nuke)")
            self.config.set('nuke_mock_mode', False)
            if logger:
                logger.info("Mock mode disabled (NUKE_MODE = True)")
        else:
            print("[StaXPanel.__init__] Mock mode remains enabled (not in Nuke)")
            if logger:
                logger.warning("Mock mode enabled (NUKE_MODE = False)")
        
        try:
            db_path = self.config.get('database_path')
            print("[StaXPanel.__init__] Database path: {}".format(db_path))
            self.db = DatabaseManager(db_path)
            print("[StaXPanel.__init__]   [OK] DatabaseManager initialized")
            if logger:
                logger.info("DatabaseManager initialized with path: {}".format(db_path))
            
            # Load database-stored settings (previews_path, etc.)
            print("[StaXPanel.__init__] Loading database-stored settings...")
            self.config.load_from_database(self.db)
            print("[StaXPanel.__init__]   [OK] Database settings loaded")
            DebugManager.sync_from_config(self.config)
            
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize DatabaseManager: {}".format(e))
            if logger:
                logger.exception("Failed to initialize DatabaseManager")
            raise
        
        try:
            mock_mode = self.config.get('nuke_mock_mode')
            print("[StaXPanel.__init__] Creating NukeBridge (mock_mode={})...".format(mock_mode))
            self.nuke_bridge = NukeBridge(mock_mode=mock_mode)
            print("[StaXPanel.__init__]   [OK] NukeBridge initialized")
            if logger:
                logger.info("NukeBridge initialized (mock_mode={})".format(mock_mode))
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize NukeBridge: {}".format(e))
            if logger:
                logger.exception("Failed to initialize NukeBridge")
            raise
        
        try:
            self.ingestion = IngestionCore(self.db, self.config.get_all())
            print("[StaXPanel.__init__]   [OK] IngestionCore initialized")
            if logger:
                logger.info("IngestionCore initialized")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize IngestionCore: {}".format(e))
            if logger:
                logger.exception("Failed to initialize IngestionCore")
            raise
        
        try:
            self.processor_manager = ProcessorManager(self.config.get_all())
            print("[StaXPanel.__init__]   [OK] ProcessorManager initialized")
            if logger:
                logger.info("ProcessorManager initialized")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize ProcessorManager: {}".format(e))
            if logger:
                logger.exception("Failed to initialize ProcessorManager")
            raise

        try:
            self.nuke_integration = NukeIntegration(
                self.nuke_bridge,
                self.db,
                config=self.config,
                ingestion_core=self.ingestion,
                processor_manager=self.processor_manager
            )
            print("[StaXPanel.__init__]   [OK] NukeIntegration initialized")
            if logger:
                logger.info("NukeIntegration initialized")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to initialize NukeIntegration: {}".format(e))
            if logger:
                logger.exception("Failed to initialize NukeIntegration")
            raise
        
        # User authentication
        self.current_user = None
        self.is_admin = False
        print("[StaXPanel.__init__]   [OK] User authentication variables set")
        
        # Set window properties
        try:
            self.setWindowTitle("StaX")
            self.resize(1200, 700)
            print("[StaXPanel.__init__]   [OK] Window properties set")
            if logger:
                logger.info("Window properties set (1200x700)")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] Failed to set window properties: {}".format(e))
            if logger:
                logger.exception("Failed to set window properties")
            raise
        
        # Set application icon
        try:
            icon_path = os.path.join(stax_root, 'resources', 'logo.png')
            if os.path.exists(icon_path):
                self.setWindowIcon(QtGui.QIcon(icon_path))
                print("[StaXPanel.__init__]   [OK] Window icon set")
                if logger:
                    logger.info("Window icon set: {}".format(icon_path))
            else:
                print("[StaXPanel.__init__]   [WARN] Window icon not found: {}".format(icon_path))
                if logger:
                    logger.warning("Window icon not found: {}".format(icon_path))
        except Exception as e:
            print("[StaXPanel.__init__]   [WARN] Failed to set window icon: {}".format(e))
            if logger:
                logger.warning("Failed to set window icon: {}".format(e))
        
        # Setup UI first
        print("[StaXPanel.__init__] Setting up UI...")
        try:
            self.setup_ui()
            print("[StaXPanel.__init__]   [OK] UI setup complete")
            if logger:
                logger.info("UI setup completed successfully")
        except Exception as e:
            print("[StaXPanel.__init__]   [ERROR] CRITICAL: Failed to setup UI: {}".format(e))
            if logger:
                logger.exception("Failed to setup UI")
            raise
        
        # Skip login dialog in Nuke mode - auto-login as admin
        if NUKE_MODE:
            print("[StaXPanel.__init__] NUKE_MODE: Skipping login dialog, running as guest until elevated")
            self.current_user = {
                'user_id': None,
                'username': 'guest',
                'role': 'guest'
            }
            self.is_admin = False
            if hasattr(self, 'user_label'):
                self.user_label.setText("User: Guest (Read-only)")
                self.user_label.setStyleSheet("padding: 5px; color: #ff9a3c; font-weight: bold;")
            self.show_status("Running in guest mode - login required for admin settings")
            if logger:
                logger.info("Guest session initialized (Nuke mode); admin login required for settings")
        else:
            # Show login dialog in standalone mode
            print("[StaXPanel.__init__] Scheduling login dialog...")
            try:
                QtCore.QTimer.singleShot(100, self.show_login)
                print("[StaXPanel.__init__]   [OK] Login dialog scheduled")
                if logger:
                    logger.info("Login dialog scheduled (100ms delay)")
            except Exception as e:
                print("[StaXPanel.__init__]   [ERROR] Failed to schedule login dialog: {}".format(e))
                if logger:
                    logger.exception("Failed to schedule login dialog")
                raise
        
        print("[StaXPanel.__init__] [OK] Initialization complete!\n")
        if logger:
            logger.info("StaXPanel initialization completed successfully")
            logger.separator()
    
    def setup_ui(self):
        """Setup the panel UI."""
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Toolbar
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)
        
        # Main content splitter
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self._stored_left_width = None
        
        # Left: Stacks/Lists panel
        self.stacks_panel = StacksListsPanel(self.db, self.config, main_window=self)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        self.stacks_panel.stack_selected.connect(self.on_stack_selected)
        self.stacks_panel.favorites_selected.connect(self.on_favorites_selected)
        self.stacks_panel.playlist_selected.connect(self.on_playlist_selected)
        self.stacks_panel.tags_filter_changed.connect(self.on_tags_filter_changed)
        self.main_splitter.addWidget(self.stacks_panel)
        
        # Center: Media display
        self.media_display = MediaDisplayWidget(self.db, self.config, self.nuke_bridge, main_window=self)
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        self.main_splitter.addWidget(self.media_display)
        
        # Video preview disabled in embedded Nuke mode
        self.video_player_pane = None
        
        # Set splitter sizes (left: 260, center: remainder)
        self.main_splitter.setSizes([260, 900])
        
        main_layout.addWidget(self.main_splitter)
        
        # Store toolbar reference for focus mode
        self.toolbar = toolbar
        
        # Connect selection changes to update preview pane
        self.media_display.gallery_view.itemSelectionChanged.connect(self.on_selection_changed)
        self.media_display.table_view.itemSelectionChanged.connect(self.on_selection_changed)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("padding: 5px; color: #16c6b0;")
        main_layout.addWidget(self.status_label)
    
    def create_toolbar(self):
        """Create toolbar with actions."""
        toolbar = QtWidgets.QToolBar("Main Toolbar")
        toolbar.setIconSize(QtCore.QSize(20, 20))
        toolbar.setStyleSheet("QToolBar { spacing: 5px; padding: 5px; }")
        
        # Ingest Files action
        ingest_action = QtWidgets.QAction(get_icon('import', size=20), "Ingest Files", self)
        ingest_action.setToolTip("Ingest files into StaX (Ctrl+I)")
        ingest_action.triggered.connect(self.ingest_files)
        toolbar.addAction(ingest_action)
        
        # Ingest Library action
        ingest_lib_action = QtWidgets.QAction(get_icon('folder', size=20), "Ingest Library", self)
        ingest_lib_action.setToolTip("Bulk ingest folder structures (Ctrl+Shift+I)")
        ingest_lib_action.triggered.connect(self.ingest_library)
        toolbar.addAction(ingest_lib_action)
        
        toolbar.addSeparator()
        
        # Advanced Search action
        search_action = QtWidgets.QAction(get_icon('search', size=20), "Search", self)
        search_action.setToolTip("Advanced search (Ctrl+F)")
        search_action.triggered.connect(self.show_advanced_search)
        toolbar.addAction(search_action)

        favorites_action = QtWidgets.QAction(get_icon('favorite', size=20), "Favorites", self)
        favorites_action.setToolTip("Show favorites across stacks")
        favorites_action.triggered.connect(self.on_favorites_selected)
        toolbar.addAction(favorites_action)
        
        toolbar.addSeparator()
        
        # Register Toolset action
        toolset_action = QtWidgets.QAction(get_icon('add', size=20), "Register Toolset", self)
        toolset_action.setToolTip("Save selected Nuke nodes as toolset (Ctrl+Shift+T)")
        toolset_action.triggered.connect(self.register_toolset)
        toolbar.addAction(toolset_action)
        
        toolbar.addSeparator()
        
        # History action
        history_action = QtWidgets.QAction(get_icon('history', size=20), "History", self)
        history_action.setToolTip("Show ingestion history (Ctrl+2)")
        history_action.triggered.connect(self.show_history)
        toolbar.addAction(history_action)
        
        # Settings action
        settings_action = QtWidgets.QAction(get_icon('settings', size=20), "Settings", self)
        settings_action.setToolTip("Show settings (Ctrl+3)")
        settings_action.triggered.connect(self.show_settings)
        toolbar.addAction(settings_action)
        
        toolbar.addSeparator()
        
        # User info label
        self.user_label = QtWidgets.QLabel("Not logged in")
        self.user_label.setStyleSheet("padding: 5px; color: #ff9a3c; font-weight: bold;")
        toolbar.addWidget(self.user_label)
        
        # Logout action
        logout_action = QtWidgets.QAction("Logout", self)
        logout_action.setToolTip("Logout and switch user (Ctrl+L)")
        logout_action.triggered.connect(self.logout)
        toolbar.addAction(logout_action)
        
        return toolbar
    
    def show_login(self):
        """Show login dialog."""
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = self.current_user and self.current_user.get('role') == 'admin'
            
            # Update user label
            username = self.current_user['username'] if self.current_user else 'Guest'
            role_text = ' (Admin)' if self.is_admin else ''
            self.user_label.setText("User: {}{}".format(username, role_text))
            
            self.show_status("Logged in as: {}".format(username))
        else:
            # User cancelled login - use guest mode
            self.current_user = {'username': 'guest', 'role': 'guest'}
            self.is_admin = False
            self.user_label.setText("User: Guest (Read-only)")
            self.show_status("Running in guest mode")
    
    def check_admin_permission(self, action_name="this action"):
        """
        Check if current user has admin permissions.
        Shows error dialog if not.
        
        Args:
            action_name (str): Name of the action being attempted
            
        Returns:
            bool: True if user is admin
        """
        if not self.is_admin:
            QtWidgets.QMessageBox.warning(
                self,
                "Permission Denied",
                "You need administrator privileges to perform {}.\n\n"
                "Current user: {} ({})\n\n"
                "Please login as an administrator.".format(
                    action_name,
                    self.current_user['username'] if self.current_user else 'guest',
                    self.current_user.get('role', 'guest') if self.current_user else 'guest'
                )
            )
            return False
        return True
    
    def logout(self):
        """Logout current user and show login dialog."""
        if self.current_user and self.current_user.get('user_id'):
            # End session
            import socket
            machine_name = socket.gethostname()
            session = self.db.get_active_session(self.current_user['user_id'], machine_name)
            if session:
                self.db.end_session(session['session_id'])
        
        # Show login again
        self.show_login()
    
    def show_status(self, message):
        """Update status label."""
        self.status_label.setText(message)
    
    def toggle_focus_mode(self, checked):
        """Hide or show navigation panel and toolbar for distraction-free browsing."""
        sizes = self.main_splitter.sizes()
        if len(sizes) < 2:
            return

        if checked:
            # Store the left width before hiding
            self._stored_left_width = sizes[0] if sizes[0] > 0 else self.stacks_panel.minimumWidth()
            # Give all space to center
            total_width = self.main_splitter.width()
            sizes = [0, total_width]
            self.stacks_panel.hide()
            self.toolbar.hide()  # Hide toolbar in focus mode
        else:
            # Restore the left panel
            restore_width = self._stored_left_width or self.stacks_panel.minimumWidth()
            total_width = self.main_splitter.width()
            center_width = max(400, total_width - restore_width)
            sizes = [restore_width, center_width]
            self.stacks_panel.show()
            self.toolbar.show()  # Show toolbar when exiting focus mode

        self.main_splitter.setSizes(sizes)
    
    def on_list_selected(self, list_id):
        """Handle list selection."""
        self.media_display.load_elements(list_id)
        
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst['stack_fk'])
            if stack:
                self.show_status("Viewing: {} > {}".format(stack['name'], lst['name']))
    
    def on_stack_selected(self, stack_id):
        """Handle stack selection - optionally show all elements from all lists in the stack."""
        if not self.config.get('show_entire_stack_elements', False):
            return  # Feature disabled
        
        lists = self.db.get_lists_by_stack(stack_id)
        all_elements = []
        for lst in lists:
            all_elements.extend(self.db.get_elements_by_list(lst['list_id']))
        
        self.media_display.current_list_id = None
        self.media_display.current_elements = all_elements
        self.media_display.current_tag_filter = []
        
        if self.config.get('pagination_enabled', True):
            self.media_display.pagination.set_total_items(len(all_elements))
            self.media_display.pagination.set_items_per_page(self.config.get('items_per_page', 100))
            self.media_display.pagination.setVisible(len(all_elements) > 0)
        else:
            self.media_display.pagination.setVisible(False)
        
        if all_elements:
            self.media_display.content_stack.setCurrentIndex(1)
        else:
            stack = self.db.get_stack_by_id(stack_id)
            if stack:
                self.media_display.info_label.setText("No elements in stack '{}'".format(stack['name']))
                self.media_display.hint_label.setText("Add lists and elements to this stack")
            self.media_display.content_stack.setCurrentIndex(0)
        
        self.media_display._display_current_page()
        
        stack = self.db.get_stack_by_id(stack_id)
        if stack:
            self.show_status("Viewing: {} (all lists)".format(stack['name']))
    
    def on_tags_filter_changed(self, tags):
        """Handle tags filter change."""
        if tags:
            self.media_display.load_elements_by_tags(tags)
            self.show_status("Filtering by tags: {}".format(", ".join(tags)))
        else:
            self.media_display.show_empty_state("Select tags to filter the library", "Choose tags from the Tags Filter panel")
    
    def on_favorites_selected(self):
        """Handle favorites button click."""
        self.media_display.load_favorites()
        self.show_status("Viewing: Favorites")
    
    def on_playlist_selected(self, playlist_id):
        """Handle playlist selection."""
        self.media_display.load_playlist(playlist_id)
        playlist = self.db.get_playlist_by_id(playlist_id)
        if playlist:
            self.show_status("Viewing Playlist: {}".format(playlist['name']))
    
    def on_element_double_clicked(self, element_id):
        """Handle element double-click (insert into Nuke)."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.show_status("Inserted: {}".format(element['name']))
                if NUKE_MODE:
                    nuke.message("Element '{}' inserted into node graph".format(element['name']))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def on_selection_changed(self):
        """Handle element selection change - update preview pane."""
        if not self.video_player_pane:
            return
        selected_ids = self.media_display.get_selected_element_ids()
        
        if len(selected_ids) == 1:
            # Single element selected - show preview pane
            element_id = selected_ids[0]
            self.video_player_pane.load_element(element_id)
            self.video_player_pane.show()
        elif len(selected_ids) > 1:
            # Multiple elements selected - hide preview pane
            self.video_player_pane.hide()
            self.video_player_pane.clear()
        else:
            # No selection - keep pane visible but cleared if it was already visible
            if self.video_player_pane.isVisible():
                self.video_player_pane.clear()
    
    def on_preview_pane_closed(self):
        """Handle preview pane close button."""
        if not self.video_player_pane:
            return
        self.video_player_pane.hide()
        self.video_player_pane.clear()
    
    def ingest_files(self):
        """Open file dialog to ingest files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Files to Ingest", "", "All Files (*.*)"
        )
        
        if not files:
            return
        
        # Ask for target list
        dialog = SelectListDialog(self.db, self)
        if dialog.exec_():
            target_list_id = dialog.get_selected_list()
            if target_list_id:
                self.perform_ingestion(files, target_list_id)
    
    def perform_ingestion(self, files, target_list_id):
        """Perform ingestion of files."""
        progress = QtWidgets.QProgressDialog("Ingesting files...", "Cancel", 0, len(files), self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        
        success_count = 0
        error_count = 0
        
        for i, filepath in enumerate(files):
            if progress.wasCanceled():
                break
            
            progress.setValue(i)
            progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
            
            result = self.ingestion.ingest_file(
                filepath,
                target_list_id,
                copy_policy=self.config.get('default_copy_policy')
            )
            
            if result['success']:
                success_count += 1
            else:
                error_count += 1
        
        progress.setValue(len(files))
        
        # Show result
        QtWidgets.QMessageBox.information(
            self,
            "Ingestion Complete",
            "Ingested {} files successfully.\n{} errors.".format(success_count, error_count)
        )
        
        # Refresh current view
        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)
    
    def ingest_library(self):
        """Open Library Ingest dialog to bulk-ingest folder structures."""
        dialog = IngestLibraryDialog(self.db, self.ingestion, self.config, self)
        if dialog.exec_():
            # Refresh stacks/lists after library ingestion
            self.stacks_panel.load_data()
    
    def register_toolset(self):
        """Open Register Toolset dialog to save selected Nuke nodes as a toolset."""
        if not NUKE_MODE:
            QtWidgets.QMessageBox.warning(self, "Nuke Required", "This feature requires Nuke to be running.")
            return
        
        dialog = RegisterToolsetDialog(self.db, self.nuke_integration, self.config, self)
        if dialog.exec_():
            # Refresh media display to show new toolset
            if hasattr(self.media_display, 'current_list_id') and self.media_display.current_list_id:
                self.media_display.load_elements(self.media_display.current_list_id)
            self.show_status("Toolset registered successfully")
    
    def show_history(self):
        """Show history dialog."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Ingestion History")
        dialog.resize(800, 500)
        
        dialog_layout = QtWidgets.QVBoxLayout(dialog)
        history_panel = HistoryPanel(self.db)
        dialog_layout.addWidget(history_panel)
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)
        
        history_panel.load_history()
        dialog.exec_()
    
    def show_settings(self):
        """Show settings dialog - requires admin access."""
        # Check if user is admin, if not show login dialog first
        if not self.is_admin:
            print("[show_settings] Non-admin user attempting to access settings, showing login...")
            self.show_login()
            
            # Check again after login attempt
            if not self.is_admin:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Access Denied",
                    "Settings panel requires administrator privileges.\n\n"
                    "Please login as an administrator to access settings."
                )
                return
        
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.resize(900, 600)
        
        dialog_layout = QtWidgets.QVBoxLayout(dialog)
        settings_panel = SettingsPanel(self.config, self.db, main_window=self)
        settings_panel.settings_changed.connect(self.on_settings_changed)
        dialog_layout.addWidget(settings_panel)
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def on_settings_changed(self):
        """Handle settings change."""
        # Reload processor manager
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.show_status("Settings updated")
    
    def show_advanced_search(self):
        """Show advanced search dialog."""
        if not hasattr(self, 'advanced_search_dialog') or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()


def show_stax_panel():
    """
    Show StaX panel in Nuke.
    This function is called from menu.py.
    """
    print("\n" + "="*80)
    print("[show_stax_panel] Function called")
    print("="*80)
    if logger:
        logger.info("="*80)
        logger.info("show_stax_panel() function called")
        logger.info("="*80)
    
    # Apply stylesheet
    print("[show_stax_panel] Getting QApplication instance...")
    try:
        app = QtWidgets.QApplication.instance()
        if app:
            print("[show_stax_panel]   [OK] QApplication instance found")
            if logger:
                logger.info("QApplication instance found")
        else:
            print("[show_stax_panel]   [WARN] No QApplication instance found")
            if logger:
                logger.warning("No QApplication instance found")
    except Exception as e:
        print("[show_stax_panel]   [ERROR] Failed to get QApplication instance: {}".format(e))
        if logger:
            logger.exception("Failed to get QApplication instance")
        raise
    
    if app and not NUKE_MODE:
        # Only apply stylesheet in standalone mode
        # Skip in Nuke to avoid Qt compatibility issues
        print("[show_stax_panel] Loading stylesheet (standalone mode)...")
        stylesheet_path = os.path.join(stax_root, 'resources', 'style.qss')
        print("[show_stax_panel] Stylesheet path: {}".format(stylesheet_path))
        
        if os.path.exists(stylesheet_path):
            print("[show_stax_panel]   [OK] Stylesheet file exists")
            try:
                with open(stylesheet_path, 'r') as f:
                    stylesheet = f.read()
                    # Replace icon paths with absolute paths
                    resources_dir = os.path.join(stax_root, 'resources', 'icons')
                    unchecked_path = os.path.join(resources_dir, 'unchecked.svg').replace('\\', '/')
                    checked_path = os.path.join(resources_dir, 'checked.svg').replace('\\', '/')
                    stylesheet = stylesheet.replace('url(:/icons/unchecked.svg)', 'url({})'.format(unchecked_path))
                    stylesheet = stylesheet.replace('url(:/icons/checked.svg)', 'url({})'.format(checked_path))
                    app.setStyleSheet(stylesheet)
                    print("[show_stax_panel]   [OK] Stylesheet applied ({} chars)".format(len(stylesheet)))
                    if logger:
                        logger.info("Stylesheet applied: {} ({} characters)".format(stylesheet_path, len(stylesheet)))
            except Exception as e:
                print("[show_stax_panel]   [WARN] Failed to load stylesheet: {}".format(e))
                if logger:
                    logger.warning("Failed to load stylesheet: {}".format(e))
        else:
            print("[show_stax_panel]   [WARN] Stylesheet file not found: {}".format(stylesheet_path))
            if logger:
                logger.warning("Stylesheet file not found: {}".format(stylesheet_path))
    elif NUKE_MODE:
        print("[show_stax_panel] NUKE_MODE: Skipping stylesheet (using Nuke's default styling)")
        if logger:
            logger.info("Skipped stylesheet in Nuke mode")
    
    # Create and show panel
    print("[show_stax_panel] Checking NUKE_MODE: {}".format(NUKE_MODE))
    if logger:
        logger.info("NUKE_MODE = {}".format(NUKE_MODE))
    
    if NUKE_MODE:
        print("[show_stax_panel] Using nukescripts.panels.registerWidgetAsPanel...")
        # Use nukescripts.panels for proper Nuke integration
        try:
            print("[show_stax_panel] Calling registerWidgetAsPanel('panel.StaXPanel', 'StaX Asset Manager', 'uk.co.thefoundry.StaXPanel')...")
            panel = nukescripts.panels.registerWidgetAsPanel(
                'panel.StaXPanel',
                'StaX Asset Manager',
                'uk.co.thefoundry.StaXPanel'
            )
            print("[show_stax_panel]   [OK] Panel registered")
            if logger:
                logger.info("Panel registered: panel.StaXPanel")
            
            print("[show_stax_panel] Adding panel to pane...")
            panel.addToPane()
            print("[show_stax_panel]   [OK] Panel added to pane")
            if logger:
                logger.info("Panel added to pane successfully")
            
            print("[show_stax_panel] [OK] Panel shown successfully")
            print("="*80 + "\n")
            if logger:
                logger.info("show_stax_panel() completed successfully")
                logger.separator()
                
        except Exception as e:
            print("[show_stax_panel]   [ERROR] CRITICAL: Failed to register panel: {}".format(e))
            if logger:
                logger.exception("Failed to register panel with nukescripts")
            
            print("[show_stax_panel] Falling back to standalone dialog...")
            try:
                panel = StaXPanel()
                panel.show()
                print("[show_stax_panel]   [OK] Fallback dialog shown")
                if logger:
                    logger.info("Fallback: Showed StaXPanel as standalone dialog")
            except Exception as fallback_error:
                print("[show_stax_panel]   [ERROR] CRITICAL: Fallback also failed: {}".format(fallback_error))
                if logger:
                    logger.exception("Fallback dialog creation failed")
                raise
    else:
        # Running outside Nuke - show as dialog
        print("[show_stax_panel] Running in standalone mode (NUKE_MODE=False)")
        if logger:
            logger.info("Running in standalone mode - showing as dialog")
        
        try:
            panel = StaXPanel()
            print("[show_stax_panel]   [OK] StaXPanel created")
            panel.show()
            print("[show_stax_panel]   [OK] Panel shown as dialog")
            if logger:
                logger.info("Panel shown as standalone dialog")
        except Exception as e:
            print("[show_stax_panel]   [ERROR] CRITICAL: Failed to create/show panel: {}".format(e))
            if logger:
                logger.exception("Failed to create/show panel in standalone mode")
            raise
    
    print("[show_stax_panel] Returning panel object")
    return panel


def main():
    """
    Standalone launcher for testing outside Nuke.
    """
    print("\n" + "="*80)
    print("[main] Standalone launcher starting")
    print("="*80)
    if logger:
        logger.info("="*80)
        logger.info("main() function - standalone launcher")
        logger.info("="*80)
    
    print("[main] Getting/creating QApplication...")
    try:
        app = QtWidgets.QApplication.instance()
        if not app:
            print("[main]   Creating new QApplication instance...")
            app = QtWidgets.QApplication(sys.argv)
            print("[main]   [OK] QApplication created")
            if logger:
                logger.info("Created new QApplication instance")
        else:
            print("[main]   [OK] Using existing QApplication instance")
            if logger:
                logger.info("Using existing QApplication instance")
    except Exception as e:
        print("[main]   [ERROR] CRITICAL: Failed to get/create QApplication: {}".format(e))
        if logger:
            logger.exception("Failed to get/create QApplication")
        raise
    
    # # Apply stylesheet
    # stylesheet_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
    # if os.path.exists(stylesheet_path):
    #     try:
    #         with open(stylesheet_path, 'r') as f:
    #             stylesheet = f.read()
    #             app.setStyleSheet(stylesheet)
    #             print("Applied stylesheet from: {}".format(stylesheet_path))
    #     except Exception as e:
    #         print("Failed to load stylesheet: {}".format(e))
    
    # Create and show panel
    print("[main] Creating StaXPanel...")
    try:
        panel = StaXPanel()
        print("[main]   [OK] StaXPanel created")
        if logger:
            logger.info("StaXPanel created successfully")
    except Exception as e:
        print("[main]   [ERROR] CRITICAL: Failed to create StaXPanel: {}".format(e))
        if logger:
            logger.exception("Failed to create StaXPanel")
        raise
    
    print("[main] Showing panel...")
    try:
        panel.show()
        print("[main]   [OK] Panel shown")
        if logger:
            logger.info("Panel shown successfully")
    except Exception as e:
        print("[main]   [ERROR] Failed to show panel: {}".format(e))
        if logger:
            logger.exception("Failed to show panel")
        raise
    
    print("[main] Starting Qt event loop...")
    print("="*80 + "\n")
    if logger:
        logger.info("Starting Qt event loop (app.exec_)")
        logger.separator()
    
    try:
        exit_code = app.exec_()
        print("\n[main] Qt event loop exited with code: {}".format(exit_code))
        if logger:
            logger.info("Qt event loop exited with code: {}".format(exit_code))
        sys.exit(exit_code)
    except Exception as e:
        print("[main]   [ERROR] Event loop crashed: {}".format(e))
        if logger:
            logger.exception("Qt event loop crashed")
        raise


if __name__ == '__main__':
    main()
