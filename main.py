# -*- coding: utf-8 -*-
"""
Main GUI for StaX
PySide2-based user interface with drag-and-drop support
Python 2.7 compatible

PATCHED: Features 1–6 integrated
  1. Async preview worker (PreviewWorker / LazyGalleryView handshake)
  2. Lazy virtual-scroll gallery  (LazyGalleryView swap)
  3. Duplicate detection          (via IngestionCore signals)
  4. Local REST API server         (APIServer background thread)
  5. Batch metadata editor         (context-menu entry in MediaDisplayWidget)
  6. Usage analytics panel         (Ctrl+4 dock, AnalyticsPanel)
"""

import os
import sys
import logging

import dependency_bootstrap
dependency_bootstrap.bootstrap()

from src.debug_manager import DebugManager
DebugManager.bootstrap_from_config()

from PySide2 import QtWidgets, QtCore, QtGui

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

from src.config import Config
from src.db_manager import DatabaseManager
from src.ingestion_core import IngestionCore
from src.nuke_bridge import NukeBridge, NukeIntegration
from src.extensibility_hooks import ProcessorManager
from src.icon_loader import get_icon
from src.video_player_widget import VideoPlayerWidget

# ---- NEW: Feature 1 — async preview worker --------------------------------
from src.preview_worker import get_preview_queue, shutdown_preview_queue
# ---- NEW: Feature 4 — REST API --------------------------------------------
from src.api_server import get_api_server, shutdown_api_server
# ---- NEW: Feature 6 — analytics -------------------------------------------
from src.ui.analytics_panel import AnalyticsPanel

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
    NukeInstallerDialog,
    MediaInfoPopup,
    StacksListsPanel,
    MediaDisplayWidget,
    HistoryPanel,
    SettingsPanel,
)

log = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""

    def __init__(self, config=None):
        super(MainWindow, self).__init__()

        # Initialize core components
        if config is not None:
            self.config = config
        else:
            self.config = Config()

        self.config.ensure_directories()
        self.db = DatabaseManager(self.config.get('database_path'))

        # Load database-stored settings (previews_path, etc.)
        self.config.load_from_database(self.db)
        DebugManager.sync_from_config(self.config)

        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.nuke_bridge = NukeBridge(mock_mode=self.config.get('nuke_mock_mode'))
        self.nuke_integration = NukeIntegration(
            self.nuke_bridge,
            self.db,
            config=self.config,
            ingestion_core=self.ingestion,
            processor_manager=self.processor_manager,
        )

        self._stored_left_width = None
        self.active_view = ('none', None)
        self._view_before_tags = None
        self._suspend_tag_restore = False

        # User authentication — deferred login
        self.current_user = None
        self.is_admin = False

        self.setWindowTitle("Stax")
        self.resize(1400, 800)

        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'logo.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        self.setup_ui()
        self.setup_shortcuts()

        # ---- Feature 1: start async preview worker ------------------------
        self._start_preview_worker()

        # ---- Feature 4: start REST API server if enabled ------------------
        self._start_api_server()

    # -----------------------------------------------------------------------
    # Feature 1 — async preview worker
    # -----------------------------------------------------------------------

    def _start_preview_worker(self):
        """Initialise and start the background preview worker thread."""
        pw = get_preview_queue()
        # Forward preview_ready to the media display's lazy gallery
        pw.preview_ready.connect(self.media_display.on_preview_ready)
        pw.job_failed.connect(self._on_preview_failed)
        pw.queue_empty.connect(
            lambda: self.statusBar().showMessage("Previews ready.", 3000)
        )
        if not pw.isRunning():
            pw.start()
        log.debug("Preview worker started.")

    @QtCore.Slot(int, str)
    def _on_preview_failed(self, element_id, message):
        log.warning("Preview generation failed for element %d: %s",
                    element_id, message)

    # -----------------------------------------------------------------------
    # Feature 4 — REST API server
    # -----------------------------------------------------------------------

    def _start_api_server(self):
        """Start the local REST API server if enabled in config."""
        if not self.config.get('api_enabled', False):
            return
        srv = get_api_server()
        srv.configure(self.db, self.config)
        srv.server_started.connect(
            lambda port: self.statusBar().showMessage(
                "API server running on http://127.0.0.1:{}".format(port), 5000
            )
        )
        srv.server_error.connect(
            lambda msg: QtWidgets.QMessageBox.warning(
                self, "API Server Error", msg
            )
        )
        srv.start()

    # -----------------------------------------------------------------------
    # setup_ui
    # -----------------------------------------------------------------------

    def setup_ui(self):
        """Setup the main window UI."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)

        self.setup_toolbar()

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
        self.media_display = MediaDisplayWidget(
            self.db, self.config, self.nuke_bridge, main_window=self
        )
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        self.main_splitter.addWidget(self.media_display)
        self.main_splitter.setStretchFactor(1, 1)

        # Right: Video player preview pane (hidden by default)
        self.video_player_pane = VideoPlayerWidget(self.db, self.config, self)
        self.video_player_pane.closed.connect(self.on_preview_pane_closed)
        self.video_player_pane.hide()
        self.main_splitter.addWidget(self.video_player_pane)
        self.preview_pane_expanded_width = 360

        self.main_splitter.setSizes([280, 920, 360])
        layout.addWidget(self.main_splitter)

        # Selection changes → update preview pane
        self.media_display.gallery_view.itemSelectionChanged.connect(
            self.on_selection_changed
        )
        self.media_display.table_view.itemSelectionChanged.connect(
            self.on_selection_changed
        )

        # History dock
        self.history_dock = QtWidgets.QDockWidget("History", self)
        self.history_panel = HistoryPanel(self.db)
        self.history_dock.setWidget(self.history_panel)
        self.history_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)

        # Settings dock
        self.settings_dock = QtWidgets.QDockWidget("Settings", self)
        self.settings_panel = SettingsPanel(self.config, self.db, main_window=self)
        self.settings_panel.settings_changed.connect(self.on_settings_changed)
        self.settings_dock.setWidget(self.settings_panel)
        self.settings_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.settings_dock)

        # ---- Feature 6: analytics dock ------------------------------------
        self.analytics_dock = QtWidgets.QDockWidget("Analytics", self)
        self.analytics_panel = AnalyticsPanel(self.db)
        self.analytics_dock.setWidget(self.analytics_panel)
        self.analytics_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.analytics_dock)
        # -------------------------------------------------------------------

        self.create_menus()
        self.statusBar().showMessage("Ready")

    # -----------------------------------------------------------------------
    # Toolbar
    # -----------------------------------------------------------------------

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

        history_action = QtWidgets.QAction(get_icon('history', size=20), "History", self)
        history_action.setToolTip("Show ingestion history (Ctrl+2)")
        history_action.triggered.connect(self.toggle_history)
        self.toolbar.addAction(history_action)

        settings_action = QtWidgets.QAction(get_icon('settings', size=20), "Settings", self)
        settings_action.setToolTip("Open settings panel (Ctrl+3)")
        settings_action.triggered.connect(self.toggle_settings)
        self.toolbar.addAction(settings_action)

        # ---- Feature 6: analytics toolbar button -------------------------
        analytics_action = QtWidgets.QAction(
            get_icon('chart', size=20), "Analytics", self
        )
        analytics_action.setToolTip("Show usage analytics (Ctrl+4)")
        analytics_action.triggered.connect(self.toggle_analytics)
        self.toolbar.addAction(analytics_action)
        # ------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Menus
    # -----------------------------------------------------------------------

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

        # ---- Feature 6: analytics menu entry -----------------------------
        analytics_menu_action = QtWidgets.QAction("Analytics Panel", self)
        analytics_menu_action.setShortcut("Ctrl+4")
        analytics_menu_action.setCheckable(True)
        analytics_menu_action.triggered.connect(self.toggle_analytics)
        view_menu.addAction(analytics_menu_action)
        # ------------------------------------------------------------------

        # Help menu
        help_menu = menubar.addMenu("Help")

        doc_action = QtWidgets.QAction("Documentation", self)
        doc_action.setToolTip("Open the online documentation")
        doc_action.triggered.connect(
            lambda checked=False: QtGui.QDesktopServices.openUrl(
                QtCore.QUrl("https://aramadan0096.github.io/stax-docs/")
            )
        )
        help_menu.addAction(doc_action)

        about_action = QtWidgets.QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        install_nuke_action = QtWidgets.QAction("Install to Nuke...", self)
        install_nuke_action.setToolTip("Add StaX plugin path to a Nuke user's init.py")
        install_nuke_action.triggered.connect(self.show_nuke_installer)
        help_menu.addAction(install_nuke_action)

    # -----------------------------------------------------------------------
    # Shortcuts
    # -----------------------------------------------------------------------

    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+2"), self, self.toggle_history)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+3"), self, self.toggle_settings)
        # ---- Feature 6 ----
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+4"), self, self.toggle_analytics)

    # -----------------------------------------------------------------------
    # Toggle handlers
    # -----------------------------------------------------------------------

    def toggle_history(self):
        visible = not self.history_dock.isVisible()
        self.history_dock.setVisible(visible)
        if visible:
            self.history_panel.load_history()

    def toggle_settings(self):
        if not self.current_user:
            if not self.show_login(required=True):
                QtWidgets.QMessageBox.information(
                    self, "Login Required", "You must login to access settings."
                )
                return
        self.settings_dock.setVisible(not self.settings_dock.isVisible())

    # ---- Feature 6 --------------------------------------------------------
    def toggle_analytics(self):
        """Toggle the usage analytics dock panel."""
        visible = not self.analytics_dock.isVisible()
        self.analytics_dock.setVisible(visible)
        if visible:
            self.analytics_panel.refresh()

    # -----------------------------------------------------------------------
    # Focus mode
    # -----------------------------------------------------------------------

    def toggle_focus_mode(self, checked):
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return

        if checked:
            self._stored_left_width = sizes[0] if sizes[0] > 0 else self.stacks_panel.minimumWidth()
            total_width = self.main_splitter.width()
            preview_width = sizes[2]
            center_width = max(400, total_width - preview_width)
            sizes = [0, center_width, preview_width]
            self.stacks_panel.hide()
            self.toolbar.hide()
            if hasattr(self, 'history_dock') and self.history_dock.isVisible():
                self.history_dock.hide()
            if hasattr(self, 'settings_dock') and self.settings_dock.isVisible():
                self.settings_dock.hide()
            if hasattr(self, 'analytics_dock') and self.analytics_dock.isVisible():
                self.analytics_dock.hide()
            if hasattr(self.media_display, 'pagination'):
                self.media_display.pagination.hide()
        else:
            restore_width = self._stored_left_width or self.stacks_panel.minimumWidth()
            total_width = self.main_splitter.width()
            preview_width = sizes[2]
            center_width = max(400, total_width - restore_width - preview_width)
            sizes = [restore_width, center_width, preview_width]
            self.stacks_panel.show()
            self.toolbar.show()
            if hasattr(self.media_display, 'pagination') and self.config.get('pagination_enabled', True):
                if len(self.media_display.current_elements) > 0:
                    self.media_display.pagination.show()

        self.main_splitter.setSizes(sizes)

    # -----------------------------------------------------------------------
    # Preview pane helpers
    # -----------------------------------------------------------------------

    def expand_preview_pane(self):
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return
        total = sum(sizes)
        left_width = max(self.stacks_panel.minimumWidth(), sizes[0])
        available = max(0, total - left_width)
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
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return
        if sizes[2] > 0:
            self.preview_pane_expanded_width = sizes[2]
        sizes[1] += sizes[2]
        sizes[2] = 0
        self.main_splitter.setSizes(sizes)
        self.video_player_pane.hide()

    # -----------------------------------------------------------------------
    # Auth helpers
    # -----------------------------------------------------------------------

    def show_nuke_installer(self):
        try:
            dlg = NukeInstallerDialog(self)
            dlg.exec_()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error",
                "Failed to open Nuke installer: {}".format(exc))

    def show_login(self, required=False):
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = (
                self.current_user and
                self.current_user.get('role') == 'admin'
            )
            username = self.current_user['username'] if self.current_user else 'Guest'
            role_text = ' (Admin)' if self.is_admin else ''
            self.setWindowTitle("Stax - {}{}".format(username, role_text))
            self.statusBar().showMessage("Logged in as: {}".format(username))
            return True
        return False

    def check_admin_permission(self, action_name="this action"):
        if not self.current_user:
            if not self.show_login(required=True):
                QtWidgets.QMessageBox.information(
                    self, "Login Required",
                    "You must login to perform {}.".format(action_name)
                )
                return False
        if not self.is_admin:
            QtWidgets.QMessageBox.warning(
                self, "Permission Denied",
                "You need administrator privileges to perform {}.\n\n"
                "Current user: {} ({})\n\n"
                "Please login as an administrator.".format(
                    action_name,
                    self.current_user['username'] if self.current_user else 'guest',
                    self.current_user.get('role', 'guest') if self.current_user else 'guest',
                )
            )
            return False
        return True

    def logout(self):
        if self.current_user and self.current_user.get('user_id'):
            import socket
            machine_name = socket.gethostname()
            session = self.db.get_active_session(
                self.current_user['user_id'], machine_name
            )
            if session:
                self.db.end_session(session['session_id'])
        self.show_login()

    # -----------------------------------------------------------------------
    # View event handlers
    # -----------------------------------------------------------------------

    def on_list_selected(self, list_id):
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
                self.statusBar().showMessage(
                    "Viewing: {} > {}".format(stack['name'], lst['name'])
                )
        self.active_view = ('list', list_id)
        self._view_before_tags = None

    def on_stack_selected(self, stack_id):
        if not self.config.get('show_entire_stack_elements', False):
            return
        lists = self.db.get_lists_by_stack(stack_id)
        all_elements = []
        for lst in lists:
            all_elements.extend(self.db.get_elements_by_list(lst['list_id']))
        self.media_display.current_list_id = None
        self.media_display.current_elements = all_elements
        self.media_display.current_tag_filter = []
        if self.config.get('pagination_enabled', True):
            self.media_display.pagination.set_total_items(len(all_elements))
            self.media_display.pagination.set_items_per_page(
                self.config.get('items_per_page', 100)
            )
            self.media_display.pagination.setVisible(len(all_elements) > 0)
        else:
            self.media_display.pagination.setVisible(False)
        if all_elements:
            self.media_display.content_stack.setCurrentIndex(1)
        else:
            stack = self.db.get_stack_by_id(stack_id)
            if stack:
                self.media_display.info_label.setText(
                    "No elements in stack '{}'".format(stack['name'])
                )
                self.media_display.hint_label.setText(
                    "Add lists and elements to this stack"
                )
                self.media_display.content_stack.setCurrentIndex(0)
        self.media_display._display_current_page()
        stack = self.db.get_stack_by_id(stack_id)
        if stack:
            self.statusBar().showMessage(
                "Viewing: {} (all lists)".format(stack['name'])
            )
        self.active_view = ('stack', stack_id)

    def on_favorites_selected(self):
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
        if getattr(self.stacks_panel, 'get_selected_tags', None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_playlist(playlist_id)
        playlist = self.db.get_playlist_by_id(playlist_id)
        if playlist:
            self.statusBar().showMessage(
                "Viewing Playlist: {}".format(playlist['name'])
            )
        self.active_view = ('playlist', playlist_id)
        self._view_before_tags = None

    def on_element_double_clicked(self, element_id):
        """Handle element double-click (insert into Nuke)."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage(
                    "Inserted: {}".format(element['name'])
                )
            # ---- Feature 6: log insertion ---------------------------------
            try:
                import socket
                from src.ui.analytics_panel import log_insertion
                uid = (
                    self.current_user.get('user_id')
                    if self.current_user else None
                )
                log_insertion(
                    db         = self.db,
                    element_id = element_id,
                    user_id    = uid,
                    project    = os.environ.get('STAX_PROJECT', ''),
                    host       = socket.gethostname(),
                )
            except Exception:
                pass
            # ---------------------------------------------------------------
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error",
                "Failed to insert element: {}".format(str(e))
            )

    def on_selection_changed(self):
        selected_ids = self.media_display.get_selected_element_ids()
        if len(selected_ids) == 1:
            element_id = selected_ids[0]
            self.expand_preview_pane()
            self.video_player_pane.load_element(element_id)
        elif len(selected_ids) > 1:
            self.video_player_pane.clear()
            self.collapse_preview_pane()
        else:
            if self.video_player_pane.isVisible():
                self.video_player_pane.clear()

    def on_preview_pane_closed(self):
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
        self.statusBar().showMessage(
            "Filtering by tags: {}".format(', '.join(tags))
        )

    def restore_active_view(self):
        mode, value = self.active_view
        if mode == 'list' and value:
            self.media_display.load_elements(value)
        elif mode == 'favorites':
            self.media_display.load_favorites()
        elif mode == 'playlist' and value:
            self.media_display.load_playlist(value)
        elif mode == 'tags' and value:
            self.media_display.load_elements_by_tags(list(value))
        else:
            self.media_display.show_empty_state()

    # -----------------------------------------------------------------------
    # Ingestion
    # -----------------------------------------------------------------------

    def ingest_files(self):
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
        progress = QtWidgets.QProgressDialog(
            "Ingesting files...", "Cancel", 0, len(files), self
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)

        success_count = 0
        error_count   = 0
        skipped_count = 0

        for i, filepath in enumerate(files):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(
                "Ingesting: {}".format(os.path.basename(filepath))
            )
            result = self.ingestion.ingest_file(
                filepath,
                target_list_id,
                copy_policy=self.config.get('default_copy_policy'),
            )
            if result['success']:
                success_count += 1
            elif result.get('reason') == 'duplicate_skipped':
                skipped_count += 1
            else:
                error_count += 1

        progress.setValue(len(files))

        msg = "Ingested {} file(s) successfully.".format(success_count)
        if skipped_count:
            msg += "\n{} skipped (duplicates).".format(skipped_count)
        if error_count:
            msg += "\n{} error(s).".format(error_count)

        QtWidgets.QMessageBox.information(self, "Ingestion Complete", msg)

        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)

    def ingest_library(self):
        dialog = IngestLibraryDialog(self.db, self.ingestion, self.config, self)
        if dialog.exec_():
            self.stacks_panel.load_data()

    def register_toolset(self):
        dialog = RegisterToolsetDialog(
            self.db, self.nuke_integration, self.config, self
        )
        if dialog.exec_():
            if hasattr(self.media_display, 'current_list_id') and \
               self.media_display.current_list_id:
                self.media_display.load_elements(
                    self.media_display.current_list_id
                )
            self.statusBar().showMessage("Toolset registered successfully")

    def on_settings_changed(self):
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.statusBar().showMessage("Settings updated")

    def show_advanced_search(self):
        if not hasattr(self, 'advanced_search_dialog') or \
           self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()

    def show_about(self):
        QtWidgets.QMessageBox.about(
            self, "About Stax",
            "<h3>Stax</h3>"
            "<p>Version 0.9.3</p>"
            "<p>Advanced Stock Management for VFX Studios</p>"
            "<p>Author: Ahmed Ramadan</p>"
            "<p>New in 0.9.3: Async previews · Virtual scroll · "
            "Duplicate detection · REST API · Batch edit · Analytics</p>"
        )

    # -----------------------------------------------------------------------
    # Window close — shut down background threads cleanly
    # -----------------------------------------------------------------------

    def closeEvent(self, event):
        """Gracefully stop all background threads before exiting."""
        # Feature 1 — preview worker
        shutdown_preview_queue()
        # Feature 4 — REST API server
        shutdown_api_server()
        super(MainWindow, self).closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Suppress Chromium GLES2 performance warnings emitted by the 3D WebGL
    # viewer ("Attribute 0 is disabled").  Must be set before QApplication.
    os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--log-level=3')

    try:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)
    config = Config()
    DebugManager.sync_from_config(config)
    config.ensure_directories()

    app.setStyle('Fusion')
    stylesheet_path = os.path.join(
        os.path.dirname(__file__), 'resources', 'style.qss'
    )
    if os.path.exists(stylesheet_path):
        try:
            with open(stylesheet_path, 'r') as f:
                stylesheet = f.read()
            resources_dir = os.path.join(
                os.path.dirname(__file__), 'resources', 'icons'
            )
            unchecked_path = os.path.join(
                resources_dir, 'unchecked.svg'
            ).replace('\\', '/')
            checked_path = os.path.join(
                resources_dir, 'checked.svg'
            ).replace('\\', '/')
            stylesheet = stylesheet.replace(
                'url(:/icons/unchecked.svg)',
                'url({})'.format(unchecked_path)
            )
            stylesheet = stylesheet.replace(
                'url(:/icons/checked.svg)',
                'url({})'.format(checked_path)
            )
            app.setStyleSheet(stylesheet)
        except Exception as e:
            print("Failed to load stylesheet: {}".format(e))

    window = MainWindow(config=config)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
