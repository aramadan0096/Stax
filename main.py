# -*- coding: utf-8 -*-
"""
Main GUI for StaX — Python 3.9+

Changes from original:
  - apply_dark_palette(app) before setStyleSheet  THE real fix for white bg
  - _force_panel_palette() propagates dark bg to LEFT nav + RIGHT preview
  - setObjectName on all three main panels for reliable QSS targeting
  - Async preview worker wired (Feature 1)
  - Analytics dock, Ctrl+4 shortcut (Feature 6)
  - REST API server (Feature 4)
  - closeEvent shuts down background threads
  - Insertion logging on double-click (Feature 6)
  - Duplicate-skip shown in ingestion summary (Feature 3)
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
from src.ingest_worker import IngestWorker
from src.nuke_bridge import NukeBridge, NukeIntegration
from src.extensibility_hooks import ProcessorManager
from src.icon_loader import get_icon
from src.dark_palette import apply_dark_palette
from src.ui.accessibility import apply_accessibility
from src.video_player_widget import VideoPlayerWidget
from src.ui.inspector_panel import InspectorPanel
from src.ui.layout_manager import apply_preset, preset_names
from src.ui.onboarding_checklist import OnboardingChecklist
from src.ui.start_page import StartPage
from src.watch_scanner import WatchFolderScanner
from src.ingest_automation import apply_recipe_to_config

try:
    from src.preview_worker import get_preview_queue, shutdown_preview_queue
    _PREVIEW_WORKER_AVAILABLE = True
except ImportError:
    _PREVIEW_WORKER_AVAILABLE = False

try:
    from src.api_server import get_api_server, shutdown_api_server
    _API_SERVER_AVAILABLE = True
except ImportError:
    _API_SERVER_AVAILABLE = False

try:
    from src.ui.analytics_panel import AnalyticsPanel, log_insertion
    _ANALYTICS_AVAILABLE = True
except ImportError:
    _ANALYTICS_AVAILABLE = False

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
    HealthPanel,
    SettingsPanel,
)
from src.ui.job_queue_dashboard import JobQueueDashboard

log = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, config=None):
        super(MainWindow, self).__init__()

        if config is not None:
            self.config = config
        else:
            self.config = Config()

        self.config.ensure_directories()
        self.db = DatabaseManager(self.config.get("database_path"))
        self.config.load_from_database(self.db)
        DebugManager.sync_from_config(self.config)

        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.nuke_bridge = NukeBridge(mock_mode=self.config.get("nuke_mock_mode"))
        self.nuke_integration = NukeIntegration(
            self.nuke_bridge, self.db,
            config=self.config,
            ingestion_core=self.ingestion,
            processor_manager=self.processor_manager,
        )

        self._stored_left_width = None
        self.active_view = ("none", None)
        self._current_list_id = None
        self._view_before_tags = None
        self._suspend_tag_restore = False
        self.current_user = None
        self.is_admin = False
        # EP6: retry workers are kept separate from self._ingest_worker (the
        # batch-ingest worker slot) so a retry can't clobber a still-running
        # batch worker's reference, or vice-versa. See _retry_job/_cancel_job.
        self._retry_workers = []
        # EP6: same premature-GC hazard as _retry_workers -- WatchFolderScanner
        # can emit files_detected for multiple enabled folders back-to-back in
        # one pass, so a single self._watch_ingest_worker slot would be
        # overwritten by the second call while the first worker's QThread is
        # still running. See _forget_watch_worker.
        self._watch_ingest_workers = []

        self.setWindowTitle("Stax")
        self.resize(1400, 800)

        icon_path = os.path.join(os.path.dirname(__file__), "resources", "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        self.setup_ui()
        self.setup_shortcuts()
        self._start_preview_worker()
        self._start_api_server()

        apply_preset(self, self.config.get("layout_preset", "Browse"))

        self.onboarding_checklist = None
        if not self.config.get("onboarding_dismissed", False):
            self.open_onboarding_checklist()

        self._watch_scanner = None
        self._start_watch_scanner()

    # -------------------------------------------------------------------------
    # Background services
    # -------------------------------------------------------------------------

    def _start_preview_worker(self):
        if not _PREVIEW_WORKER_AVAILABLE:
            return
        pw = get_preview_queue()
        pw.preview_ready.connect(self.media_display.on_preview_ready)
        pw.job_failed.connect(self._on_preview_failed)
        pw.queue_empty.connect(
            lambda: self.statusBar().showMessage("Previews ready.", 3000)
        )
        if not pw.isRunning():
            pw.start()

    @QtCore.Slot(int, str)
    def _on_preview_failed(self, element_id, message):
        log.warning("Preview failed for element %d: %s", element_id, message)

    def _start_api_server(self):
        if not _API_SERVER_AVAILABLE:
            return
        if not self.config.get("api_enabled", False):
            return
        srv = get_api_server()
        srv.configure(self.db, self.config)
        srv.server_started.connect(
            lambda port: self.statusBar().showMessage(
                "API server running on http://127.0.0.1:{}".format(port), 5000
            )
        )
        srv.server_error.connect(
            lambda msg: QtWidgets.QMessageBox.warning(self, "API Server Error", msg)
        )
        srv.start()

    # -------------------------------------------------------------------------
    # Panel palette helper
    # -------------------------------------------------------------------------

    @staticmethod
    def _force_panel_palette(widget, bg_hex):
        """
        Push a dark QPalette onto *widget* and all its existing children so
        they paint *bg_hex* instead of the app-wide base.

        This is the palette-level equivalent of the QSS panel rule and works
        even when QSS background-color is ignored by the platform style engine.
        It must be called AFTER the widget has been fully constructed so that
        all child widgets already exist.
        """
        bg   = QtGui.QColor(bg_hex)
        text = QtGui.QColor("#acabaa")
        alt  = QtGui.QColor("#1f2020")
        btn  = QtGui.QColor("#262626")
        full = QtGui.QColor("#e7e5e4")

        def _apply(w):
            pal = w.palette()
            pal.setColor(QtGui.QPalette.Window,        bg)
            pal.setColor(QtGui.QPalette.WindowText,    text)
            pal.setColor(QtGui.QPalette.Base,          bg)
            pal.setColor(QtGui.QPalette.AlternateBase, alt)
            pal.setColor(QtGui.QPalette.Button,        btn)
            pal.setColor(QtGui.QPalette.ButtonText,    full)
            pal.setColor(QtGui.QPalette.Text,          full)
            w.setPalette(pal)
            w.setAutoFillBackground(True)

        _apply(widget)
        for child in widget.findChildren(QtWidgets.QWidget):
            _apply(child)

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)

        self.setup_toolbar()

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)

        # LEFT
        self.stacks_panel = StacksListsPanel(self.db, self.config, main_window=self)
        self.stacks_panel.setObjectName("stacks_panel")
        self.stacks_panel.setMinimumWidth(260)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        self.stacks_panel.stack_selected.connect(self.on_stack_selected)
        self.stacks_panel.favorites_selected.connect(self.on_favorites_selected)
        self.stacks_panel.playlist_selected.connect(self.on_playlist_selected)
        self.stacks_panel.tags_filter_changed.connect(self.on_tags_filter_changed)
        self._force_panel_palette(self.stacks_panel, "#191a1a")
        self.main_splitter.addWidget(self.stacks_panel)

        # CENTER
        self.media_display = MediaDisplayWidget(
            self.db, self.config, self.nuke_bridge, main_window=self
        )
        self.media_display.setObjectName("media_display")
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)

        # EP3 Task 11: minimal personalized start page (Recent / Favorites /
        # Most-used), installed as the widget shown on the nested empty-page
        # stack (media_display._empty_page_stack, index 0 of content_stack)
        # via the same _set_empty_page_widget seam EP1's context-aware empty
        # states use. Installed here, once, at startup, with persistent=True
        # (Final review Finding 1) so it is never deleteLater()'d when an
        # EP1 empty state (list/search/favorites/library) evicts it as the
        # visible page -- MediaDisplayWidget.show_empty_state()'s no-args
        # "nothing selected at all" path re-installs and refresh()es this
        # same live instance, so it comes back once the user clears their
        # selection instead of staying gone after the first empty state.
        # EP1's own empty-state paths are otherwise untouched: they still
        # install their own widget via _show_empty_state/_set_empty_page_widget.
        #
        # Favorites/Most-used are keyed off the same user_name/machine_name
        # Config values every other favorites write/read in the app uses
        # (see MediaDisplayWidget.bulk_add_to_favorites) -- NOT
        # self.current_user, which favorites rows are never written against.
        self.start_page = StartPage(
            self.db,
            self.config.get('user_name'),
            self.config.get('machine_name'),
            parent=self.media_display,
        )
        self.start_page.element_activated.connect(self.on_start_page_element_activated)
        self.media_display._set_empty_page_widget(self.start_page, persistent=True)

        # EP2 Task 9: Saved Searches / Smart Collections nav <-> media display.
        self.stacks_panel.filter_selected.connect(self.media_display.apply_filter)
        self.media_display.saved_search_created.connect(self.stacks_panel.refresh_saved_searches)
        self.main_splitter.addWidget(self.media_display)
        self.main_splitter.setStretchFactor(1, 1)

        # RIGHT (EP3 Task 6: preview + persistent editable inspector, stacked
        # in their own vertical splitter so main_splitter keeps exactly 3
        # direct children -- every main_splitter.sizes()/setSizes() index
        # elsewhere (toggle_focus_mode, expand/collapse_preview_pane) still
        # addresses [left, center, right] unchanged.)
        self.video_player_pane = VideoPlayerWidget(self.db, self.config, self)
        self.video_player_pane.setObjectName("video_player_pane")
        self.video_player_pane.closed.connect(self.on_preview_pane_closed)
        self.video_player_pane.hide()
        self._force_panel_palette(self.video_player_pane, "#191a1a")

        self.inspector = InspectorPanel(self.db)
        self.inspector.setObjectName("inspector_panel")
        self._force_panel_palette(self.inspector, "#191a1a")
        # Rating/label edits repaint that one gallery/table row's badge in
        # place, reusing the grid's own quick-edit refresh hook (design SS3.4).
        self.inspector.element_updated.connect(self.media_display.refresh_item_badge)
        # EP4 final review I3: double-click on a Related row was a dead
        # click -- route it through the same select/reveal path StartPage
        # card activation uses.
        self.inspector.related_activated.connect(self.on_start_page_element_activated)

        self.right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.addWidget(self.video_player_pane)
        self.right_splitter.addWidget(self.inspector)
        self.right_splitter.setSizes([500, 260])
        self.main_splitter.addWidget(self.right_splitter)
        self.preview_pane_expanded_width = 360

        self.main_splitter.setSizes([280, 920, 360])
        layout.addWidget(self.main_splitter)

        self.media_display.gallery_view.itemSelectionChanged.connect(self.on_selection_changed)
        self.media_display.table_view.itemSelectionChanged.connect(self.on_selection_changed)

        # History dock
        self.history_dock = QtWidgets.QDockWidget("History", self)
        self.history_panel = HistoryPanel(self.db)
        self._force_panel_palette(self.history_panel, "#191a1a")
        self.history_dock.setWidget(self.history_panel)
        self.history_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)

        # Job Queue dock (EP6: ingest_jobs ledger + IngestWorker retry/cancel)
        self.job_dashboard = JobQueueDashboard(self.db)
        self._force_panel_palette(self.job_dashboard, "#191a1a")
        self.job_queue_dock = QtWidgets.QDockWidget("Job Queue", self)
        self.job_queue_dock.setWidget(self.job_dashboard)
        self.job_queue_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.job_queue_dock)
        self.job_dashboard.retry_requested.connect(self._retry_job)
        self.job_dashboard.cancel_requested.connect(self._cancel_job)

        # Health dock (EP4 Task 12: metadata quality issues for the
        # currently-selected list)
        self.health_dock = QtWidgets.QDockWidget("Health", self)
        self.health_panel = HealthPanel(self.db)
        self._force_panel_palette(self.health_panel, "#191a1a")
        # Reuse the same "select an element by id" path the EP3 start-page
        # cards use: look up the element, navigate to its list, then select
        # it in the active gallery/table view.
        self.health_panel.element_selected.connect(self.on_start_page_element_activated)
        self.health_dock.setWidget(self.health_panel)
        self.health_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.health_dock)

        # Settings dock
        self.settings_dock = QtWidgets.QDockWidget("Settings", self)
        self.settings_panel = SettingsPanel(self.config, self.db, main_window=self)
        self._force_panel_palette(self.settings_panel, "#191a1a")
        self.settings_panel.settings_changed.connect(self.on_settings_changed)
        self.settings_dock.setWidget(self.settings_panel)
        self.settings_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.settings_dock)

        # Analytics dock
        if _ANALYTICS_AVAILABLE:
            self.analytics_dock = QtWidgets.QDockWidget("Analytics", self)
            self.analytics_panel = AnalyticsPanel(self.db)
            self._force_panel_palette(self.analytics_panel, "#191a1a")
            self.analytics_dock.setWidget(self.analytics_panel)
            self.analytics_dock.setVisible(False)
            self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.analytics_dock)
        else:
            self.analytics_dock = None
            self.analytics_panel = None

        self.create_menus()
        self.statusBar().showMessage("Ready")

    def setup_toolbar(self):
        self.toolbar = QtWidgets.QToolBar("Main Toolbar", self)
        self.toolbar.setIconSize(QtCore.QSize(20, 20))
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("QToolBar { spacing: 6px; padding: 4px; }")
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.toolbar)

        ingest_action = QtWidgets.QAction(get_icon("import", size=20), "Ingest Files", self)
        ingest_action.setToolTip("Ingest files into StaX (Ctrl+I)")
        ingest_action.triggered.connect(self.ingest_files)
        self.toolbar.addAction(ingest_action)

        ingest_library_action = QtWidgets.QAction(get_icon("folder", size=20), "Ingest Library", self)
        ingest_library_action.setToolTip("Bulk ingest folder structures (Ctrl+Shift+I)")
        ingest_library_action.triggered.connect(self.ingest_library)
        self.toolbar.addAction(ingest_library_action)

        self.toolbar.addSeparator()

        search_action = QtWidgets.QAction(get_icon("search", size=20), "Search", self)
        search_action.setToolTip("Advanced search (Ctrl+F)")
        search_action.triggered.connect(self.show_advanced_search)
        self.toolbar.addAction(search_action)

        favorites_action = QtWidgets.QAction(get_icon("favorite", size=20), "Favorites", self)
        favorites_action.setToolTip("Show favorites across stacks")
        favorites_action.triggered.connect(self.on_favorites_selected)
        self.toolbar.addAction(favorites_action)
        self.favorites_action = favorites_action

        self.toolbar.addSeparator()

        history_action = QtWidgets.QAction(get_icon("history", size=20), "History", self)
        history_action.setToolTip("Show ingestion history (Ctrl+2)")
        history_action.triggered.connect(self.toggle_history)
        self.toolbar.addAction(history_action)

        settings_action = QtWidgets.QAction(get_icon("settings", size=20), "Settings", self)
        settings_action.setToolTip("Open settings panel (Ctrl+3)")
        settings_action.triggered.connect(self.toggle_settings)
        self.toolbar.addAction(settings_action)

        if _ANALYTICS_AVAILABLE:
            analytics_action = QtWidgets.QAction(get_icon("chart", size=20), "Analytics", self)
            analytics_action.setToolTip("Show usage analytics (Ctrl+4)")
            analytics_action.triggered.connect(self.toggle_analytics)
            self.toolbar.addAction(analytics_action)

    def create_menus(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        ingest_action = QtWidgets.QAction("Ingest Files...", self)
        ingest_action.setIcon(get_icon("import", size=16))
        ingest_action.setShortcut("Ctrl+I")
        ingest_action.triggered.connect(self.ingest_files)
        file_menu.addAction(ingest_action)
        ingest_library_action = QtWidgets.QAction("Ingest Library...", self)
        ingest_library_action.setIcon(get_icon("folder", size=16))
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

        search_menu = menubar.addMenu("Search")
        advanced_search_action = QtWidgets.QAction("Advanced Search...", self)
        advanced_search_action.setIcon(get_icon("search", size=16))
        advanced_search_action.setShortcut("Ctrl+F")
        advanced_search_action.triggered.connect(self.show_advanced_search)
        search_menu.addAction(advanced_search_action)

        view_menu = menubar.addMenu("View")
        history_view_action = QtWidgets.QAction("History Panel", self)
        history_view_action.setIcon(get_icon("history", size=16))
        history_view_action.setShortcut("Ctrl+2")
        history_view_action.setCheckable(True)
        history_view_action.triggered.connect(self.toggle_history)
        view_menu.addAction(history_view_action)
        settings_view_action = QtWidgets.QAction("Settings Panel", self)
        settings_view_action.setIcon(get_icon("settings", size=16))
        settings_view_action.setShortcut("Ctrl+3")
        settings_view_action.setCheckable(True)
        settings_view_action.triggered.connect(self.toggle_settings)
        view_menu.addAction(settings_view_action)
        if _ANALYTICS_AVAILABLE:
            analytics_view_action = QtWidgets.QAction("Analytics Panel", self)
            analytics_view_action.setShortcut("Ctrl+4")
            analytics_view_action.setCheckable(True)
            analytics_view_action.triggered.connect(self.toggle_analytics)
            view_menu.addAction(analytics_view_action)
        health_view_action = QtWidgets.QAction("Health Panel", self)
        health_view_action.setShortcut("Ctrl+5")
        health_view_action.setCheckable(True)
        health_view_action.triggered.connect(self.toggle_health)
        view_menu.addAction(health_view_action)
        self.health_view_action = health_view_action

        layout_menu = view_menu.addMenu("Layout")
        for preset_name in preset_names():
            act = QtWidgets.QAction(preset_name, self)
            act.triggered.connect(
                lambda checked=False, n=preset_name: apply_preset(self, n)
            )
            layout_menu.addAction(act)

        help_menu = menubar.addMenu("Help")
        doc_action = QtWidgets.QAction("Documentation", self)
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
        install_nuke_action.triggered.connect(self.show_nuke_installer)
        help_menu.addAction(install_nuke_action)
        shortcut_help_action = QtWidgets.QAction("Keyboard Shortcuts", self)
        shortcut_help_action.triggered.connect(self.open_shortcut_help)
        help_menu.addAction(shortcut_help_action)
        onboarding_action = QtWidgets.QAction("Getting Started", self)
        onboarding_action.triggered.connect(self.open_onboarding_checklist)
        help_menu.addAction(onboarding_action)

    def setup_shortcuts(self):
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+2"), self, self.toggle_history)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+3"), self, self.toggle_settings)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+5"), self,
            lambda: self.toggle_health(not self.health_dock.isVisible())
        )
        if _ANALYTICS_AVAILABLE:
            QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+4"), self, self.toggle_analytics)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+K"), self, self.open_command_palette)
        QtWidgets.QShortcut(QtGui.QKeySequence("?"), self, self.open_shortcut_help)

    def open_command_palette(self):
        from src.ui.command_palette import CommandPalette, harvest_actions, build_jump_targets
        entries = harvest_actions(self.menuBar(), self.toolbar)
        try:
            entries = entries + build_jump_targets(
                self.db, self.config, self.on_list_selected, self.on_stack_selected
            )
        except Exception:
            log.warning("Failed to build command-palette jump targets", exc_info=True)
        pal = CommandPalette(entries, self)
        pal.move(self.geometry().center() - pal.rect().center())
        pal.show()
        pal.search_box.setFocus()

    def open_shortcut_help(self):
        """Show the read-only keyboard-shortcut cheat sheet (design SS3.3).

        Harvests every bound `QAction` shortcut from the live menu bar,
        grouped by the menu it lives under, and appends a short static
        block for the EP3 keys that aren't backed by a `QAction` (raw
        `QShortcut`s and overlay-local key handling): the command palette
        (open + in-palette navigation/run), quicklook (open + prev/next),
        and this dialog's own Esc-to-close / `?`-to-open.
        """
        from src.ui.shortcut_help_overlay import ShortcutHelpOverlay, collect_shortcuts_grouped
        pairs = collect_shortcuts_grouped(self.menuBar())
        pairs += [
            ("Shortcuts", "Command palette", "Ctrl+K"),
            ("Shortcuts", "Move selection in palette", "↑ / ↓"),
            ("Shortcuts", "Run selected command", "Enter"),
            ("Shortcuts", "Quicklook selected element", "Space"),
            ("Shortcuts", "Quicklook previous / next element", "← / →"),
            ("Shortcuts", "Close quicklook / palette / this dialog", "Esc"),
            ("Shortcuts", "Keyboard shortcuts help", "?"),
        ]
        ShortcutHelpOverlay(pairs, self).exec_()

    def open_onboarding_checklist(self):
        """Show (or re-show) the first-run "Getting started" checklist
        (design SS3.8). Reachable from Help -> "Getting Started" as well
        as automatically at startup while `onboarding_dismissed` is unset.

        Non-modal by construction: a plain `.show()` on a `Qt.Tool`-flagged
        floating widget, never `exec_()`. Safe to call from the constructor
        path -- it never blocks the event loop.
        """
        if self.onboarding_checklist is None:
            oc = OnboardingChecklist(self.db, self.config, parent=self)
            oc.setWindowFlags(QtCore.Qt.Tool)
            oc.action_requested.connect(self._on_onboarding_action)
            self.onboarding_checklist = oc
        else:
            self.onboarding_checklist.refresh()
        self.onboarding_checklist.move(
            self.geometry().center() - self.onboarding_checklist.rect().center()
        )
        self.onboarding_checklist.show()
        self.onboarding_checklist.raise_()

    def _on_onboarding_action(self, step):
        """Wire an onboarding step's one-click action to its real entry
        point. The checklist widget itself knows nothing about MainWindow;
        it only emits the step name.
        """
        if step == "Create a stack":
            self.stacks_panel.add_stack()
        elif step == "Ingest files":
            self.ingest_files()
        else:
            log.debug("Onboarding: no wired action for step %r", step)

    # -------------------------------------------------------------------------
    # Toggle handlers
    # -------------------------------------------------------------------------

    def toggle_history(self):
        visible = not self.history_dock.isVisible()
        self.history_dock.setVisible(visible)
        if visible:
            self.history_panel.load_history()

    def toggle_health(self, visible):
        self.health_dock.setVisible(visible)
        self.health_view_action.setChecked(visible)
        if visible and self._current_list_id is not None:
            self.health_panel.load_list(self._current_list_id)

    def toggle_settings(self):
        if not self.current_user:
            if not self.show_login(required=True):
                QtWidgets.QMessageBox.information(
                    self, "Login Required", "You must login to access settings."
                )
                return
        self.settings_dock.setVisible(not self.settings_dock.isVisible())

    def toggle_analytics(self):
        if not self.analytics_dock:
            return
        visible = not self.analytics_dock.isVisible()
        self.analytics_dock.setVisible(visible)
        if visible:
            self.analytics_panel.refresh()

    # -------------------------------------------------------------------------
    # Focus mode
    # -------------------------------------------------------------------------

    def toggle_focus_mode(self, checked):
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return
        if checked:
            self._stored_left_width = sizes[0] if sizes[0] > 0 else self.stacks_panel.minimumWidth()
            total_width = self.main_splitter.width()
            preview_width = sizes[2]
            center_width = max(400, total_width - preview_width)
            self.main_splitter.setSizes([0, center_width, preview_width])
            self.stacks_panel.hide()
            self.toolbar.hide()
            if self.history_dock.isVisible():
                self.history_dock.hide()
            if self.settings_dock.isVisible():
                self.settings_dock.hide()
            if self.analytics_dock and self.analytics_dock.isVisible():
                self.analytics_dock.hide()
            if hasattr(self.media_display, "pagination"):
                self.media_display.pagination.hide()
        else:
            restore_width = self._stored_left_width or self.stacks_panel.minimumWidth()
            total_width = self.main_splitter.width()
            preview_width = sizes[2]
            center_width = max(400, total_width - restore_width - preview_width)
            self.main_splitter.setSizes([restore_width, center_width, preview_width])
            self.stacks_panel.show()
            self.toolbar.show()
            if (hasattr(self.media_display, "pagination")
                    and self.config.get("pagination_enabled", True)
                    and len(self.media_display.current_elements) > 0):
                self.media_display.pagination.show()

    # -------------------------------------------------------------------------
    # Preview pane helpers
    # -------------------------------------------------------------------------

    def _right_column_collapsed_width(self):
        """Narrowest `main_splitter`'s 3rd column (video preview +
        `InspectorPanel`, EP3 Task 6) may go while the preview is
        collapsed -- just wide enough to keep the sticky inspector
        (design SS3.4), including its "No selection" state, usable.
        Derived from the inspector's own `minimumSizeHint()` rather than a
        bare magic number so it stays correct if the inspector's layout
        changes."""
        return max(self.inspector.minimumSizeHint().width(), 240)

    def expand_preview_pane(self):
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return
        total = sum(sizes)
        left_width = max(self.stacks_panel.minimumWidth(), sizes[0])
        available = max(0, total - left_width)
        # An explicitly-remembered preset width (apply_preset(), EP3 Task 6
        # fix) must be able to raise this cap, not just be clipped by it --
        # otherwise Review's 860px column snaps right back to ~1/3 of
        # available space at realistic window sizes (e.g. the app's own
        # 1400x800 default), which is byte-identical to the pre-fix
        # behavior. The `available - 420` center-floor guard a few lines
        # down still applies afterwards, so the center pane's protection is
        # unchanged.
        preview_width = min(
            self.preview_pane_expanded_width,
            max(320, available // 3, self.preview_pane_expanded_width),
        )
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
        """Hide the video preview, but keep the right column -- and the
        sticky inspector living inside it (design SS3.4) -- visible at a
        narrow, usable width.

        Earlier code drove `main_splitter`'s 3rd column straight to width
        0. That was correct back when the 3rd column WAS the preview; now
        that `right_splitter` nests `video_player_pane` and
        `InspectorPanel` together in that column (EP3 Task 6), collapsing
        it to 0 also hid the always-should-be-reachable inspector,
        including its "No selection" state.

        `video_player_pane.hide()` runs before the width is computed so
        the floor below reflects the column's real minimum once the
        preview is gone, not the still-visible video widget's (larger)
        minimum -- otherwise `main_splitter` (which has
        `setChildrenCollapsible(False)`) would refuse to shrink the column
        past the video widget's own minimum size on this same call.
        """
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3:
            return
        self.video_player_pane.hide()
        floor = self._right_column_collapsed_width()
        if sizes[2] > floor:
            self.preview_pane_expanded_width = sizes[2]
        if sizes[2] != floor:
            sizes[1] = max(0, sizes[1] + (sizes[2] - floor))
            sizes[2] = floor
            self.main_splitter.setSizes(sizes)

    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------

    def show_nuke_installer(self):
        try:
            dlg = NukeInstallerDialog(self)
            dlg.exec_()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to open Nuke installer: {}".format(exc))

    def show_login(self, required=False):
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = self.current_user and self.current_user.get("role") == "admin"
            username = self.current_user["username"] if self.current_user else "Guest"
            role_text = " (Admin)" if self.is_admin else ""
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
                    self.current_user["username"] if self.current_user else "guest",
                    self.current_user.get("role", "guest") if self.current_user else "guest",
                )
            )
            return False
        return True

    def logout(self):
        if self.current_user and self.current_user.get("user_id"):
            import socket
            machine_name = socket.gethostname()
            session = self.db.get_active_session(self.current_user["user_id"], machine_name)
            if session:
                self.db.end_session(session["session_id"])
        self.show_login()

    # -------------------------------------------------------------------------
    # View event handlers
    # -------------------------------------------------------------------------

    def on_list_selected(self, list_id):
        if getattr(self.stacks_panel, "get_selected_tags", None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_elements(list_id)
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst["stack_fk"])
            if stack:
                self.statusBar().showMessage("Viewing: {} > {}".format(stack["name"], lst["name"]))
        self._current_list_id = list_id
        if self.health_dock.isVisible():
            self.health_panel.load_list(list_id)
        self.active_view = ("list", list_id)
        self._view_before_tags = None

    def on_stack_selected(self, stack_id):
        if not self.config.get("show_entire_stack_elements", False):
            return
        lists = self.db.get_lists_by_stack(stack_id)
        all_elements = []
        for lst in lists:
            all_elements.extend(self.db.get_elements_by_list(lst["list_id"]))
        self.media_display.current_list_id = None
        self.media_display.current_elements = all_elements
        self.media_display.current_tag_filter = []
        if self.config.get("pagination_enabled", True):
            self.media_display.pagination.set_total_items(len(all_elements))
            self.media_display.pagination.set_items_per_page(self.config.get("items_per_page", 100))
            self.media_display.pagination.setVisible(len(all_elements) > 0)
        else:
            self.media_display.pagination.setVisible(False)
        if all_elements:
            self.media_display.content_stack.setCurrentIndex(1)
        else:
            stack = self.db.get_stack_by_id(stack_id)
            if stack:
                # Route through the widget's own public entry point so the
                # nested empty-page stack is actually reset to the legacy
                # page (a bare content_stack.setCurrentIndex(0) only flips
                # the outer index and can leave a stale EP1 empty page --
                # e.g. from a prior search or tag filter -- on screen).
                self.media_display.show_empty_state(
                    "No elements in stack '{}'".format(stack["name"]),
                    "Add lists and elements to this stack",
                )
        self.media_display._display_current_page()
        stack = self.db.get_stack_by_id(stack_id)
        if stack:
            self.statusBar().showMessage("Viewing: {} (all lists)".format(stack["name"]))
        self.active_view = ("stack", stack_id)

    def on_favorites_selected(self):
        if getattr(self.stacks_panel, "get_selected_tags", None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_favorites()
        self.statusBar().showMessage("Viewing: Favorites")
        self.active_view = ("favorites", None)
        self._view_before_tags = None

    def on_playlist_selected(self, playlist_id):
        if getattr(self.stacks_panel, "get_selected_tags", None):
            selected_tags = self.stacks_panel.get_selected_tags()
            if selected_tags:
                self._suspend_tag_restore = True
                self.stacks_panel.clear_tag_selection(emit_signal=True)
        self.media_display.load_playlist(playlist_id)
        playlist = self.db.get_playlist_by_id(playlist_id)
        if playlist:
            self.statusBar().showMessage("Viewing Playlist: {}".format(playlist["name"]))
        self.active_view = ("playlist", playlist_id)
        self._view_before_tags = None

    def on_start_page_element_activated(self, element_id):
        """StartPage card activation (EP3 Task 11 / final review "also
        fix"): select the element and reveal its list, per spec Sec3.9
        ("clicking a card should select the element / open its list") --
        NOT insert it into Nuke the way a gallery double-click does. A
        Recent/Favorites/Most-used card is a navigation shortcut, not an
        "add this to my script" action, and the start page is shown
        precisely when nothing is selected yet -- silently inserting a
        node the user only meant to look at would be a surprising,
        hard-to-undo side effect.

        Reuses the existing list-selection and in-view-selection paths
        (MainWindow.on_list_selected, MediaDisplayWidget.
        _select_element_in_view -- the same helper select_next_element/
        select_previous_element already rely on) rather than inventing a
        new one.
        """
        element = self.db.get_element_by_id(element_id)
        if not element:
            return
        list_id = element.get('list_fk')
        if list_id:
            self.on_list_selected(list_id)
        self.media_display._select_element_in_view(element)

    def on_element_double_clicked(self, element_id):
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted: {}".format(element["name"]))
            if _ANALYTICS_AVAILABLE:
                try:
                    import socket
                    uid = self.current_user.get("user_id") if self.current_user else None
                    log_insertion(
                        db=self.db, element_id=element_id, user_id=uid,
                        project=os.environ.get("STAX_PROJECT", ""),
                        host=socket.gethostname(),
                    )
                except Exception:
                    logging.getLogger(__name__).warning("Analytics logging failed", exc_info=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))

    def on_advanced_search_result(self, element_id):
        """Handle activation of an advanced-search result: insert it, same path
        as a gallery double-click. (Fixes audit issue M4.)"""
        self.on_element_double_clicked(element_id)

    def on_selection_changed(self):
        selected_ids = self.media_display.get_selected_element_ids()
        if len(selected_ids) == 1:
            self.expand_preview_pane()
            self.video_player_pane.load_element(selected_ids[0])
            self.inspector.show_element(selected_ids[0])
        elif len(selected_ids) > 1:
            self.video_player_pane.clear()
            self.collapse_preview_pane()
            self.inspector.clear()
        else:
            if self.video_player_pane.isVisible():
                self.video_player_pane.clear()
            self.inspector.clear()

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
            if self.active_view[0] == "tags" and self._view_before_tags:
                self.active_view = self._view_before_tags
                self._view_before_tags = None
                self.restore_active_view()
            return
        if not self._view_before_tags and self.active_view[0] != "tags":
            self._view_before_tags = self.active_view
        self.active_view = ("tags", tuple(tags))
        self.media_display.load_elements_by_tags(tags)
        self.statusBar().showMessage("Filtering by tags: {}".format(", ".join(tags)))

    def restore_active_view(self):
        mode, value = self.active_view
        if mode == "list" and value:
            self.media_display.load_elements(value)
        elif mode == "favorites":
            self.media_display.load_favorites()
        elif mode == "playlist" and value:
            self.media_display.load_playlist(value)
        elif mode == "tags" and value:
            self.media_display.load_elements_by_tags(list(value))
        else:
            self.media_display.show_empty_state()

    # -------------------------------------------------------------------------
    # Ingestion
    # -------------------------------------------------------------------------

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
        jobs = [(f, target_list_id) for f in files]
        progress = QtWidgets.QProgressDialog(
            "Ingesting files...", "Cancel", 0, len(jobs), self
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)

        worker = IngestWorker(
            self.db, self.config.get_all(), jobs,
            copy_policy=self.config.get("default_copy_policy"),
        )
        self._ingest_worker = worker            # keep a reference alive

        worker.progress.connect(
            lambda done, total, label: (
                progress.setValue(done - 1),
                progress.setLabelText("Ingesting: {}".format(label)),
            )
        )
        progress.canceled.connect(worker.cancel)
        worker.ingest_finished.connect(
            lambda s, k, e: self._on_perform_ingestion_done(progress, s, k, e)
        )
        worker.ingest_failed.connect(
            lambda msg: self._on_perform_ingestion_failed(progress, msg)
        )

        # EP6: ingest_jobs ledger + Job Queue dashboard wiring (additive --
        # does not replace the SP2 connections above).
        self._record_ingest_jobs(files, target_list_id)
        worker.file_done.connect(self._on_job_file_done)
        worker.ingest_finished.connect(self._on_ingest_finished_notify)

        worker.start()
        progress.exec_()

    def _on_perform_ingestion_done(self, progress, success, skipped, errors):
        progress.reset()
        msg = "Ingested {} file(s) successfully.".format(success)
        if skipped:
            msg += "\n{} skipped (duplicates).".format(skipped)
        if errors:
            msg += "\n{} error(s).".format(errors)
        QtWidgets.QMessageBox.information(self, "Ingestion Complete", msg)
        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)

    def _on_perform_ingestion_failed(self, progress, message):
        progress.reset()
        QtWidgets.QMessageBox.critical(self, "Ingestion Error", message)

    # -------------------------------------------------------------------------
    # Ingest job ledger + dashboard wiring (EP6, F033/F034/F039)
    # -------------------------------------------------------------------------

    def _record_ingest_jobs(self, files, target_list_id, recipe_id=None):
        """Insert one pending ingest_jobs row per file; return the job ids."""
        ids = []
        for f in files:
            ids.append(self.db.create_job(
                "ingest", f, target_list_id=target_list_id, recipe_id=recipe_id,
                payload={"source_path": f, "target_list_id": target_list_id,
                         "recipe_id": recipe_id}))
        return ids

    def _on_job_file_done(self, result):
        """Update the matching pending/running ledger row from an IngestWorker result."""
        if not isinstance(result, dict):
            return
        src = result.get("source_path")
        job = None
        for j in self.db.get_jobs(status="running") + self.db.get_jobs(status="pending"):
            if j.get("source_path") == src:
                job = j
                break
        if job is None:
            return
        if result.get("success"):
            status = "done"
        elif result.get("reason") == "duplicate_skipped":
            status = "skipped"
        else:
            status = "failed"
        self.db.update_job_status(job["job_id"], status, message=result.get("message"))
        self.job_dashboard.refresh()

    def _on_ingest_finished_notify(self, success, skipped, errors):
        level = "error" if errors else "success"
        self.db.add_notification(
            "Ingest complete",
            "{} ok / {} skipped / {} errors".format(success, skipped, errors),
            level=level)
        self.statusBar().showMessage(
            "Ingest complete: {} ok, {} skipped, {} errors".format(success, skipped, errors),
            5000)
        self.job_dashboard.refresh()

    def _retry_job(self, job_id):
        """Re-submit a failed job's payload to a fresh IngestWorker (SP2 seam)."""
        job = self.db.get_job(job_id)
        if not job or not job.get("payload"):
            return
        payload = job["payload"]
        self.db.update_job_status(job_id, "pending")
        self.db.bump_job_attempt(job_id)
        worker = IngestWorker(
            self.db, self.config.get_all(),
            [(payload["source_path"], payload["target_list_id"])],
            copy_policy=self.config.get("default_copy_policy"))
        self._ingest_worker = worker
        # Also hold a strong reference in self._retry_workers: a second
        # retry (or a retry overlapping an in-flight batch ingest)
        # overwrites self._ingest_worker, and without this list the
        # superseded worker's only reference would be gone while its
        # QThread is still running -- a premature-GC risk. Entries are
        # dropped once the thread's `finished` signal fires.
        self._retry_workers.append(worker)
        worker.file_done.connect(self._on_job_file_done)
        worker.ingest_finished.connect(self._on_ingest_finished_notify)
        worker.ingest_failed.connect(
            lambda msg, jid=job_id: self._on_retry_job_failed(jid, msg))
        worker.finished.connect(lambda w=worker: self._forget_retry_worker(w))
        worker.start()

    # -------------------------------------------------------------------------
    # Watch-folder scanner lifecycle (EP6, F031/F032)
    # -------------------------------------------------------------------------

    def _start_watch_scanner(self):
        """Build and start a WatchFolderScanner over the enabled watch_folders
        rows. No-op (self._watch_scanner = None) when none are enabled."""
        rows = self.db.get_watch_folders(enabled_only=True)
        if not rows:
            self._watch_scanner = None
            return
        interval = min((r["interval_sec"] for r in rows), default=30)
        self._watch_scanner = WatchFolderScanner(rows, interval_sec=interval)
        self._watch_scanner.files_detected.connect(self._on_watched_files)
        self._watch_scanner.start()

    def _stop_watch_scanner(self):
        """Stop the watch scanner thread (if running) and drop the reference."""
        scanner = getattr(self, "_watch_scanner", None)
        if scanner is not None:
            scanner.stop()
            scanner.wait(2000)
        self._watch_scanner = None

    def _on_watched_files(self, watch_id, paths):
        """Record ledger rows for newly-detected files and ingest them
        off-thread, applying the watch folder's recipe overlay (if any)."""
        row = next(
            (r for r in self.db.get_watch_folders() if r["watch_id"] == watch_id),
            None)
        if not row:
            return
        target = row.get("target_list_id")
        recipe_id = row.get("recipe_id")
        self._record_ingest_jobs(paths, target, recipe_id=recipe_id)

        config = self.config.get_all()
        if recipe_id:
            recipe = next(
                (rc for rc in self.db.get_ingest_recipes()
                 if rc["recipe_id"] == recipe_id),
                None)
            if recipe:
                config = apply_recipe_to_config(recipe["values"], config)

        jobs = [(p, target) for p in paths]
        worker = IngestWorker(
            self.db, config, jobs,
            copy_policy=config.get("default_copy_policy", "soft"))
        # Hold a strong reference in a list, not a single overwritable slot:
        # WatchFolderScanner.scan_once can emit files_detected for several
        # enabled folders in the same pass, so a second _on_watched_files
        # call must not clobber a still-running worker from the first.
        self._watch_ingest_workers.append(worker)
        worker.file_done.connect(self._on_job_file_done)
        worker.ingest_finished.connect(self._on_ingest_finished_notify)
        worker.finished.connect(lambda w=worker: self._forget_watch_worker(w))
        worker.start()

    def _on_retry_job_failed(self, job_id, message):
        """A retried job's IngestWorker raised (worker.ingest_failed carries
        no job id itself, so this closes over the one being retried)."""
        self.db.update_job_status(job_id, "failed", message=message)
        self.job_dashboard.refresh()

    def _forget_retry_worker(self, worker):
        if worker in self._retry_workers:
            self._retry_workers.remove(worker)

    def _forget_watch_worker(self, worker):
        if worker in self._watch_ingest_workers:
            self._watch_ingest_workers.remove(worker)

    def _cancel_job(self, job_id):
        if getattr(self, "_ingest_worker", None) is not None:
            self._ingest_worker.cancel()
        self.db.update_job_status(job_id, "cancelled")
        self.job_dashboard.refresh()

    def ingest_library(self):
        dialog = IngestLibraryDialog(self.db, self.ingestion, self.config, self)
        if dialog.exec_():
            self.stacks_panel.load_data()

    def register_toolset(self):
        dialog = RegisterToolsetDialog(self.db, self.nuke_integration, self.config, self)
        if dialog.exec_():
            if hasattr(self.media_display, "current_list_id") and self.media_display.current_list_id:
                self.media_display.load_elements(self.media_display.current_list_id)
            self.statusBar().showMessage("Toolset registered successfully")

    def on_settings_changed(self):
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.statusBar().showMessage("Settings updated")

        # Final-review Finding 2: a label/synonym/smart-collection edit in
        # SettingsPanel must refresh the open gallery's stale label chips
        # and the nav's saved-search/smart-collection lists -- both were
        # previously left stale until the next list navigation / app reload.
        if hasattr(self, 'media_display'):
            try:
                self.media_display._label_color_cache = None
                self.media_display.refresh_current_view()
            except Exception:
                log.exception("Failed to refresh media display after settings change")

        if hasattr(self, 'stacks_panel'):
            try:
                self.stacks_panel.refresh_smart_collections()
                self.stacks_panel.refresh_saved_searches()
            except Exception:
                log.exception("Failed to refresh nav panel after settings change")

    def show_advanced_search(self):
        if not hasattr(self, "advanced_search_dialog") or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
            self.advanced_search_dialog.result_activated.connect(self.on_advanced_search_result)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()

    def show_about(self):
        QtWidgets.QMessageBox.about(
            self, "About Stax",
            "<h3>Stax</h3>"
            "<p>Version 0.9.3</p>"
            "<p>Advanced Stock Management for VFX Studios</p>"
            "<p>Author: Ahmed Ramadan</p>"
            "<p><a href='https://aramadan0096.github.io/stax-docs/'>Docs</a></p>"
        )

    # -------------------------------------------------------------------------
    # Close
    # -------------------------------------------------------------------------

    def closeEvent(self, event):
        self._stop_watch_scanner()
        if _PREVIEW_WORKER_AVAILABLE:
            shutdown_preview_queue()
        if _API_SERVER_AVAILABLE:
            shutdown_api_server()
        super(MainWindow, self).closeEvent(event)


# =============================================================================
# Entry point
# =============================================================================

def main():
    try:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)
    config = Config()
    DebugManager.sync_from_config(config)
    config.ensure_directories()

    # STEP 1 — Fusion style
    app.setStyle("Fusion")

    # STEP 2 — Dark palette (MUST be before any widget construction and before QSS)
    try:
        apply_dark_palette(app)
    except Exception:
        logging.getLogger(__name__).exception("Failed to apply dark palette; using default")

    # STEP 3 — QSS fine-grained overrides on top of the palette
    stylesheet_path = os.path.join(os.path.dirname(__file__), "resources", "style.qss")
    if os.path.exists(stylesheet_path):
        try:
            with open(stylesheet_path, "r") as f:
                stylesheet = f.read()
            resources_dir = os.path.join(os.path.dirname(__file__), "resources", "icons")
            unchecked_path = os.path.join(resources_dir, "unchecked.svg").replace("\\", "/")
            checked_path   = os.path.join(resources_dir, "checked.svg").replace("\\", "/")
            stylesheet = stylesheet.replace("url(:/icons/unchecked.svg)", "url({})".format(unchecked_path))
            stylesheet = stylesheet.replace("url(:/icons/checked.svg)",   "url({})".format(checked_path))
            app.setStyleSheet(stylesheet)
        except Exception as e:
            print("Failed to load stylesheet: {}".format(e))

    # STEP 3.5 — Accessibility overlay (high contrast / text scale / focus
    # assist). MUST come after STEP 3's app.setStyleSheet(stylesheet): that
    # call replaces the app stylesheet outright, so applying accessibility
    # any earlier would (a) get wiped by it, and (b) cause accessibility.py
    # to cache the empty pre-QSS string as the "base" stylesheet, permanently
    # losing the dark theme on every later toggle. Must also come before
    # STEP 4, so the window is built with accessibility already in effect.
    try:
        apply_accessibility(app, config)
    except Exception:
        logging.getLogger(__name__).exception("Failed to apply accessibility settings")

    # STEP 4 — Create window (palette and QSS are already in effect)
    window = MainWindow(config=config)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()