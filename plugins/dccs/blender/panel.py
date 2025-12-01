# -*- coding: utf-8 -*-
"""
StaX Blender Panel
Blender-specific panel launcher for StaX asset management system
Implements window re-parenting, event loop, and IPC server
"""

import os
import sys

# Bootstrap dependencies first
import dependency_bootstrap
dependency_bootstrap.bootstrap()

from src.debug_manager import DebugManager
DebugManager.bootstrap_from_config()

print("\n" + "="*80)
print("[blender_panel] Module loading started...")
print("="*80)

# Check for Blender
BLENDER_MODE = False
try:
    import bpy
    BLENDER_MODE = True
    print("[blender_panel] [OK] Blender environment detected")
except ImportError:
    BLENDER_MODE = False
    print("[blender_panel] [WARN] Running outside Blender environment (mock mode)")

# Setup paths
current_dir = os.path.dirname(__file__)
stax_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if stax_root not in sys.path:
    sys.path.insert(0, stax_root)

# Import PySide2 (with fallback to PySide)
PYSIDE_AVAILABLE = False
try:
    from PySide2 import QtWidgets, QtCore, QtGui
    PYSIDE_AVAILABLE = True
    PYSIDE_VERSION = 2
    print("[blender_panel] [OK] PySide2 imported")
except ImportError:
    try:
        from PySide import QtWidgets, QtCore, QtGui
        PYSIDE_AVAILABLE = True
        PYSIDE_VERSION = 1
        print("[blender_panel] [OK] PySide imported")
    except ImportError:
        PYSIDE_AVAILABLE = False
        print("[blender_panel] [ERROR] PySide not available - GUI will not work")

# Import core modules
try:
    from src.config import Config
    from src.db_manager import DatabaseManager
    from src.ingestion_core import IngestionCore
    from src.extensibility_hooks import ProcessorManager
    from src.icon_loader import get_icon
    from src.ui import (
        AdvancedSearchDialog,
        AddStackDialog,
        AddListDialog,
        AddSubListDialog,
        CreatePlaylistDialog,
        AddToPlaylistDialog,
        LoginDialog,
        EditElementDialog,
        SelectListDialog,
        IngestLibraryDialog,
        MediaInfoPopup,
        StacksListsPanel,
        MediaDisplayWidget,
        HistoryPanel,
        SettingsPanel,
    )
    print("[blender_panel] [OK] Core modules imported")
except Exception as e:
    print("[blender_panel] [ERROR] Failed to import core modules: {}".format(e))
    import traceback
    traceback.print_exc()
    raise

# Import Blender-specific modules
from .bridge import BlenderBridge, BlenderIntegration as BlenderIntegrationHelper
from .integration import BlenderIntegration
from .ipc_server import IPCServer
from .dcc_base import ReferenceManager

print("[blender_panel] [OK] All imports successful")
print("="*80 + "\n")


class StaXBlenderPanel(QtWidgets.QWidget):
    """
    StaX panel widget for embedding in Blender.
    Uses OS-level window re-parenting and non-blocking event loop.
    """
    
    _instance = None  # Singleton instance
    
    def __init__(self, parent=None):
        """Initialize Blender panel."""
        print("\n[StaXBlenderPanel.__init__] Initialization started...")
        
        # Singleton pattern - only one instance allowed
        if StaXBlenderPanel._instance is not None:
            print("[StaXBlenderPanel] WARNING: Instance already exists, returning existing instance")
            return StaXBlenderPanel._instance
        
        try:
            super(StaXBlenderPanel, self).__init__(parent)
            StaXBlenderPanel._instance = self
        except Exception as e:
            print("[StaXBlenderPanel.__init__] ERROR in super().__init__: {}".format(e))
            import traceback
            traceback.print_exc()
            raise
        
        # Initialize Blender integration
        self.blender_integration = BlenderIntegration()
        
        # Setup QApplication
        if PYSIDE_AVAILABLE:
            self.app = self.blender_integration.setup_qapplication()
        else:
            self.app = None
            print("[StaXBlenderPanel] ERROR: Cannot proceed without PySide")
            return
        
        # Initialize core components
        try:
            self.config = Config()
            self.config.ensure_directories()
            
            db_path = self.config.get('database_path')
            self.db = DatabaseManager(db_path)
            self.config.load_from_database(self.db)
            DebugManager.sync_from_config(self.config)
            print("[StaXBlenderPanel.__init__] Core components initialized")
        except Exception as e:
            print("[StaXBlenderPanel.__init__] ERROR initializing core components: {}".format(e))
            import traceback
            traceback.print_exc()
            raise
        
        # Initialize Blender bridge
        mock_mode = not BLENDER_MODE
        self.blender_bridge = BlenderBridge(mock_mode=mock_mode)
        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        
        self.blender_integration_helper = BlenderIntegrationHelper(
            self.blender_bridge,
            self.db,
            config=self.config,
            ingestion_core=self.ingestion,
            processor_manager=self.processor_manager
        )
        
        # User authentication
        self.current_user = None
        self.is_admin = False
        
        # Setup UI
        self.setup_ui()
        
        # Setup window re-parenting (optional - can fail gracefully)
        if BLENDER_MODE:
            try:
                self.setup_window_reparenting()
            except Exception as e:
                print("[StaXBlenderPanel.__init__] WARNING: Window re-parenting failed: {}".format(e))
                # Continue without re-parenting - window will be standalone
        
        # Setup event loop (optional - can fail gracefully)
        if BLENDER_MODE:
            try:
                self.blender_integration.setup_event_loop()
            except Exception as e:
                print("[StaXBlenderPanel.__init__] WARNING: Event loop setup failed: {}".format(e))
                # Continue without event loop - will use standard Qt event processing
        
        # Setup IPC server (will be started after panel is shown)
        self.ipc_server = IPCServer(command_handler=self._execute_ipc_command)
        self.ipc_server.set_command_executor(self._execute_ipc_command)
        
        # Setup input filter
        if BLENDER_MODE:
            self.blender_integration.setup_input_filter(self)
        
        # Register with reference manager
        ReferenceManager.register_widget(self)
        
        print("[StaXBlenderPanel.__init__] [OK] Initialization complete!\n")
    
    def setup_ui(self):
        """Setup the panel UI."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Toolbar
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)
        
        # Main content splitter
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: Stacks/Lists panel
        self.stacks_panel = StacksListsPanel(self.db, self.config, main_window=self)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        self.stacks_panel.stack_selected.connect(self.on_stack_selected)
        self.stacks_panel.favorites_selected.connect(self.on_favorites_selected)
        self.stacks_panel.playlist_selected.connect(self.on_playlist_selected)
        self.stacks_panel.tags_filter_changed.connect(self.on_tags_filter_changed)
        self.main_splitter.addWidget(self.stacks_panel)
        
        # Center: Media display
        # Use mock NukeBridge for media display (it doesn't need real Nuke)
        from plugins.dccs.nuke.bridge import NukeBridge
        mock_nuke_bridge = NukeBridge(mock_mode=True)
        self.media_display = MediaDisplayWidget(self.db, self.config, mock_nuke_bridge, main_window=self)
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        self.main_splitter.addWidget(self.media_display)
        
        # Set splitter sizes
        self.main_splitter.setSizes([260, 900])
        main_layout.addWidget(self.main_splitter)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("padding: 5px; color: #16c6b0;")
        main_layout.addWidget(self.status_label)
        
        # Store toolbar reference
        self.toolbar = toolbar
    
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
        
        return toolbar
    
    def setup_window_reparenting(self):
        """Setup OS-level window re-parenting to Blender main window."""
        if not PYSIDE_AVAILABLE:
            return
        
        # Get Blender window handle
        parent_handle = self.blender_integration.get_main_window_handle()
        if not parent_handle:
            print("[StaXBlenderPanel] WARNING: Could not get Blender window handle")
            return
        
        # Re-parent this widget to Blender window
        success = self.blender_integration.reparent_window(self, parent_handle)
        if success:
            print("[StaXBlenderPanel] Successfully re-parented to Blender window")
        else:
            print("[StaXBlenderPanel] WARNING: Failed to re-parent window")
    
    def _execute_ipc_command(self, command, args=None, kwargs=None):
        """Execute IPC command (called from IPC server).
        
        Args:
            command (str): Command string to execute
            args (list): Positional arguments
            kwargs (dict): Keyword arguments
            
        Returns:
            Result of command execution
        """
        try:
            # Parse command string (e.g., "stax.blender.gui.launch_browser_panel")
            if command == "stax.blender.gui.launch_browser_panel":
                # Show the panel
                self.show()
                self.raise_()
                return {'success': True, 'message': 'Panel shown'}
            elif command == "stax.blender.gui.insert_element":
                # Insert element into Blender
                element_id = args[0] if args else kwargs.get('element_id')
                if element_id:
                    obj = self.blender_integration_helper.insert_element(element_id)
                    return {'success': True, 'object': str(obj)}
                return {'success': False, 'error': 'No element_id provided'}
            else:
                return {'success': False, 'error': 'Unknown command: {}'.format(command)}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def process_ipc_commands(self):
        """Process queued IPC commands (call from main thread)."""
        if self.ipc_server:
            self.ipc_server.process_commands()
    
    def show_status(self, message):
        """Update status label."""
        self.status_label.setText(message)
    
    def on_list_selected(self, list_id):
        """Handle list selection."""
        self.media_display.load_elements(list_id)
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst['stack_fk'])
            if stack:
                self.show_status("Viewing: {} > {}".format(stack['name'], lst['name']))
    
    def on_stack_selected(self, stack_id):
        """Handle stack selection."""
        if not self.config.get('show_entire_stack_elements', False):
            return
        # Implementation similar to Nuke panel
        self.show_status("Viewing stack: {}".format(stack_id))
    
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
    
    def on_tags_filter_changed(self, tags):
        """Handle tags filter change."""
        if tags:
            self.media_display.load_elements_by_tags(tags)
            self.show_status("Filtering by tags: {}".format(", ".join(tags)))
    
    def on_element_double_clicked(self, element_id):
        """Handle element double-click (insert into Blender)."""
        try:
            self.blender_integration_helper.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.show_status("Inserted: {}".format(element['name']))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def ingest_files(self):
        """Open file dialog to ingest files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Files to Ingest", "", "All Files (*.*)"
        )
        if not files:
            return
        
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
        
        QtWidgets.QMessageBox.information(
            self,
            "Ingestion Complete",
            "Ingested {} files successfully.\n{} errors.".format(success_count, error_count)
        )
        
        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)
    
    def ingest_library(self):
        """Open Library Ingest dialog."""
        dialog = IngestLibraryDialog(self.db, self.ingestion, self.config, self)
        if dialog.exec_():
            self.stacks_panel.load_data()
    
    def show_history(self):
        """Show history dialog."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Ingestion History")
        dialog.resize(800, 500)
        
        dialog_layout = QtWidgets.QVBoxLayout(dialog)
        history_panel = HistoryPanel(self.db)
        dialog_layout.addWidget(history_panel)
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)
        
        history_panel.load_history()
        dialog.show()  # Use show() instead of exec_() for non-blocking
    
    def show_settings(self):
        """Show settings dialog."""
        if not self.is_admin:
            self.show_login()
            if not self.is_admin:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Access Denied",
                    "Settings panel requires administrator privileges."
                )
                return
        
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.resize(900, 600)
        
        dialog_layout = QtWidgets.QVBoxLayout(dialog)
        settings_panel = SettingsPanel(self.config, self.db, main_window=self)
        settings_panel.settings_changed.connect(self.on_settings_changed)
        dialog_layout.addWidget(settings_panel)
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)
        
        dialog.show()  # Use show() instead of exec_() for non-blocking
    
    def show_login(self):
        """Show login dialog."""
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = self.current_user and self.current_user.get('role') == 'admin'
            
            username = self.current_user['username'] if self.current_user else 'Guest'
            role_text = ' (Admin)' if self.is_admin else ''
            self.user_label.setText("User: {}{}".format(username, role_text))
            self.show_status("Logged in as: {}".format(username))
    
    def on_settings_changed(self):
        """Handle settings change."""
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.show_status("Settings updated")
    
    def show_advanced_search(self):
        """Show advanced search dialog."""
        if not hasattr(self, 'advanced_search_dialog') or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()
    
    def closeEvent(self, event):
        """Handle close event."""
        # Cleanup
        if self.ipc_server:
            self.ipc_server.stop()
        if self.blender_integration:
            self.blender_integration.cleanup()
        ReferenceManager.unregister_widget(self)
        StaXBlenderPanel._instance = None
        event.accept()


# Global panel instance
_panel_instance = None

# Store reference for IPC access
def get_panel_instance():
    """Get the current panel instance."""
    return _panel_instance


def show_stax_panel():
    """Show StaX panel in Blender."""
    global _panel_instance
    
    print("\n[show_stax_panel] Function called")
    
    try:
        # Ensure QApplication exists
        app = QtWidgets.QApplication.instance()
        if app is None:
            import sys
            app = QtWidgets.QApplication(sys.argv)
            print("[show_stax_panel] Created QApplication")
        
        if _panel_instance is None:
            print("[show_stax_panel] Creating StaXBlenderPanel...")
            _panel_instance = StaXBlenderPanel()
            print("[show_stax_panel] Panel created successfully")
        
        # Start IPC server if not already started
        if _panel_instance.ipc_server and not _panel_instance.ipc_server.running:
            _panel_instance.ipc_server.start()
        
        _panel_instance.show()
        _panel_instance.raise_()
        _panel_instance.activateWindow()
        
        # Process IPC commands periodically
        if _panel_instance.app:
            # Use QTimer to process IPC commands
            timer = QtCore.QTimer()
            timer.timeout.connect(_panel_instance.process_ipc_commands)
            timer.start(50)  # 50ms = 20Hz
        
        # On Linux, need to process events (like Prism does)
        import platform
        if platform.system() == "Linux":
            app.processEvents()
        
        print("[show_stax_panel] Panel shown successfully")
        return _panel_instance
        
    except Exception as e:
        print("[show_stax_panel] ERROR: {}".format(e))
        import traceback
        traceback.print_exc()
        raise


def add_to_library():
    """Add selected Blender objects to StaX library."""
    if not BLENDER_MODE:
        print("[add_to_library] WARNING: Not running in Blender")
        return
    
    try:
        import bpy
        selected = bpy.context.selected_objects
        if not selected:
            print("[add_to_library] No objects selected")
            return
        
        # Show panel if not visible
        panel = show_stax_panel()
        
        # Open ingest dialog
        panel.ingest_files()
        
    except Exception as e:
        print("[add_to_library] ERROR: {}".format(e))
        import traceback
        traceback.print_exc()

