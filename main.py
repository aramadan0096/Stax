# -*- coding: utf-8 -*-
"""
Main GUI for StaX
PySide2-based user interface with drag-and-drop support
Python 2.7 compatible
"""

import os
import sys

import dependency_bootstrap

dependency_bootstrap.bootstrap()

from PySide2 import QtWidgets, QtCore, QtGui

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

from src.config import Config
from src.db_manager import DatabaseManager
from src.ingestion_core import IngestionCore
from src.nuke_bridge import NukeBridge, NukeIntegration
from src.extensibility_hooks import ProcessorManager
from src.icon_loader import get_icon
from src.video_player_widget import VideoPlayerWidget

# Import all UI widgets from ui module
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


class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        # Initialize core components
        self.config = Config()
        self.config.ensure_directories()
        
        self.db = DatabaseManager(self.config.get('database_path'))
        
        # Load database-stored settings (previews_path, etc.)
        self.config.load_from_database(self.db)
        
        self.nuke_bridge = NukeBridge(mock_mode=self.config.get('nuke_mock_mode'))
        self.nuke_integration = NukeIntegration(self.nuke_bridge, self.db)
        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        self._stored_left_width = None
        self.active_view = ('none', None)
        self._view_before_tags = None
        self._suspend_tag_restore = False
        
        # User authentication - deferred login (only when accessing settings or delete operations)
        self.current_user = None
        self.is_admin = False
        
        self.setWindowTitle("Stax")
        self.resize(1400, 800)
        
        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'logo.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        
        self.setup_ui()
        self.setup_shortcuts()
        
        # Skip login dialog - login will be requested only when needed
    
    def setup_ui(self):
        """Setup the main window UI."""
        # Central widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)

        # Global toolbar
        self.setup_toolbar()
        
        # Main splitter for left panel, center content, and right preview pane
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)

        # Left: Stacks/Lists panel
        self.stacks_panel = StacksListsPanel(self.db, self.config, main_window=self)
        self.stacks_panel.setMinimumWidth(260)
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
        self.main_splitter.setStretchFactor(1, 1)

        # Right: Video player preview pane (hidden by default)
        self.video_player_pane = VideoPlayerWidget(self.db, self.config, self)
        self.video_player_pane.closed.connect(self.on_preview_pane_closed)
        self.video_player_pane.hide()
        self.main_splitter.addWidget(self.video_player_pane)
        self.preview_pane_expanded_width = 360

        # Set splitter sizes (left: 250, center: 900, right: 400)
        self.main_splitter.setSizes([280, 920, 360])

        layout.addWidget(self.main_splitter)
        
        # Connect selection changes to update preview pane
        self.media_display.gallery_view.itemSelectionChanged.connect(self.on_selection_changed)
        self.media_display.table_view.itemSelectionChanged.connect(self.on_selection_changed)
        
        # Create dockable panels
        
        # History panel (dockable)
        self.history_dock = QtWidgets.QDockWidget("History", self)
        self.history_panel = HistoryPanel(self.db)
        self.history_dock.setWidget(self.history_panel)
        self.history_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)
        
        # Settings panel (dockable)
        self.settings_dock = QtWidgets.QDockWidget("Settings", self)
        self.settings_panel = SettingsPanel(self.config, self.db, main_window=self)
        self.settings_panel.settings_changed.connect(self.on_settings_changed)
        self.settings_dock.setWidget(self.settings_panel)
        self.settings_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.settings_dock)
        
        # Menu bar
        self.create_menus()
        
        # Status bar
        self.statusBar().showMessage("Ready")

    def setup_toolbar(self):
        """Create and configure the top toolbar."""
        self.toolbar = QtWidgets.QToolBar("Main Toolbar", self)
        self.toolbar.setIconSize(QtCore.QSize(20, 20))
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("QToolBar { spacing: 6px; padding: 4px; }")
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.toolbar)

        ingest_action = QtWidgets.QAction(get_icon('import', size=20), "Ingest Files", self)
        ingest_action.setToolTip("Ingest files into StaX (Ctrl+I)")
        ingest_action.triggered.connect(self.ingest_files)
        self.toolbar.addAction(ingest_action)

        ingest_library_action = QtWidgets.QAction(get_icon('folder', size=20), "Ingest Library", self)
        ingest_library_action.setToolTip("Bulk ingest folder structures (Ctrl+Shift+I)")
        ingest_library_action.triggered.connect(self.ingest_library)
        self.toolbar.addAction(ingest_library_action)

        self.toolbar.addSeparator()

        search_action = QtWidgets.QAction(get_icon('search', size=20), "Search", self)
        search_action.setToolTip("Advanced search (Ctrl+F)")
        search_action.triggered.connect(self.show_advanced_search)
        self.toolbar.addAction(search_action)

        favorites_action = QtWidgets.QAction(get_icon('favorite', size=20), "Favorites", self)
        favorites_action.setToolTip("Show favorites across stacks")
        favorites_action.triggered.connect(self.on_favorites_selected)
        self.toolbar.addAction(favorites_action)
        self.favorites_action = favorites_action

        self.toolbar.addSeparator()

        # Register Toolset action - hidden in standalone mode (only show in Nuke)
        # Since this is standalone, we don't add this action at all
        # toolset_action = QtWidgets.QAction(get_icon('add', size=20), "Register Toolset", self)
        # toolset_action.setToolTip("Save selected Nuke nodes as toolset (Ctrl+Shift+T)")
        # toolset_action.triggered.connect(self.register_toolset)
        # self.toolbar.addAction(toolset_action)

        history_action = QtWidgets.QAction(get_icon('history', size=20), "History", self)
        history_action.setToolTip("Show ingestion history (Ctrl+2)")
        history_action.triggered.connect(self.toggle_history)
        self.toolbar.addAction(history_action)

        settings_action = QtWidgets.QAction(get_icon('settings', size=20), "Settings", self)
        settings_action.setToolTip("Open settings panel (Ctrl+3)")
        settings_action.triggered.connect(self.toggle_settings)
        self.toolbar.addAction(settings_action)

    def toggle_focus_mode(self, checked):
        """Hide or show navigation panel, toolbar, and panels for distraction-free browsing."""
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return

        if checked:
            # Store the left width before hiding
            self._stored_left_width = sizes[0] if sizes[0] > 0 else self.stacks_panel.minimumWidth()
            # Give left panel space to center, keep preview pane unchanged
            total_width = self.main_splitter.width()
            preview_width = sizes[2]
            center_width = max(400, total_width - preview_width)
            sizes = [0, center_width, preview_width]
            self.stacks_panel.hide()
            self.toolbar.hide()  # Hide toolbar in focus mode
            
            # Close panels
            if hasattr(self, 'video_player_dock') and self.video_player_dock.isVisible():
                self.video_player_dock.hide()
            if hasattr(self, 'history_dock') and self.history_dock.isVisible():
                self.history_dock.hide()
            if hasattr(self, 'settings_dock') and self.settings_dock.isVisible():
                self.settings_dock.hide()
            
            # Hide pagination
            if hasattr(self.media_display, 'pagination'):
                self.media_display.pagination.hide()
        else:
            # Restore the left panel
            restore_width = self._stored_left_width or self.stacks_panel.minimumWidth()
            total_width = self.main_splitter.width()
            preview_width = sizes[2]
            center_width = max(400, total_width - restore_width - preview_width)
            sizes = [restore_width, center_width, preview_width]
            self.stacks_panel.show()
            self.toolbar.show()  # Show toolbar when exiting focus mode
            
            # Restore pagination visibility if there are elements
            if hasattr(self.media_display, 'pagination') and self.config.get('pagination_enabled', True):
                if len(self.media_display.current_elements) > 0:
                    self.media_display.pagination.show()

        self.main_splitter.setSizes(sizes)


    def expand_preview_pane(self):
        """Expand or show the preview pane without crushing other panes."""
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return

        total = sum(sizes)
        left_width = max(self.stacks_panel.minimumWidth(), sizes[0])
        available = max(0, total - left_width)

        # Target preview width while respecting available space
        preview_width = min(self.preview_pane_expanded_width, max(320, available // 3))
        preview_width = max(280, preview_width)
        if preview_width > available - 420:
            preview_width = max(240, available - 420)

        if preview_width < 200:
            preview_width = max(0, available - 400)

        center_width = max(400, available - preview_width)

        if preview_width <= 0:
            preview_width = 0
            center_width = available

        self.preview_pane_expanded_width = max(self.preview_pane_expanded_width, preview_width)
        self.main_splitter.setSizes([left_width, center_width, preview_width])

        if preview_width > 0 and not self.video_player_pane.isVisible():
            self.video_player_pane.show()

    def collapse_preview_pane(self):
        """Collapse preview pane but remember last width for smooth restores."""
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return

        if sizes[2] > 0:
            self.preview_pane_expanded_width = sizes[2]

        sizes[1] += sizes[2]
        sizes[2] = 0
        self.main_splitter.setSizes(sizes)
        self.video_player_pane.hide()
    
    def create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        ingest_action = QtWidgets.QAction("Ingest Files...", self)
        ingest_action.setIcon(get_icon('import', size=16))
        ingest_action.setShortcut("Ctrl+I")
        ingest_action.triggered.connect(self.ingest_files)
        file_menu.addAction(ingest_action)
        
        ingest_library_action = QtWidgets.QAction("Ingest Library...", self)
        ingest_library_action.setIcon(get_icon('folder', size=16))
        ingest_library_action.setShortcut("Ctrl+Shift+I")
        ingest_library_action.triggered.connect(self.ingest_library)
        file_menu.addAction(ingest_library_action)
        
        file_menu.addSeparator()
        
        logout_action = QtWidgets.QAction("Logout", self)
        logout_action.setShortcut("Ctrl+L")
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)
        
        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Search menu
        search_menu = menubar.addMenu("Search")
        
        advanced_search_action = QtWidgets.QAction("Advanced Search...", self)
        advanced_search_action.setIcon(get_icon('search', size=16))
        advanced_search_action.setShortcut("Ctrl+F")
        advanced_search_action.triggered.connect(self.show_advanced_search)
        search_menu.addAction(advanced_search_action)
        
        # Nuke menu - hidden in standalone mode (only available in Nuke)
        # nuke_menu = menubar.addMenu("Nuke")
        # register_toolset_action = QtWidgets.QAction("Register Selection as Toolset...", self)
        # register_toolset_action.setIcon(get_icon('add', size=16))
        # register_toolset_action.setShortcut("Ctrl+Shift+T")
        # register_toolset_action.triggered.connect(self.register_toolset)
        # register_toolset_action.setToolTip("Save selected Nuke nodes as a reusable toolset")
        # nuke_menu.addAction(register_toolset_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        history_action = QtWidgets.QAction("History Panel", self)
        history_action.setIcon(get_icon('history', size=16))
        history_action.setShortcut("Ctrl+2")
        history_action.setCheckable(True)
        history_action.triggered.connect(self.toggle_history)
        view_menu.addAction(history_action)
        
        settings_action = QtWidgets.QAction("Settings Panel", self)
        settings_action.setIcon(get_icon('settings', size=16))
        settings_action.setShortcut("Ctrl+3")
        settings_action.setCheckable(True)
        settings_action.triggered.connect(self.toggle_settings)
        view_menu.addAction(settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QtWidgets.QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+2 for history
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+2"), self, self.toggle_history)
        
        # Ctrl+3 for settings
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+3"), self, self.toggle_settings)
    
    def show_login(self, required=False):
        """Show login dialog.
        
        Args:
            required (bool): If True, prevents cancellation. If False, allows canceling login.
        
        Returns:
            bool: True if user logged in successfully, False if cancelled
        """
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = self.current_user and self.current_user.get('role') == 'admin'
            
            # Update window title with username
            username = self.current_user['username'] if self.current_user else 'Guest'
            role_text = ' (Admin)' if self.is_admin else ''
            self.setWindowTitle("Stax - {}{}".format(username, role_text))
            
            self.statusBar().showMessage("Logged in as: {}".format(username))
            return True
        else:
            # User cancelled login
            if required:
                # If login is required (e.g., for settings), return False
                return False
            return False
    
    def check_admin_permission(self, action_name="this action"):
        """
        Check if current user has admin permissions.
        Shows error dialog if not. Requests login if not logged in.
        
        Args:
            action_name (str): Name of the action being attempted
            
        Returns:
            bool: True if user is admin
        """
        # Check if user is logged in
        if not self.current_user:
            # Request login first
            if not self.show_login(required=True):
                QtWidgets.QMessageBox.information(
                    self,
                    "Login Required",
                    "You must login to perform {}.".format(action_name)
                )
                return False
        
        # Check if user is admin
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
    
    def toggle_history(self):
        """Toggle history panel visibility."""
        visible = not self.history_dock.isVisible()
        self.history_dock.setVisible(visible)
        if visible:
            self.history_panel.load_history()
    
    def toggle_settings(self):
        """Toggle settings panel visibility - requires login."""
        # Check if user is logged in
        if not self.current_user:
            # Request login first
            if not self.show_login(required=True):
                QtWidgets.QMessageBox.information(
                    self,
                    "Login Required",
                    "You must login to access settings."
                )
                return
        
        self.settings_dock.setVisible(not self.settings_dock.isVisible())
    
    def on_list_selected(self, list_id):
        """Handle list selection."""
        if getattr(self.stacks_panel, 'get_selected_tags', None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_elements(list_id)
        
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst['stack_fk'])
            if stack:
                self.statusBar().showMessage("Viewing: {} > {}".format(stack['name'], lst['name']))
        self.active_view = ('list', list_id)
        self._view_before_tags = None
    
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
            self.statusBar().showMessage("Viewing: {} (all lists)".format(stack['name']))
        self.active_view = ('stack', stack_id)
    
    def on_favorites_selected(self):
        """Handle favorites button click."""
        if getattr(self.stacks_panel, 'get_selected_tags', None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_favorites()
        self.statusBar().showMessage("Viewing: Favorites")
        self.active_view = ('favorites', None)
        self._view_before_tags = None
    
    def on_playlist_selected(self, playlist_id):
        """Handle playlist selection."""
        if getattr(self.stacks_panel, 'get_selected_tags', None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_playlist(playlist_id)
        playlist = self.db.get_playlist_by_id(playlist_id)
        if playlist:
            self.statusBar().showMessage("Viewing Playlist: {}".format(playlist['name']))
        self.active_view = ('playlist', playlist_id)
        self._view_before_tags = None
    
    def on_element_double_clicked(self, element_id):
        """Handle element double-click (insert into Nuke)."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted: {}".format(element['name']))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def on_selection_changed(self):
        """Handle element selection change - update preview pane."""
        selected_ids = self.media_display.get_selected_element_ids()
        
        if len(selected_ids) == 1:
            # Single element selected - show preview pane
            element_id = selected_ids[0]
            self.expand_preview_pane()
            self.video_player_pane.load_element(element_id)
        elif len(selected_ids) > 1:
            # Multiple elements selected - hide preview pane
            self.video_player_pane.clear()
            self.collapse_preview_pane()
        else:
            # No selection - keep pane visible but cleared if it was already visible
            if self.video_player_pane.isVisible():
                self.video_player_pane.clear()
    
    def on_preview_pane_closed(self):
        """Handle preview pane close button."""
        self.video_player_pane.clear()
        self.collapse_preview_pane()

    def on_tags_filter_changed(self, tags):
        tags = [t for t in tags if t]
        if not tags:
            if self._suspend_tag_restore:
                self._suspend_tag_restore = False
                self._view_before_tags = None
                return
            if self.active_view[0] == 'tags' and self._view_before_tags:
                self.active_view = self._view_before_tags
            self._view_before_tags = None
            self.restore_active_view()
            return

        if not self._view_before_tags and self.active_view[0] != 'tags':
            self._view_before_tags = self.active_view

        self.active_view = ('tags', tuple(tags))
        self.media_display.load_elements_by_tags(tags)
        self.statusBar().showMessage("Filtering by tags: {}".format(', '.join(tags)))

    def restore_active_view(self):
        mode, value = self.active_view
        if mode == 'list' and value:
            self.media_display.load_elements(value)
            return
        if mode == 'favorites':
            self.media_display.load_favorites()
            return
        if mode == 'playlist' and value:
            self.media_display.load_playlist(value)
            return
        if mode == 'tags' and value:
            self.media_display.load_elements_by_tags(list(value))
            return
        self.media_display.show_empty_state()
    
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
        dialog = RegisterToolsetDialog(self.db, self.nuke_bridge, self.config, self)
        if dialog.exec_():
            # Refresh media display to show new toolset
            if hasattr(self.media_display, 'current_list_id') and self.media_display.current_list_id:
                self.media_display.load_elements(self.media_display.current_list_id)
            self.statusBar().showMessage("Toolset registered successfully")
    
    def on_settings_changed(self):
        """Handle settings change."""
        # Reload processor manager
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.statusBar().showMessage("Settings updated")
    
    def show_advanced_search(self):
        """Show advanced search dialog."""
        if not hasattr(self, 'advanced_search_dialog') or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()
    
    def on_advanced_search_result(self, element_id):
        """Handle result selection from advanced search."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted from search: {}".format(element['name']))
                QtWidgets.QMessageBox.information(
                    self,
                    "Element Inserted",
                    "Element '{}' has been inserted into Nuke.".format(element['name'])
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def show_about(self):
        """Show about dialog."""
        QtWidgets.QMessageBox.about(
            self,
            "About Stax",
            "<h3>Stax</h3>"
            "<p>Version 0.1.0 (nightly)</p>"
            "<p>Advanced Stock Management for VFX Studios</p>"
            "<p>Author: Ahmed Ramadan</p>"
            "<p>Website: <a href='https://www.linkedin.com/in/a-ramadan0096/'>LinkedIn</a></p>"
            "<p>License: MIT</p>"
        )




def main():
    """Main entry point."""
    # Enable High DPI scaling before creating the app (improves appearance on HiDPI displays)
    try:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style and load styles early
    app.setStyle('Fusion')
    stylesheet_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
    if os.path.exists(stylesheet_path):
        try:
            with open(stylesheet_path, 'r') as f:
                stylesheet = f.read()
                # Replace icon paths with absolute paths
                resources_dir = os.path.join(os.path.dirname(__file__), 'resources', 'icons')
                unchecked_path = os.path.join(resources_dir, 'unchecked.svg').replace('\\', '/')
                checked_path = os.path.join(resources_dir, 'checked.svg').replace('\\', '/')
                stylesheet = stylesheet.replace('url(:/icons/unchecked.svg)', 'url({})'.format(unchecked_path))
                stylesheet = stylesheet.replace('url(:/icons/checked.svg)', 'url({})'.format(checked_path))
                app.setStyleSheet(stylesheet)
                print("Applied stylesheet from: {}".format(stylesheet_path))
        except Exception as e:
            print("Failed to load stylesheet: {}".format(e))
    else:
        print("Stylesheet not found at: {}".format(stylesheet_path))
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
