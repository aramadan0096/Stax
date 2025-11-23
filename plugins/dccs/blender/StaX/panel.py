# -*- coding: utf-8 -*-
"""
StaX Blender Panel
Blender-specific panel launcher for StaX asset management system
Python 3 compatible
"""

import os
import sys

# Define stax_root globally for this module
stax_root = None

# Ensure project root is in sys.path
# Note: sys.path should be set up by __init__.py before importing this module
# But we keep a fallback check just in case
try:
    import dependency_bootstrap
    # If successful, we need to find stax_root. 
    # dependency_bootstrap doesn't export it, but we can deduce it or use Config later.
    # For now, let's try to deduce it from the module file if possible, or assume CWD if running from source.
    if hasattr(dependency_bootstrap, '__file__'):
        stax_root = os.path.dirname(dependency_bootstrap.__file__)
except ImportError:
    # Try to find root relative to this file (dev mode)
    current_dir = os.path.dirname(__file__)
    # Assuming structure: plugins/dccs/blender/StaX/panel.py -> root is 4 levels up
    potential_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))
    
    if os.path.exists(os.path.join(potential_root, 'dependency_bootstrap.py')):
        stax_root = potential_root
        if stax_root not in sys.path:
            sys.path.insert(0, stax_root)
    
    try:
        import dependency_bootstrap
    except ImportError:
        print("Error: Could not find dependency_bootstrap. Please ensure StaX root is in sys.path.")
        # We don't raise here to allow module to load, but it will likely fail later
        pass

if 'dependency_bootstrap' in sys.modules:
    import dependency_bootstrap
    dependency_bootstrap.bootstrap()

# Fallback if stax_root is still None (e.g. imported but __file__ not available)
if stax_root is None:
    # Try to find it via Config if possible, or default to current working dir
    # But we can't import Config yet if sys.path isn't set.
    # Let's assume the user set it up correctly if we got this far.
    pass

from src.debug_manager import DebugManager
DebugManager.bootstrap_from_config()

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    print("Error: PySide2 not found. Please install PySide2 in Blender's Python environment.")
    raise

from src.config import Config
from src.db_manager import DatabaseManager
from src.ingestion_core import IngestionCore
from src.extensibility_hooks import ProcessorManager
from src.icon_loader import get_icon
from src.ui import (
    AdvancedSearchDialog,
    StacksListsPanel,
    MediaDisplayWidget,
    HistoryPanel,
    SettingsPanel,
    LoginDialog
)

from .bridge import BlenderBridge
from .ingest_dialog import RegisterMeshDialog

# Global reference to keep window alive
_stax_window = None

class StaXBlenderPanel(QtWidgets.QWidget):
    """
    StaX panel widget for Blender.
    """
    
    def __init__(self, parent=None):
        super(StaXBlenderPanel, self).__init__(parent)
        
        self.config = Config()
        self.config.ensure_directories()
        
        self.db = DatabaseManager(self.config.get('database_path'))
        self.config.load_from_database(self.db)
        DebugManager.sync_from_config(self.config)
        
        self.bridge = BlenderBridge()
        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        
        # User authentication
        self.current_user = None
        self.is_admin = False
        
        self.setWindowTitle("StaX")
        self.resize(1200, 700)
        
        # Set window flags to keep it on top of Blender if desired, 
        # or just standard window. Standard is usually better for UX.
        # self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        
        self.setup_ui()
        
        # Auto-login as guest or show login
        # For now, let's just auto-login as guest to match Nuke behavior
        self.current_user = {'username': 'guest', 'role': 'guest'}
        self.is_admin = False
        self.user_label.setText("User: Guest (Read-only)")

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)
        
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        self.stacks_panel = StacksListsPanel(self.db, self.config, main_window=self)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        self.stacks_panel.stack_selected.connect(self.on_stack_selected)
        self.stacks_panel.favorites_selected.connect(self.on_favorites_selected)
        self.stacks_panel.playlist_selected.connect(self.on_playlist_selected)
        self.stacks_panel.tags_filter_changed.connect(self.on_tags_filter_changed)
        self.main_splitter.addWidget(self.stacks_panel)
        
        # Pass BlenderBridge as nuke_bridge (interface compatible)
        self.media_display = MediaDisplayWidget(self.db, self.config, self.bridge, main_window=self)
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        self.main_splitter.addWidget(self.media_display)
        
        self.main_splitter.setSizes([260, 900])
        main_layout.addWidget(self.main_splitter)
        
        self.status_label = QtWidgets.QLabel("Ready")
        main_layout.addWidget(self.status_label)

    def create_toolbar(self):
        toolbar = QtWidgets.QToolBar("Main Toolbar")
        toolbar.setIconSize(QtCore.QSize(20, 20))
        
        ingest_action = QtWidgets.QAction(get_icon('import', size=20), "Ingest Files", self)
        ingest_action.triggered.connect(self.ingest_files)
        toolbar.addAction(ingest_action)
        
        toolbar.addSeparator()
        
        search_action = QtWidgets.QAction(get_icon('search', size=20), "Search", self)
        search_action.triggered.connect(self.show_advanced_search)
        toolbar.addAction(search_action)
        
        favorites_action = QtWidgets.QAction(get_icon('favorite', size=20), "Favorites", self)
        favorites_action.triggered.connect(self.on_favorites_selected)
        toolbar.addAction(favorites_action)
        
        toolbar.addSeparator()
        
        # Add to Library (Mesh)
        add_lib_action = QtWidgets.QAction(get_icon('add', size=20), "Add to Library", self)
        add_lib_action.setToolTip("Export selected objects to library")
        add_lib_action.triggered.connect(self.add_to_library)
        toolbar.addAction(add_lib_action)
        
        toolbar.addSeparator()
        
        self.user_label = QtWidgets.QLabel("Not logged in")
        toolbar.addWidget(self.user_label)
        
        return toolbar

    def on_list_selected(self, list_id):
        self.media_display.load_elements(list_id)
        lst = self.db.get_list_by_id(list_id)
        if lst:
            self.status_label.setText(f"Viewing: {lst['name']}")

    def on_stack_selected(self, stack_id):
        # Logic to show all elements in stack
        lists = self.db.get_lists_by_stack(stack_id)
        all_elements = []
        for lst in lists:
            all_elements.extend(self.db.get_elements_by_list(lst['list_id']))
        self.media_display.current_list_id = None
        self.media_display.current_elements = all_elements
        self.media_display._update_views_with_elements(all_elements)
        self.status_label.setText("Viewing Stack")

    def on_favorites_selected(self):
        self.media_display.load_favorites()
        self.status_label.setText("Viewing Favorites")

    def on_playlist_selected(self, playlist_id):
        self.media_display.load_playlist(playlist_id)
        self.status_label.setText("Viewing Playlist")

    def on_tags_filter_changed(self, tags):
        if tags:
            self.media_display.load_elements_by_tags(tags)
        else:
            self.media_display.show_empty_state()

    def on_element_double_clicked(self, element_id):
        # Import logic
        element = self.db.get_element_by_id(element_id)
        if not element:
            return
        
        filepath = element.get('filepath_hard') or element.get('filepath_soft')
        if not filepath:
            return
            
        # Resolve path
        if not os.path.isabs(filepath):
            filepath = os.path.join(self.config.root_dir, filepath)
            
        if self.bridge.import_object(filepath):
            self.status_label.setText(f"Imported: {element['name']}")
        else:
            self.status_label.setText(f"Failed to import: {element['name']}")

    def ingest_files(self):
        # Reuse existing ingest logic
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Files")
        if files:
            # Show list selector... (simplified for now)
            pass

    def show_advanced_search(self):
        if not hasattr(self, 'advanced_search_dialog') or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()

    def add_to_library(self):
        """Show dialog to add selected objects to library."""
        dialog = RegisterMeshDialog(self.db, self.bridge, self.config, self)
        if dialog.exec_():
            # Refresh view if needed
            if self.media_display.current_list_id:
                self.media_display.load_elements(self.media_display.current_list_id)

    # ... (Other methods like check_admin_permission, logout, etc. can be added as needed)

def show_stax_panel():
    """Show the StaX panel."""
    global _stax_window
    
    app = QtWidgets.QApplication.instance()
    if not app:
        # This shouldn't happen in Blender usually, but just in case
        app = QtWidgets.QApplication(sys.argv)
    
    if _stax_window is None:
        _stax_window = StaXBlenderPanel()
        
        # Determine root path for resources
        root_path = stax_root
        if not root_path and hasattr(_stax_window, 'config'):
            root_path = _stax_window.config.root_dir
            
        if root_path:
            # Apply stylesheet
            stylesheet_path = os.path.join(root_path, 'resources', 'style.qss')
            if os.path.exists(stylesheet_path):
                with open(stylesheet_path, 'r') as f:
                    stylesheet = f.read()
                    # Fix icon paths
                    resources_dir = os.path.join(root_path, 'resources', 'icons').replace('\\', '/')
                    stylesheet = stylesheet.replace('url(:/icons/', f'url({resources_dir}/')
                    _stax_window.setStyleSheet(stylesheet)
    
    _stax_window.show()
    _stax_window.raise_()
    _stax_window.activateWindow()
    return _stax_window

def add_to_library():
    """Directly open the Add to Library dialog."""
    # We need the panel instance to parent the dialog, or at least the app
    panel = show_stax_panel()
    panel.add_to_library()
