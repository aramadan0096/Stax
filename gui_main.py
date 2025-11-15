# -*- coding: utf-8 -*-
"""
Main GUI for StaX
PySide2-based user interface with drag-and-drop support
Python 2.7 compatible
"""

import os
import sys
from PySide2 import QtWidgets, QtCore, QtGui

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
        self.nuke_bridge = NukeBridge(mock_mode=self.config.get('nuke_mock_mode'))
        self.nuke_integration = NukeIntegration(self.nuke_bridge, self.db)
        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        
        # User authentication
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
        
        # Show login dialog
        self.show_login()
    
    def setup_ui(self):
        """Setup the main window UI."""
        # Central widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Main splitter for left panel, center content, and right preview pane
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: Stacks/Lists panel
        self.stacks_panel = StacksListsPanel(self.db, self.config)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        self.stacks_panel.favorites_selected.connect(self.on_favorites_selected)
        self.stacks_panel.playlist_selected.connect(self.on_playlist_selected)
        main_splitter.addWidget(self.stacks_panel)
        
        # Center: Media display
        self.media_display = MediaDisplayWidget(self.db, self.config, self.nuke_bridge, main_window=self)
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        main_splitter.addWidget(self.media_display)
        
        # Right: Video player preview pane (hidden by default)
        self.video_player_pane = VideoPlayerWidget(self.db, self.config, self)
        self.video_player_pane.closed.connect(self.on_preview_pane_closed)
        self.video_player_pane.hide()
        main_splitter.addWidget(self.video_player_pane)
        
        # Set splitter sizes (left: 250, center: 900, right: 400)
        main_splitter.setSizes([250, 900, 400])
        
        layout.addWidget(main_splitter)
        
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
    
    def create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        ingest_action = QtWidgets.QAction("Ingest Files...", self)
        ingest_action.setIcon(get_icon('upload', size=16))
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
        
        # Nuke menu
        nuke_menu = menubar.addMenu("Nuke")
        
        register_toolset_action = QtWidgets.QAction("Register Selection as Toolset...", self)
        register_toolset_action.setIcon(get_icon('add', size=16))
        register_toolset_action.setShortcut("Ctrl+Shift+T")
        register_toolset_action.triggered.connect(self.register_toolset)
        register_toolset_action.setToolTip("Save selected Nuke nodes as a reusable toolset")
        nuke_menu.addAction(register_toolset_action)
        
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
    
    def show_login(self):
        """Show login dialog."""
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = self.current_user and self.current_user.get('role') == 'admin'
            
            # Update window title with username
            username = self.current_user['username'] if self.current_user else 'Guest'
            role_text = ' (Admin)' if self.is_admin else ''
            self.setWindowTitle("Stax - {}{}".format(username, role_text))
            
            self.statusBar().showMessage("Logged in as: {}".format(username))
        else:
            # User cancelled login - exit application
            QtWidgets.QApplication.quit()
    
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
    
    def toggle_history(self):
        """Toggle history panel visibility."""
        visible = not self.history_dock.isVisible()
        self.history_dock.setVisible(visible)
        if visible:
            self.history_panel.load_history()
    
    def toggle_settings(self):
        """Toggle settings panel visibility."""
        self.settings_dock.setVisible(not self.settings_dock.isVisible())
    
    def on_list_selected(self, list_id):
        """Handle list selection."""
        self.media_display.load_elements(list_id)
        
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst['stack_fk'])
            if stack:
                self.statusBar().showMessage("Viewing: {} > {}".format(stack['name'], lst['name']))
    
    def on_favorites_selected(self):
        """Handle favorites button click."""
        self.media_display.load_favorites()
        self.statusBar().showMessage("Viewing: Favorites")
    
    def on_playlist_selected(self, playlist_id):
        """Handle playlist selection."""
        self.media_display.load_playlist(playlist_id)
        playlist = self.db.get_playlist_by_id(playlist_id)
        if playlist:
            self.statusBar().showMessage("Viewing Playlist: {}".format(playlist['name']))
    
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
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Load and apply stylesheet
    stylesheet_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
    if os.path.exists(stylesheet_path):
        try:
            with open(stylesheet_path, 'r') as f:
                stylesheet = f.read()
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
