# -*- coding: utf-8 -*-
"""
Media Display Widget with Gallery/List Views
"""

import logging
import os
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon, get_pixmap
from src.preview_cache import get_preview_cache
from src.utils.paths import resolve_path
from src.utils.formatting import human_size
from src.ui.media_info_popup import MediaInfoPopup
from src.ui.drag_gallery_view import DragGalleryView
from src.ui.pagination_widget import PaginationWidget
from src.ui.dialogs import AddToPlaylistDialog, EditElementDialog

logger = logging.getLogger(__name__)


class MediaDisplayWidget(QtWidgets.QWidget):
    """Central widget for displaying media elements."""
    
    # Signals
    element_selected = QtCore.Signal(int)  # element_id
    element_double_clicked = QtCore.Signal(int)  # element_id
    saved_search_created = QtCore.Signal()  # a saved search was persisted (EP2 Task 9)
    
    def __init__(self, db_manager, config, nuke_bridge, main_window=None, parent=None):
        super(MediaDisplayWidget, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.nuke_bridge = nuke_bridge
        self.main_window = main_window  # Reference to MainWindow for permission checks
        self.current_list_id = None
        self.current_elements = []  # Store all elements for pagination
        self.current_tag_filter = []
        self.view_mode = 'gallery'  # 'gallery' or 'list'
        self.alt_pressed = False  # Track Alt key state
        self.hover_timer = QtCore.QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_info_popup)
        self.hover_item = None
        self.hover_row = -1
        self.media_popup = MediaInfoPopup(self)
        self.media_popup.insert_requested.connect(self.on_popup_insert)
        self.media_popup.reveal_requested.connect(self.on_popup_reveal)
        self.preview_cache = get_preview_cache()  # Initialize preview cache
        self.gif_movies = {}  # Cache for QMovie objects {element_id: QMovie}
        self._pending_icon_size = None
        self._size_debounce = QtCore.QTimer(self)
        self._size_debounce.setSingleShot(True)
        self._size_debounce.timeout.connect(lambda: self._apply_pending_size())
        self.current_gif_item = None  # Currently hovering item with GIF
        self.element_items = {}  # Map element_id -> QListWidgetItem
        self.element_flags = {}  # Map element_id -> status flags (favorite/deprecated)
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.setup_ui()

        # EP2 Task 6: faceted filter drawer + removable chip bar, wired
        # after the views are built (self.content_stack must already
        # exist for _install_filter_widgets to reparent it). Flat imports
        # to match the module identity `from ui.facet_drawer import ...`
        # tests patch (see the dual-import note on ingest_dropped_files).
        from ui.facet_drawer import FacetDrawer
        from ui.filter_chip_bar import FilterChipBar
        from filter_spec import empty_filter
        self.current_filter = empty_filter()
        self.facet_drawer = FacetDrawer()
        self.chip_bar = FilterChipBar()
        self._install_filter_widgets(self.facet_drawer, self.chip_bar)
        self.facet_drawer.filter_changed.connect(self.apply_filter)
        self.chip_bar.chip_removed.connect(self._on_chip_removed)
        self.chip_bar.cleared.connect(lambda: self.apply_filter(empty_filter()))

        # EP2 Task 12: seed the search box's recent-query QCompleter once,
        # at construction. A QCompleter is a non-modal popup, so this is
        # safe on a construction path per the repo's modal-placement rule.
        self._install_recent_completer(self._current_user_name())

        # Enable mouse tracking for hover events
        self.setMouseTracking(True)

        # Enable drag & drop
        self.setAcceptDrops(True)
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        
        # Search bar with tag filtering support
        search_container = QtWidgets.QWidget()
        search_layout = QtWidgets.QVBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search elements... (use #tag or tag:fire for tag filtering)")
        self.search_box.textChanged.connect(self.on_search)
        # EP2 Task 12: record a *committed* search (Enter), never a
        # per-keystroke one -- see _on_search_committed's docstring.
        self.search_box.returnPressed.connect(self._on_search_committed)
        search_layout.addWidget(self.search_box)

        # Search hint label
        self.search_hint_label = QtWidgets.QLabel()
        self.search_hint_label.setStyleSheet("color: #888888; font-size: 10px; font-style: italic;")
        self.search_hint_label.hide()  # Hidden by default
        search_layout.addWidget(self.search_hint_label)

        # EP2 Task 12: "did you mean" suggestion. Hidden by default, same
        # as search_hint_label above; run_text_search shows it when a
        # cross-list text search matches nothing but suggest_correction
        # finds a close vocabulary term.
        self.did_you_mean_label = QtWidgets.QLabel()
        self.did_you_mean_label.setStyleSheet("color: #cc9944; font-size: 10px; font-style: italic;")
        self.did_you_mean_label.hide()  # Hidden by default
        search_layout.addWidget(self.did_you_mean_label)

        toolbar.addWidget(search_container, 1)  # Give it stretch priority

        # Save current search/filter as a personal saved search (EP2 Task 9).
        self.save_search_btn = QtWidgets.QPushButton("Save search…")
        self.save_search_btn.setToolTip("Save the current search/filter for quick access later")
        self.save_search_btn.setObjectName('small')
        self.save_search_btn.setProperty('class', 'small')
        self.save_search_btn.clicked.connect(self._on_save_search_clicked)
        toolbar.addWidget(self.save_search_btn)

        # View mode toggle
        self.gallery_btn = QtWidgets.QPushButton()
        self.gallery_btn.setIcon(get_icon('gallery', size=20))
        self.gallery_btn.setToolTip("Gallery View")
        self.gallery_btn.setObjectName('icon')
        self.gallery_btn.setProperty('class', 'small')
        self.gallery_btn.setCheckable(True)
        self.gallery_btn.setChecked(True)
        self.gallery_btn.clicked.connect(lambda: self.set_view_mode('gallery'))
        toolbar.addWidget(self.gallery_btn)
        
        self.list_btn = QtWidgets.QPushButton()
        self.list_btn.setIcon(get_icon('list', size=20))
        self.list_btn.setToolTip("List View")
        self.list_btn.setObjectName('icon')
        self.list_btn.setProperty('class', 'small')
        self.list_btn.setCheckable(True)
        self.list_btn.clicked.connect(lambda: self.set_view_mode('list'))
        toolbar.addWidget(self.list_btn)
        
        # Element size slider
        self.size_label = QtWidgets.QLabel("Size:")
        toolbar.addWidget(self.size_label)
        
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size_slider.setMinimum(64)
        self.size_slider.setMaximum(512)
        self.size_slider.setValue(256)
        self.size_slider.setMaximumWidth(150)
        self.size_slider.valueChanged.connect(self.on_size_changed)
        toolbar.addWidget(self.size_slider)
        
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        
        # Main content container - stacks empty state and views
        self.content_stack = QtWidgets.QStackedWidget()
        
        # Empty state container with icon and text (index 0)
        self.empty_state_widget = QtWidgets.QWidget()
        empty_state_layout = QtWidgets.QVBoxLayout(self.empty_state_widget)
        empty_state_layout.setAlignment(QtCore.Qt.AlignCenter)
        
        # Icon label (using a large icon)
        self.empty_icon_label = QtWidgets.QLabel()
        self.empty_icon_label.setAlignment(QtCore.Qt.AlignCenter)
        empty_icon = get_icon('film', size=96)
        if empty_icon and not empty_icon.isNull():
            self.empty_icon_label.setPixmap(empty_icon.pixmap(96, 96))
        else:
            fallback_icon = get_icon('folder', size=96)
            if fallback_icon and not fallback_icon.isNull():
                self.empty_icon_label.setPixmap(fallback_icon.pixmap(96, 96))
        self.empty_icon_label.setStyleSheet("padding: 20px;")
        empty_state_layout.addWidget(self.empty_icon_label)
        
        # Info label
        self.info_label = QtWidgets.QLabel("Select a list to view elements")
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #888888; font-size: 14px; padding: 10px; font-weight: bold;")
        empty_state_layout.addWidget(self.info_label)
        
        # Hint label
        self.hint_label = QtWidgets.QLabel("Browse stacks and lists in the navigation panel")
        self.hint_label.setAlignment(QtCore.Qt.AlignCenter)
        self.hint_label.setStyleSheet("color: #666666; font-size: 11px; padding: 5px;")
        empty_state_layout.addWidget(self.hint_label)
        
        empty_state_layout.addStretch()

        # Nested stack for the empty page: keeps content_stack's index-0
        # slot stable while EP1's context-aware empty states
        # (_show_empty_state/_set_empty_page_widget) swap widgets in and
        # out. The legacy self.empty_state_widget stays registered here
        # permanently so external direct writers (main.py:599-601,
        # load_elements, show_empty_state) never AttributeError -- their
        # text just stops being what's on screen once an EP1 empty state
        # replaces it as the visible page.
        self._empty_page_stack = QtWidgets.QStackedWidget()
        self._empty_page_stack.addWidget(self.empty_state_widget)
        self.content_stack.addWidget(self._empty_page_stack)  # Index 0
        
        # Views container (index 1)
        views_widget = QtWidgets.QWidget()
        views_layout = QtWidgets.QVBoxLayout(views_widget)
        views_layout.setContentsMargins(0, 0, 0, 0)
        
        # Stacked widget for different views
        self.view_stack = QtWidgets.QStackedWidget()
        
        # Gallery view (grid of thumbnails with drag & drop)
        self.gallery_view = DragGalleryView(self.db, self.config, self.nuke_bridge)
        self.gallery_view.setViewMode(QtWidgets.QListView.IconMode)
        self.gallery_view.setResizeMode(QtWidgets.QListView.Adjust)
        self.gallery_view.setIconSize(QtCore.QSize(256, 256))
        self.gallery_view.setSpacing(10)
        self.gallery_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Multi-select
        self.gallery_view.itemClicked.connect(self.on_item_clicked)
        self.gallery_view.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.gallery_view.setMouseTracking(True)  # Enable hover tracking
        self.gallery_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.gallery_view)
        
        # List view (table)
        self.table_view = QtWidgets.QTableWidget()
        self.table_view.setColumnCount(8)
        self.table_view.setHorizontalHeaderLabels(
            ['Name', 'Format', 'Frames', 'Type', 'Size', 'Comment', 'Rating', 'Label'])
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Multi-select
        self.table_view.itemClicked.connect(self.on_table_item_clicked)
        self.table_view.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        self.table_view.setMouseTracking(True)  # Enable hover tracking
        self.table_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.table_view)
        
        views_layout.addWidget(self.view_stack)
        
        # Pagination widget
        self.pagination = PaginationWidget()
        self.pagination.page_changed.connect(self.on_page_changed)
        self.pagination.setVisible(self.config.get('pagination_enabled', True))
        views_layout.addWidget(self.pagination)
        
        self.content_stack.addWidget(views_widget)  # Index 1
        
        # Show empty state by default
        self.content_stack.setCurrentIndex(0)
        
        layout.addWidget(self.content_stack)
        
        # Focus mode button (floating in bottom-right corner)
        self.focus_mode_button = None
        self.focus_mode_enabled = False
        self.setup_focus_button()

        # EP1: multi-select action tray, docked below the views. Built here
        # (main_window is already assigned at construction, before
        # setup_ui() runs) and fed by both views' selection-changed
        # signals via _on_selection_changed_ep1.
        from ui.multi_select_action_tray import MultiSelectActionTray
        self.action_tray = MultiSelectActionTray(self.db, self.main_window)
        layout.addWidget(self.action_tray)

        self.action_tray.tag_requested.connect(
            lambda: self.bulk_add_tag(self.get_selected_element_ids()))
        self.action_tray.favorite_requested.connect(
            lambda: self.bulk_add_to_favorites(self.get_selected_element_ids()))
        self.action_tray.playlist_requested.connect(
            lambda: self.bulk_add_to_playlist(self.get_selected_element_ids()))
        self.action_tray.deprecate_requested.connect(
            lambda: self.bulk_mark_deprecated(self.get_selected_element_ids()))
        self.action_tray.delete_requested.connect(
            lambda: self.bulk_delete(self.get_selected_element_ids()))
        self.action_tray.edit_requested.connect(
            lambda: self.open_batch_edit(self.get_selected_element_ids()))
        # Rate/label are applied directly by the tray (bulk_set_rating/
        # bulk_set_label write straight to the DB); just repaint afterwards.
        self.action_tray.rate_requested.connect(lambda _stars: self.refresh_current_view())
        self.action_tray.label_requested.connect(lambda _label_id: self.refresh_current_view())

        self.gallery_view.itemSelectionChanged.connect(self._on_selection_changed_ep1)
        self.table_view.itemSelectionChanged.connect(self._on_selection_changed_ep1)

    def _install_filter_widgets(self, drawer, chip_bar):
        """EP2 Task 6: wire the facet drawer + filter chip bar into the
        layout setup_ui() already built.

        The chip bar goes directly above content_stack (between the
        toolbar and the stack); the drawer becomes a collapsible left-hand
        column beside content_stack, via a small horizontal wrapper.
        Reuses setup_ui's own top-level layout (retrieved through
        self.layout(), the same QVBoxLayout instance setup_ui's local
        `layout` variable built) rather than constructing a new one, so
        the toolbar and action_tray -- already in that layout -- are left
        untouched.
        """
        layout = self.layout()
        idx = layout.indexOf(self.content_stack)
        layout.removeWidget(self.content_stack)

        content_row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(content_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(drawer)
        row_layout.addWidget(self.content_stack, 1)

        layout.insertWidget(idx, chip_bar)
        layout.insertWidget(idx + 1, content_row)

        # Design §3.3: "default collapsed until the user filters."
        drawer.setVisible(False)

    def setup_focus_button(self):
        """Create floating action button for focus mode."""
        self.focus_mode_button = QtWidgets.QToolButton(self)
        self.focus_mode_button.setIcon(get_icon('focus', size=20))
        self.focus_mode_button.setIconSize(QtCore.QSize(20, 20))
        self.focus_mode_button.setToolTip("Enter focus mode (hide navigation panel)")
        self.focus_mode_button.setCheckable(True)
        self.focus_mode_button.clicked.connect(self.toggle_focus_mode)
        self.focus_mode_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.focus_mode_button.setStyleSheet(
            """
            QToolButton {
                background-color: rgba(22, 198, 176, 0.9);
                border: 0px;
                border-radius: 22px;
                padding: 10px;
                color: #0b0e0c;
            }
            QToolButton:hover {
                background-color: rgba(22, 198, 176, 1.0);
            }
            QToolButton:checked {
                background-color: rgba(255, 154, 60, 0.95);
                color: #1b1b1b;
            }
            """
        )
        self.focus_mode_button.resize(44, 44)
        self.focus_mode_button.show()
        self.installEventFilter(self)  # Install event filter on self for resize events
        self.position_focus_button()
    
    def position_focus_button(self):
        """Position focus button in bottom-right corner above pagination."""
        if not self.focus_mode_button:
            return
        margin = 16
        # Position above pagination widget
        pagination_height = self.pagination.height() if self.pagination.isVisible() else 0
        parent_rect = self.rect()
        x = max(margin, parent_rect.width() - self.focus_mode_button.width() - margin)
        y = max(margin, parent_rect.height() - self.focus_mode_button.height() - pagination_height - margin - 10)
        self.focus_mode_button.move(x, y)
        self.focus_mode_button.raise_()
    
    def toggle_focus_mode(self, checked):
        """Toggle focus mode - signal to parent to hide/show navigation."""
        self.focus_mode_enabled = checked
        if self.main_window:
            # Signal to main window to hide navigation
            if hasattr(self.main_window, 'toggle_focus_mode'):
                self.main_window.toggle_focus_mode(checked)
        
        # Update tooltip
        if checked:
            self.focus_mode_button.setToolTip("Exit focus mode (show navigation panel)")
        else:
            self.focus_mode_button.setToolTip("Enter focus mode (hide navigation panel)")
    
    def resizeEvent(self, event):
        """Handle resize to reposition focus button."""
        super(MediaDisplayWidget, self).resizeEvent(event)
        self.position_focus_button()
    
    def dragEnterEvent(self, event):
        """Handle drag enter for file drops."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Handle drag move for file drops."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """Handle file drop for ingestion."""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        
        # Check if a list is selected
        if not self.current_list_id:
            QtWidgets.QMessageBox.warning(
                self,
                "No List Selected",
                "Please select a list before dropping files for ingestion."
            )
            event.ignore()
            return
        
        # Get dropped file paths
        urls = event.mimeData().urls()
        file_paths = []
        for url in urls:
            if url.isLocalFile():
                file_paths.append(url.toLocalFile())
        
        if not file_paths:
            event.ignore()
            return
        
        event.acceptProposedAction()
        
        # Trigger ingestion with the dropped files
        self.ingest_dropped_files(file_paths)
    
    def ingest_dropped_files(self, file_paths):
        """Ingest dropped files into the current list, off the GUI thread."""
        # Flat imports (not `src.xxx`): keep this module resolving the same
        # module/class objects tests patch via `import ingest_worker` and
        # `ui.dialogs.IngestProgressDialog.exec_` (see the dual-import note
        # in drag_gallery_view.py).
        from ui.dialogs import IngestProgressDialog
        from ingest_worker import IngestWorker

        if not self.current_list_id:
            QtWidgets.QMessageBox.information(
                self, "No List Selected", "Select a list before ingesting.")
            return

        jobs = [(p, self.current_list_id) for p in file_paths]
        dialog = IngestProgressDialog(self)
        dialog.setWindowTitle("Ingesting Files...")

        # H7: pass a dict (get_all), correct key (default_copy_policy).
        config_dict = self.config.get_all() if hasattr(self.config, "get_all") else self.config
        copy_policy = (config_dict.get("default_copy_policy", "soft")
                       if isinstance(config_dict, dict) else "soft")

        worker = IngestWorker(self.db, config_dict, jobs, copy_policy=copy_policy)
        self._ingest_worker = worker      # H7: hold a member reference until finished

        worker.progress.connect(
            lambda done, total, label: dialog.update_progress(done, total, label))
        worker.ingest_finished.connect(
            lambda s, k, e: self._on_ingest_complete(dialog))
        worker.ingest_failed.connect(
            lambda err: self._on_ingest_failed(dialog, err))
        dialog.rejected.connect(worker.cancel)

        worker.start()
        dialog.exec_()

    def _on_ingest_complete(self, dialog):
        """Handle successful ingestion completion."""
        dialog.accept()
        if self.current_list_id:
            self.load_elements(self.current_list_id)

    def _on_ingest_failed(self, dialog, error_message):
        """Handle ingestion failure."""
        dialog.reject()
        QtWidgets.QMessageBox.critical(self, "Ingestion Error", error_message)

    
    def set_view_mode(self, mode):
        """Switch between gallery and list view."""
        self.view_mode = mode
        
        if mode == 'gallery':
            self.view_stack.setCurrentWidget(self.gallery_view)
            self.gallery_btn.setChecked(True)
            self.list_btn.setChecked(False)
            self.size_slider.setEnabled(True)
        else:
            self.view_stack.setCurrentWidget(self.table_view)
            self.list_btn.setChecked(True)
            self.gallery_btn.setChecked(False)
            self.size_slider.setEnabled(False)
    
    def on_size_changed(self, value):
        """Handle thumbnail size change with debounced expensive reload."""
        self.gallery_view.setIconSize(QtCore.QSize(value, value))

        if not self.current_elements:
            return

        self._pending_icon_size = value
        self._size_debounce.start(150)

    def _apply_pending_size(self):
        """Reload current content once after size slider settles."""
        if not self.current_elements:
            return
        if self.config.get('pagination_enabled', True) and self.current_list_id:
            self._display_current_page()
        else:
            self._update_views_with_elements(self.current_elements)
    
    def load_elements(self, list_id):
        """Load elements for a list with preview caching and pagination."""
        self.current_list_id = list_id
        self.current_tag_filter = []
        elements = self.db.get_elements_by_list(list_id)
        
        # Store all elements for pagination
        self.current_elements = elements
        
        # Show/hide empty state
        if len(elements) == 0:
            lst = self.db.get_list_by_id(list_id)
            if lst:
                self.info_label.setText("No elements in '{}'".format(lst['name']))
                self.hint_label.setText("Drag files here or use 'Ingest Files' to add content")
            self._show_empty_state("list", list_name=lst['name'] if lst else None)
        else:
            self.content_stack.setCurrentIndex(1)  # Show views
        
        # Setup pagination
        if self.config.get('pagination_enabled', True):
            self.pagination.set_total_items(len(elements))
            self.pagination.set_items_per_page(self.config.get('items_per_page', 100))
            self.pagination.setVisible(len(elements) > 0)
        else:
            self.pagination.setVisible(False)
        
        # Display current page
        self._display_current_page()
    
    def on_page_changed(self, page):
        """Handle page change event."""
        self._display_current_page()
    
    def _display_current_page(self):
        """Display elements for the current page."""
        if not self.current_elements:
            return
        
        # Get page slice
        if self.config.get('pagination_enabled', True):
            start, end = self.pagination.get_page_slice()
            page_elements = self.current_elements[start:end]
        else:
            page_elements = self.current_elements
        
        # Use shared method to update both views
        self._update_views_with_elements(page_elements)

    def apply_filter(self, filter_spec):
        """EP2 Task 6: run an advanced query against filter_spec and
        refresh the chip bar, facet drawer counts, and the active view to
        match. This is the sole entry point the facet drawer's
        `filter_changed` signal and the chip bar's `chip_removed`/
        `cleared` signals route back through.

        Bypasses self.pagination for now -- loads every match in one
        query and counts via len(rows) rather than a separate
        count_elements_advanced() + limit/offset page. Wiring pagination
        to filtered results is left for a later task (see the EP2 Task 6
        report).
        """
        from filter_spec import normalize, is_active

        self.current_filter = normalize(filter_spec)
        active = is_active(self.current_filter)

        # Fix pass: reconcile the drawer's internal _state with the spec
        # that is about to drive this refresh, regardless of whether it
        # changed via a drawer checkbox, a chip removal, or a programmatic
        # load (e.g. a saved search) -- otherwise self._state can go stale
        # and a later unrelated checkbox toggle would rebuild the spec from
        # that stale state and resurrect a value the user just removed.
        # Runs before set_facets() below so that set_facets()'s own
        # orphaned-value bookkeeping (which reads self._state to decide
        # which zero-count rows to keep visible) sees the already-
        # reconciled state, not the previous refresh's. sync_from_filter()
        # never emits filter_changed (see its docstring), so this cannot
        # re-enter apply_filter.
        self.facet_drawer.sync_from_filter(self.current_filter)

        rows = self.db.search_elements_advanced(self.current_filter)
        count = len(rows)

        self.chip_bar.set_filter(self.current_filter, count)
        try:
            self.facet_drawer.set_facets(self.db.get_facet_counts(self.current_filter))
        except Exception:
            logger.exception("facet count refresh failed")

        # Design §3.3: the drawer stays collapsed until a filter is active.
        self.facet_drawer.setVisible(active)

        # This is a cross-list search (like load_favorites/load_playlist/
        # load_elements_by_tags), not scoped to whatever list was
        # previously selected, so clear that context the same way those do.
        self.current_list_id = None
        self.current_tag_filter = []
        self.current_elements = rows
        self.pagination.setVisible(False)

        self._update_views_with_elements(rows)
        if rows:
            self.content_stack.setCurrentIndex(1)
        elif active:
            self._show_empty_state("search", query=self.current_filter.get("text") or "current filter")
        else:
            self.content_stack.setCurrentIndex(1)

    def run_text_search(self, text):
        """EP2 Task 12: cross-list, synonym-expanded text search.

        This is a *separate* entry point from `on_search` (the per-list
        live filter below) -- not the plain-text branch of it. `on_search`
        early-returns unless `current_list_id` is set and is the per-list
        browse filter Task 6's regression test
        (`test_clear_filters_after_zero_match_search_stays_in_same_list`)
        depends on staying scoped to the current list. `run_text_search`
        goes through `apply_filter`, which always clears `current_list_id`
        (it is the cross-list search/facet entry point) -- rerouting
        `on_search`'s plain-text path into this one would eject a per-list
        search into the cross-list view on every keystroke and break that
        test. So the two stay separate: `on_search` keeps its existing
        per-list behavior untouched, and this is the cross-list path
        invoked deliberately (directly, not via a live keystroke signal).

        Synonym-expands `text` into `tags_any` as an OR assist alongside
        the literal `text` clause, applies the resulting FilterSpec via
        `apply_filter` (EP2 Task 6), and -- if that yields zero matches --
        shows a `suggest_correction` "did you mean" hint beneath the
        search box (EP2 Task 12).

        Also records the query for the recent-query completer -- this is
        a deliberate, one-shot call site (unlike `on_search`'s per-
        keystroke `textChanged` signal), so no extra debounce is needed
        here; see `_on_search_committed` for the guard `on_search`'s own
        path uses.
        """
        stripped = (text or "").strip()
        if stripped:
            try:
                self.db.add_recent_search(self._current_user_name(), stripped)
            except Exception:
                logger.exception("failed to record recent search for %r", stripped)

        from filter_spec import empty_filter

        spec = empty_filter()
        spec["text"] = text
        # Synonym-expand into tags_any as an OR assist; expansion failures
        # (e.g. a transient DB error) must not block the search itself.
        try:
            spec["tags_any"] = self.db.expand_terms(text)
        except Exception:
            logger.exception("term expansion failed for %r", text)

        self.apply_filter(spec)
        count = self.db.count_elements_advanced(spec)

        if count == 0:
            suggestion = self.db.suggest_correction(text)
            if suggestion:
                self.did_you_mean_label.setText(
                    "Did you mean <b>{}</b>?".format(suggestion))
                self.did_you_mean_label.setVisible(True)
                return
        self.did_you_mean_label.setVisible(False)

    def _on_chip_removed(self, key, value):
        """Strip one clause value from the active filter and re-apply it.

        `key`/`value` come straight off FilterChipBar.chip_removed, typed
        (str/int/bool) to match whatever is stored under that spec key.
        """
        spec = dict(self.current_filter)
        if isinstance(spec.get(key), list):
            spec[key] = [v for v in spec[key] if v != value]
        elif key == "rating_min":
            spec[key] = 0
        elif key == "text":
            spec[key] = ""
        else:
            spec[key] = None
        self.apply_filter(spec)

    def _current_user_name(self):
        """Resolve the acting username the same way main.py derives it
        elsewhere (self.main_window.current_user['username']), falling back
        to 'guest' when there is no main_window or nobody is logged in yet
        (EP2 Task 9: saved-search ownership)."""
        if self.main_window is not None:
            user = getattr(self.main_window, 'current_user', None)
            if user:
                return user.get('username', 'guest')
        return 'guest'

    def _install_recent_completer(self, user_name):
        """EP2 Task 12: seed a QCompleter on the search box from this
        user's recent searches (most-recent-first).

        Called once, from `__init__`, after `setup_ui` has built
        `self.search_box`. A `QCompleter` is a plain, non-modal popup --
        safe on a construction path per the repo's modal-placement rule.
        Works fine with an empty recents list (a brand-new user/db): an
        empty-string-list QCompleter simply never offers a suggestion,
        it does not raise.
        """
        try:
            recents = self.db.get_recent_searches(user_name)
        except Exception:
            logger.exception("failed to load recent searches for %r", user_name)
            recents = []
        completer = QtWidgets.QCompleter(recents, self.search_box)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.search_box.setCompleter(completer)

    def _on_save_search_clicked(self):
        """Prompt for a name and persist the active FilterSpec as a personal
        saved search (EP2 Task 9).

        This only runs from an explicit button click -- never from
        construction or a filter-changed signal path -- so a modal prompt
        here is fine per the repo's modal-placement rule.
        """
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Search", "Name for this saved search:"
        )
        if not ok or not name.strip():
            return
        user_name = self._current_user_name()
        try:
            self.db.create_saved_search(name.strip(), self.current_filter, user_name)
        except Exception:
            logger.exception("Failed to save search %r for user %r", name, user_name)
            return
        # StacksListsPanel owns the Saved Searches list; rather than reach
        # into it directly, just announce that a search was saved and let
        # MainWindow wire this signal to stacks_panel.refresh_saved_searches.
        self.saved_search_created.emit()

    def show_empty_state(self, message=None, hint=None):
        """Clear views and display placeholder message.

        Called with no arguments this is the generic "nothing selected
        yet" state (e.g. main.py's restore_active_view fallback), which
        EP1 renders as the "library" empty page. A custom message/hint
        (the tag-filter prompts in load_elements_by_tags) doesn't map onto
        any of the four fixed EP1 kinds, so it keeps rendering on the
        legacy info_label/hint_label page instead.
        """
        self.current_list_id = None
        self.current_elements = []
        self.current_tag_filter = []
        self.gallery_view.clear()
        self.table_view.setRowCount(0)
        self.pagination.setVisible(False)
        self.info_label.setText(message or "Select a list to view elements")
        self.hint_label.setText(hint or "Browse stacks and lists in the navigation panel")
        if message is None and hint is None:
            self._show_empty_state("library")
        else:
            self._set_empty_page_widget(self.empty_state_widget)



    def load_elements_by_tags(self, tags):
        """Load all elements that match any of the provided tags."""
        cleaned_tags = [t.strip() for t in tags if t and t.strip()]
        if not cleaned_tags:
            self.show_empty_state("Select tags to filter the library", "Choose one or more tags from the Tags Filter panel")
            return

        elements = self.db.search_elements_by_tags(cleaned_tags, match_all=False)
        self.current_list_id = None
        self.current_elements = elements
        self.current_tag_filter = cleaned_tags
        self.pagination.setVisible(False)

        if elements:
            self.content_stack.setCurrentIndex(1)  # Show views
        else:
            self.info_label.setText("No elements found for tags: {}".format(', '.join(cleaned_tags)))
            self.hint_label.setText("Try selecting different tags or add elements with these tags")
            # Route through the legacy page explicitly: a bare
            # setCurrentIndex(0) only flips the outer content_stack index
            # and would leave a previously-installed EP1 empty page (e.g.
            # from a prior search) visible on the nested _empty_page_stack.
            self._set_empty_page_widget(self.empty_state_widget)  # Show empty state

        self._update_views_with_elements(elements)

    def on_search(self, text):
        """Handle search text change (live filter) with tag support and pagination.

        EP2 Task 12: intentionally left as the per-list live filter it
        already was, not rerouted into the cross-list `run_text_search` --
        see `run_text_search`'s docstring for why. Recent-search recording
        for this box lives in `_on_search_committed` (returnPressed),
        deliberately not here, since this method runs on every keystroke.
        """
        if not self.current_list_id:
            return
        
        # Parse search query for tags
        # Supports: #tag, tag:value, or plain text
        text = text.strip()
        tags_to_search = []
        name_search = text
        
        # Check for tag patterns
        if text.startswith('#'):
            # Format: #fire or #fire,explosion
            tags_str = text[1:]  # Remove #
            tags_to_search = [t.strip() for t in tags_str.split(',') if t.strip()]
            name_search = ''
            self.search_hint_label.setText("Filtering by tags: " + ", ".join(tags_to_search))
            self.search_hint_label.show()
        elif 'tag:' in text.lower():
            # Format: tag:fire or tag:fire,explosion
            parts = text.lower().split('tag:', 1)
            if len(parts) > 1:
                tags_str = parts[1]
                tags_to_search = [t.strip() for t in tags_str.split(',') if t.strip()]
                name_search = parts[0].strip()
                self.search_hint_label.setText("Filtering by tags: " + ", ".join(tags_to_search))
                self.search_hint_label.show()
        else:
            self.search_hint_label.hide()
        
        # Get elements
        if tags_to_search:
            # Search by tags first
            elements = self.db.search_elements_by_tags(tags_to_search, match_all=False)
            # Filter by list
            elements = [e for e in elements if e['list_fk'] == self.current_list_id]
            
            # Further filter by name if provided
            if name_search:
                elements = [e for e in elements if name_search.lower() in e['name'].lower()]
        else:
            # Regular name search
            elements = self.db.get_elements_by_list(self.current_list_id)
            if name_search:
                elements = [e for e in elements if name_search.lower() in e['name'].lower()]
        
        # Store filtered elements for pagination
        self.current_elements = elements

        # Setup pagination for filtered results
        if self.config.get('pagination_enabled', True):
            self.pagination.set_total_items(len(elements))
            self.pagination.setVisible(len(elements) > 0)
        else:
            self.pagination.setVisible(False)

        if not elements and text:
            # A real query matched nothing: contextual "no matches" page
            # instead of a blank grid.
            self._update_views_with_elements([])
            self._show_empty_state("search", query=text)
            return

        # A query was cleared or matched something: make sure the views
        # (not a previously-shown search-empty page) are what's visible.
        self.content_stack.setCurrentIndex(1)

        # Display current page
        self._display_current_page()

    def _on_search_committed(self):
        """EP2 Task 12: on an explicit commit (Enter/returnPressed), run the
        cross-list, synonym-expanded text search (`run_text_search`) and let
        it record the query as a recent search.

        Deliberately NOT wired to `search_box.textChanged`/`on_search` --
        that fires on every keystroke, which would run a full cross-list
        search (and record every partial prefix: "f", "fi", "fir", "fire")
        instead of the query the user actually meant. `#tag`/`tag:` queries
        are skipped since those are the tag fast paths handled by `on_search`,
        not the free-text queries the "did you mean"/synonym-expansion/
        recent-completer feature targets.
        """
        text = self.search_box.text().strip()
        if not text or text.startswith('#') or 'tag:' in text.lower():
            return
        self.run_text_search(text)

    def _update_views_with_elements(self, elements):
        """Update gallery and table views with given elements."""
        self.stop_current_gif()
        self._clear_gif_movies()
        self.current_gif_item = None
        self.gallery_view.clear()
        icon_size = self.gallery_view.iconSize()
        self.element_items = {}
        self.element_flags = {}

        for element in elements:
            element_id = element.get('element_id')
            is_favorite = bool(element_id and self.db.is_favorite(element_id))
            is_deprecated = bool(element.get('is_deprecated'))
            if element_id:
                self.element_flags[element_id] = {
                    'favorite': is_favorite,
                    'deprecated': is_deprecated
                }

            item = QtWidgets.QListWidgetItem()
            display_name = element['name']
            if element.get('tags'):
                tag_list = [t.strip() for t in element['tags'].split(',') if t.strip()]
                if tag_list:
                    display_name += " [" + ", ".join(tag_list[:3]) + "]"

            item.setText(display_name)
            item.setData(QtCore.Qt.UserRole, element_id)
            if element_id:
                self.element_items[element_id] = item

            gif_path = self._resolve_path(element.get('gif_preview_path'))
            has_gif = bool(gif_path and element_id and os.path.exists(gif_path))

            if has_gif:
                movie = self.gif_movies.get(element_id)
                if not movie:
                    movie = QtGui.QMovie(gif_path)
                    if movie.isValid():
                        movie.setCacheMode(QtGui.QMovie.CacheAll)
                        movie.frameChanged.connect(lambda frame_num, eid=element_id: self._update_gif_frame(eid))
                        self.gif_movies[element_id] = movie
                    else:
                        movie = None

                if movie and movie.isValid():
                    movie.jumpToFrame(0)
                    pixmap = movie.currentPixmap()
                    if not pixmap.isNull():
                        thumbnail = self._build_fixed_thumbnail(pixmap, icon_size)
                        thumbnail = self._apply_status_badges(thumbnail, element_id, element)
                        item.setIcon(QtGui.QIcon(thumbnail))
                else:
                    has_gif = False

            if not has_gif:
                # Defer decode to the lazy loader; show the type fallback now.
                item.setIcon(self._get_default_icon_for_type(element.get('type'), icon_size))
                item.setData(QtCore.Qt.UserRole + 1, element)

            self.gallery_view.addItem(item)

        self.table_view.setRowCount(len(elements))
        for row, element in enumerate(elements):
            element_id = element.get('element_id')
            flags = self.element_flags.get(element_id, {})

            name_item = QtWidgets.QTableWidgetItem(element['name'])
            if flags.get('favorite'):
                name_item.setIcon(get_icon('favorite', size=16))
            if flags.get('deprecated'):
                name_item.setForeground(QtGui.QColor('#d88400'))
            self.table_view.setItem(row, 0, name_item)

            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element.get('format') or ''))
            
            # Display frame count for sequences (parse frame_range like "1-7" -> "7")
            frame_display = ''
            frame_range = element.get('frame_range')
            if frame_range and '-' in str(frame_range):
                try:
                    parts = str(frame_range).split('-')
                    if len(parts) == 2:
                        start_frame = int(parts[0])
                        end_frame = int(parts[1])
                        frame_count = end_frame - start_frame + 1
                        frame_display = str(frame_count)
                    else:
                        # Malformed range, display as-is
                        frame_display = str(frame_range)
                except (ValueError, IndexError):
                    frame_display = str(frame_range)
            elif frame_range:
                frame_display = str(frame_range)
            
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(frame_display))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element.get('type') or ''))

            size_str = human_size(element['file_size']) if element.get('file_size') else ''
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))

            comment_text = element.get('comment') or ''
            if element.get('tags'):
                comment_text += " [Tags: " + element['tags'] + "]"
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(comment_text))

            rating_item = QtWidgets.QTableWidgetItem(self._rating_cell_text(element.get('rating', 0)))
            rating_item.setFlags(rating_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table_view.setItem(row, 6, rating_item)

            label_item = QtWidgets.QTableWidgetItem("")
            label_item.setFlags(label_item.flags() & ~QtCore.Qt.ItemIsEditable)
            label_fk = element.get('label_fk')
            if label_fk:
                name = self._label_name(label_fk)
                color = self._label_color(label_fk)
                if name:
                    label_item.setToolTip(name)
                    label_item.setData(QtCore.Qt.AccessibleTextRole, name)
                if color:
                    label_item.setBackground(QtGui.QBrush(QtGui.QColor(color)))
            self.table_view.setItem(row, 7, label_item)

            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element_id)

        if hasattr(self.gallery_view, "set_item_loader"):
            self.gallery_view.set_item_loader(self._lazy_load_gallery_item)

        # _update_views_with_elements populates gallery_view directly
        # (bypassing LazyGalleryView.set_elements), so none of that
        # class's own triggers (its set_elements timer, scrollbar
        # valueChanged, resizeEvent) fire on an ordinary list switch.
        # Explicitly kick off an initial visible-load, deferred so the
        # viewport geometry is settled before _load_visible reads item
        # rects (mirrors set_elements's own QTimer.singleShot(0, ...)).
        if hasattr(self.gallery_view, "refresh_visible"):
            QtCore.QTimer.singleShot(0, self.gallery_view.refresh_visible)

    def _lazy_load_gallery_item(self, item):
        """Decode a single gallery item's static preview when it becomes visible."""
        if item is None or item.data(QtCore.Qt.UserRole + 1) is None:
            return
        element = item.data(QtCore.Qt.UserRole + 1)
        icon_size = self.gallery_view.iconSize()
        pixmap = self._load_preview_pixmap(element, icon_size)
        if pixmap:
            item.setIcon(QtGui.QIcon(pixmap))
        # Loaded once — drop the stash so we don't redecode.
        item.setData(QtCore.Qt.UserRole + 1, None)

    def _load_preview_pixmap(self, element, icon_size):
        """Load and scale a static preview pixmap for an element."""
        preview_path = self._resolve_path(element.get('preview_path'))
        if not preview_path or not os.path.exists(preview_path):
            return None

        cached_pixmap = self.preview_cache.get(preview_path)
        if not cached_pixmap:
            cached_pixmap = QtGui.QPixmap(preview_path)
            if not cached_pixmap.isNull():
                self.preview_cache.put(preview_path, cached_pixmap)

        if cached_pixmap and not cached_pixmap.isNull():
            element_id = element.get('element_id')
            thumbnail = self._build_fixed_thumbnail(cached_pixmap, icon_size)
            if element_id:
                thumbnail = self._apply_status_badges(thumbnail, element_id, element)
            return thumbnail
        return None

    def _build_fixed_thumbnail(self, pixmap, size):
        """Center a preview inside a square background for consistent thumbnails."""
        if pixmap is None or pixmap.isNull():
            return QtGui.QPixmap()
        if isinstance(size, QtCore.QSize):
            icon_size = max(size.width(), size.height())
        else:
            icon_size = int(size)
        icon_size = max(1, icon_size)
        canvas = QtGui.QPixmap(icon_size, icon_size)
        canvas.fill(QtGui.QColor('#1d2024'))   # dark card colour, not pure black
        scaled = pixmap.scaled(
            icon_size,
            icon_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        painter = QtGui.QPainter(canvas)
        dx = (icon_size - scaled.width()) // 2
        dy = (icon_size - scaled.height()) // 2
        painter.drawPixmap(dx, dy, scaled)
        painter.end()
        return canvas

    def _get_default_icon_for_type(self, element_type, icon_size):
        """Return a fallback icon when no preview is available."""
        # Render the SVG at the actual display size so Qt never up-scales a
        # small raster — that was the root cause of the pixelation.
        if isinstance(icon_size, QtCore.QSize):
            req_size = max(icon_size.width(), icon_size.height())
        else:
            req_size = int(icon_size)
        req_size = max(req_size, 24)

        normalized_type = (element_type or '').strip().lower()
        if normalized_type == '2d':
            icon = get_icon('film', size=req_size)
            if icon.isNull():
                icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            return self._icon_to_square(icon, icon_size)
        if normalized_type == '3d':
            icon = get_icon('cube', size=req_size)
            if icon.isNull():
                icon = self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon)
            return self._icon_to_square(icon, icon_size)
        if normalized_type == 'toolset':
            icon = get_icon('nuke', size=req_size)
            if icon.isNull():
                icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView)
            return self._icon_to_square(icon, icon_size)
        return self._icon_to_square(
            self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView), icon_size
        )

    def _icon_to_square(self, icon, size):
        """Render an icon as a square thumbnail using the existing helper."""
        if not icon or icon.isNull():
            return QtGui.QIcon()
        # Always request the pixmap at the exact display dimensions so SVG
        # icons are rasterised at the right resolution, avoiding up-scaling.
        if isinstance(size, QtCore.QSize):
            w, h = size.width(), size.height()
        else:
            w = h = int(size)
        pixmap = icon.pixmap(w, h)
        if pixmap.isNull():
            return QtGui.QIcon()
        thumbnail = self._build_fixed_thumbnail(pixmap, size)
        return QtGui.QIcon(thumbnail)

    def _apply_status_badges(self, pixmap, element_id, element=None):
        """Overlay favorite/deprecated badges onto a pixmap."""
        # EP1: overlay rating stars + label chip first so every return path
        # below (no flags / no overlays / flags present) carries it.
        pixmap = self._draw_curation_badges(pixmap, element_id, element)

        flags = self.element_flags.get(element_id)
        if not flags:
            return pixmap

        overlays = []
        if flags.get('favorite'):
            overlays.append(get_pixmap('favorite', size=18))
        if flags.get('deprecated'):
            overlays.append(get_pixmap('deprecated', size=18))

        overlays = [ov for ov in overlays if ov and not ov.isNull()]
        if not overlays:
            return pixmap

        result = QtGui.QPixmap(pixmap)
        painter = QtGui.QPainter(result)
        margin = 6
        offset = margin
        for overlay in overlays:
            badge = overlay.scaled(
                18,
                18,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            painter.drawPixmap(offset, margin, badge)
            offset += badge.width() + 4
        painter.end()

        return result

    def _draw_curation_badges(self, pixmap, element_id, element=None):
        """Overlay a star strip and a label color-chip onto a thumbnail."""
        result = QtGui.QPixmap(pixmap)
        if element_id is None:
            return result
        if element is not None:
            el = element
        else:
            try:
                el = self.db.get_element_by_id(element_id) or {}
            except Exception:
                logger.exception("failed reading curation state for %s", element_id)
                return result
        rating = el.get("rating", 0) or 0
        label_fk = el.get("label_fk")

        painter = QtGui.QPainter(result)
        try:
            # star strip, bottom-left
            if rating:
                painter.setPen(QtGui.QColor("#F5D90A"))
                painter.drawText(6, result.height() - 6, "★" * int(rating))
            # label chip, top-right
            if label_fk:
                color = self._label_color(label_fk)
                if color:
                    painter.fillRect(result.width() - 16, 6, 10, 10, QtGui.QColor(color))
        finally:
            painter.end()
        return result

    def _label_lookup(self):
        """Lazily build (and cache) a label_id -> label-dict map.

        Shared by `_label_color` and `_label_name` so both resolve from a
        single `get_labels()` round-trip; `quick_set_label` invalidates this
        same `_label_color_cache` attribute to force a re-resolve.
        """
        cache = getattr(self, "_label_color_cache", None)
        if cache is None:
            cache = {l["label_id"]: l for l in self.db.get_labels()}
            self._label_color_cache = cache
        return cache

    def _label_color(self, label_fk):
        """Resolve a label_fk to its color_hex (cached per refresh)."""
        label = self._label_lookup().get(label_fk)
        return label["color_hex"] if label else None

    def _label_name(self, label_fk):
        """Resolve a label_fk to its display name (cached per refresh)."""
        label = self._label_lookup().get(label_fk)
        return label["name"] if label else None

    @staticmethod
    def _rating_cell_text(rating):
        """Render a rating (0-5, possibly None) as a star string for the table."""
        return "★" * int(rating or 0)

    def quick_set_rating(self, element_id, stars):
        """Write-through rating setter for the grid's hover quick-edit."""
        self.db.set_element_rating(element_id, stars)
        self._refresh_item(element_id)

    def quick_set_label(self, element_id, label_id):
        """Write-through label setter for the grid's hover quick-edit."""
        self.db.set_element_label(element_id, label_id)
        self._label_color_cache = None  # force re-resolve
        self._refresh_item(element_id)

    def _refresh_item(self, element_id):
        """Repaint a single gallery item's icon after a rating/label change.

        Minimal per-item update modeled on on_preview_ready; deliberately a
        no-op when the element has no current gallery item and never
        triggers a full view rebuild (see SP2 in-place-update work).
        """
        item = self.element_items.get(element_id)
        if item is None:
            return
        try:
            element = self.db.get_element_by_id(element_id)
        except Exception:
            logger.exception("failed refreshing item %s", element_id)
            return
        if not element:
            return
        icon_size = self.gallery_view.iconSize()
        element_stub = dict(element)
        element_stub["element_id"] = element_id
        pixmap = self._load_preview_pixmap(element_stub, icon_size)
        if pixmap:
            item.setIcon(QtGui.QIcon(pixmap))

    @QtCore.Slot(int, str, str)
    def on_preview_ready(self, element_id, preview_path, preview_type):
        """Slot connected to PreviewWorker.preview_ready.

        Updates the gallery icon for *element_id* when a new thumbnail has
        been generated by the background preview worker.  Only 'thumbnail'
        type triggers an icon update; other types (gif, video) are ignored
        at this level.
        """
        if preview_type != "thumbnail":
            return
        item = self.element_items.get(element_id)
        if item is None:
            return
        if not preview_path or not os.path.exists(preview_path):
            return
        try:
            element = self.db.get_element_by_id(element_id)
        except Exception:
            logger.exception("failed loading element %s for preview refresh", element_id)
            return
        if not element:
            return
        icon_size = self.gallery_view.iconSize()
        element_stub = dict(element)
        element_stub["element_id"] = element_id
        element_stub["preview_path"] = preview_path
        pixmap = self._load_preview_pixmap(element_stub, icon_size)
        if pixmap:
            item.setIcon(QtGui.QIcon(pixmap))

    def on_item_clicked(self, item):
        """Handle gallery item click."""
        element_id = item.data(QtCore.Qt.UserRole)
        self.element_selected.emit(element_id)
    
    def on_item_double_clicked(self, item):
        """Handle gallery item double-click."""
        element_id = item.data(QtCore.Qt.UserRole)
        self.element_double_clicked.emit(element_id)
    
    def on_table_item_clicked(self, item):
        """Handle table item click."""
        element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
        self.element_selected.emit(element_id)
    
    def on_table_item_double_clicked(self, item):
        """Handle table item double-click."""
        element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
        self.element_double_clicked.emit(element_id)
    
    def eventFilter(self, watched, event):
        """Event filter to handle Alt+Hover."""
        # Check if widgets are initialized
        if not hasattr(self, 'gallery_view') or not hasattr(self, 'table_view'):
            return super(MediaDisplayWidget, self).eventFilter(watched, event)
        
        if watched in [self.gallery_view.viewport(), self.table_view.viewport()]:
            if event.type() == QtCore.QEvent.MouseMove:
                # Check if Alt is pressed
                modifiers = QtWidgets.QApplication.keyboardModifiers()
                self.alt_pressed = (modifiers & QtCore.Qt.AltModifier)
                
                if self.alt_pressed:
                    # Get item under cursor
                    if isinstance(watched, QtWidgets.QWidget):
                        pos = watched.mapFromGlobal(QtGui.QCursor.pos())
                    else:
                        pos = QtCore.QPoint()
                    
                    if watched == self.gallery_view.viewport():
                        item = self.gallery_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_row = -1
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                    elif watched == self.table_view.viewport():
                        item = self.table_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_row = item.row() if hasattr(item, 'row') else -1
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                else:
                    # Hide popup if Alt released
                    if self.media_popup.isVisible():
                        self.media_popup.hide()
                    self.hover_timer.stop()
                    self.hover_item = None
                    self.hover_row = -1
                    
                # Handle GIF preview on hover (without Alt key)
                if not self.alt_pressed and watched == self.gallery_view.viewport():
                    if isinstance(watched, QtWidgets.QWidget):
                        pos = watched.mapFromGlobal(QtGui.QCursor.pos())
                    else:
                        pos = QtCore.QPoint()
                    item = self.gallery_view.itemAt(pos)
                    
                    if item and item is not self.current_gif_item:
                        # Stop previous GIF
                        self.stop_current_gif()
                        
                        # Start new GIF if available
                        element_id = item.data(QtCore.Qt.UserRole)
                        if element_id:
                            self.play_gif_for_item(item, element_id)
                            self.current_gif_item = item
                            self.hover_row = -1
                    elif not item and self.current_gif_item:
                        # Mouse left all items, stop GIF
                        self.stop_current_gif()
                        self.current_gif_item = None
                        self.hover_row = -1
            
            elif event.type() == QtCore.QEvent.Leave:
                # Hide popup when leaving widget
                self.hover_timer.stop()
                self.hover_item = None
                self.hover_row = -1
                
                # Stop GIF playback
                self.stop_current_gif()
                self.current_gif_item = None
        
        return super(MediaDisplayWidget, self).eventFilter(watched, event)
    
    def play_gif_for_item(self, item, element_id):
        """
        Play animated GIF for gallery item on hover (Ulaavi pattern).
        
        Args:
            item (QListWidgetItem): Gallery item
            element_id (int): Element ID
        """
        # Get pre-loaded movie from cache
        if element_id not in self.gif_movies:
            return
        
        movie = self.gif_movies[element_id]
        
        # Jump to first frame and start playback
        movie.jumpToFrame(0)
        movie.start()
    
    def _update_gif_frame(self, element_id):
        """Update the gallery icon with the current GIF frame."""
        if element_id not in self.gif_movies:
            return
        movie = self.gif_movies.get(element_id)
        item = self.element_items.get(element_id)
        if not movie or not item:
            return

        try:
            _ = item.data(QtCore.Qt.UserRole)
        except RuntimeError:
            movie.stop()
            return

        pixmap = movie.currentPixmap()
        if pixmap.isNull():
            return

        icon_size = self.gallery_view.iconSize()
        thumbnail = self._build_fixed_thumbnail(pixmap, icon_size)
        thumbnail = self._apply_status_badges(thumbnail, element_id)

        try:
            item.setIcon(QtGui.QIcon(thumbnail))
        except RuntimeError:
            movie.stop()
    
    def stop_current_gif(self):
        """Stop currently playing GIF and return to static first frame (Ulaavi pattern)."""
        if self.current_gif_item:
            element_id = self.current_gif_item.data(QtCore.Qt.UserRole)
            
            # Stop movie and jump to first frame
            if element_id and element_id in self.gif_movies:
                movie = self.gif_movies[element_id]
                movie.stop()
                movie.jumpToFrame(0)
                # Update icon to show first frame
                self._update_gif_frame(element_id)

    def _clear_gif_movies(self):
        """Stop, disconnect, and clear cached QMovie instances."""
        for movie in self.gif_movies.values():
            try:
                movie.stop()
                movie.frameChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.gif_movies.clear()
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == QtCore.Qt.Key_Alt:
            self.alt_pressed = True
        super(MediaDisplayWidget, self).keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """Handle key release events."""
        if event.key() == QtCore.Qt.Key_Alt:
            self.alt_pressed = False
            if self.media_popup.isVisible():
                self.media_popup.hide()
            self.hover_timer.stop()
        super(MediaDisplayWidget, self).keyReleaseEvent(event)
    
    def show_info_popup(self):
        """Show media info popup for hovered item."""
        if not self.hover_item or not self.alt_pressed:
            return
        
        # Get element ID from item
        element_id = None
        
        if self.view_mode == 'gallery':
            element_id = self.hover_item.data(QtCore.Qt.UserRole)
        else:  # list view
            row = self.hover_row if self.hover_row >= 0 else -1
            if row >= 0:
                table_item = self.table_view.item(row, 0)
                if table_item:
                    element_id = table_item.data(QtCore.Qt.UserRole)
        
        if element_id:
            element_data = self.db.get_element_by_id(element_id)
            if element_data:
                element_data = self._prepare_element_for_popup(element_data)
                # Get global cursor position
                cursor_pos = QtGui.QCursor.pos()
                self.media_popup.show_element(element_data, cursor_pos)
    
    def on_popup_insert(self, element_id):
        """Handle insert request from popup - insert element into Nuke."""
        self.gallery_view.insert_to_nuke([element_id])
        self.element_double_clicked.emit(element_id)
    
    def on_popup_reveal(self, filepath):
        """Handle reveal request from popup."""
        filepath = self._resolve_path(filepath)
        if filepath and os.path.exists(filepath):
            # Reveal in file explorer
            import subprocess
            import platform
            
            # Get directory path
            if os.path.isfile(filepath):
                directory = os.path.dirname(filepath)
            else:
                directory = filepath
            
            # Open in OS file explorer
            if platform.system() == 'Windows':
                subprocess.Popen(['explorer', '/select,', os.path.normpath(filepath)])
            elif platform.system() == 'Darwin':  # macOS
                subprocess.Popen(['open', '-R', filepath])
            else:  # Linux
                subprocess.Popen(['xdg-open', directory])

    def _resolve_path(self, path):
        """Convert stored relative paths to absolute paths rooted at the project."""
        return resolve_path(path, project_root=self._project_root)

    def _prepare_element_for_popup(self, element_data):
        """Return a copy of element data with absolute filesystem paths."""
        element_copy = dict(element_data)
        for key in ('preview_path', 'gif_preview_path', 'filepath_soft', 'filepath_hard', 'geometry_preview_path'):
            original = element_copy.get(key)
            resolved = self._resolve_path(original)
            if resolved:
                element_copy[key] = resolved
        return element_copy
    
    def _is_admin_user(self):
        """Return True if the owning MainWindow reports an admin session.

        The widget's Qt parent is the central QSplitter (main.py), which has no
        'is_admin' attribute; permission state lives on MainWindow, injected as
        self.main_window at construction. (Fixes audit issue M3.)
        """
        return bool(getattr(self.main_window, 'is_admin', False))

    def show_context_menu(self, position, element_id):
        """
        Show context menu for element(s).
        Supports both single and bulk operations.

        Args:
            position (QPoint): Position to show menu
            element_id (int): Element ID (for single selection)
        """
        # Get all selected element IDs
        selected_ids = self.get_selected_element_ids()

        menu = QtWidgets.QMenu(self)
        is_admin = self._is_admin_user()
        
        # If multiple items selected, show bulk operations menu
        if len(selected_ids) > 1:
            actions = self._populate_bulk_menu(menu, selected_ids, is_admin, with_header=True)
            action = menu.exec_(position)
            self._dispatch_bulk_action(action, actions, selected_ids)

        else:
            # Single item context menu (existing behavior)
            # Check if already favorited
            is_fav = self.db.is_favorite(
                element_id,
                self.config.get('user_name'),
                self.config.get('machine_name')
            )
            
            # Add/Remove favorite action
            if is_fav:
                fav_action = menu.addAction(get_icon('favorite', size=16), "Remove from Favorites")
            else:
                fav_action = menu.addAction(get_icon('favorite', size=16), "Add to Favorites")
            
            # Add to playlist action
            add_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add to Playlist...")
            
            menu.addSeparator()

            insert_action = None
            if self.nuke_bridge and hasattr(self.nuke_bridge, 'is_available') and self.nuke_bridge.is_available():
                insert_action = menu.addAction("Insert into Nuke")
                menu.addSeparator()

            # Edit metadata action
            edit_action = menu.addAction(get_icon('edit', size=16), "Edit Metadata...")
            
            menu.addSeparator()
            
            # Get element to check deprecated status
            element = self.db.get_element_by_id(element_id)
            
            # Toggle deprecated action
            if element and element.get('is_deprecated'):
                deprecated_action = menu.addAction(get_icon('deprecated', size=16), "Unmark as Deprecated")
            else:
                deprecated_action = menu.addAction(get_icon('deprecated', size=16), "Mark as Deprecated")

            # Delete action
            delete_action = menu.addAction(get_icon('delete', size=16), "Delete Element")

            # Execute menu
            action = menu.exec_(position)
            
            if action == fav_action:
                self.toggle_favorite(element_id)
            elif action == add_playlist_action:
                self.add_to_playlist(element_id)
            elif insert_action and action == insert_action:
                self.element_double_clicked.emit(element_id)
            elif action == edit_action:
                self.edit_element(element_id)
            elif action == deprecated_action:
                self.toggle_deprecated(element_id)
            elif action == delete_action:
                self.delete_element(element_id)
    
    def add_to_playlist(self, element_id):
        """Show dialog to add element to playlist."""
        dialog = AddToPlaylistDialog(self.db, element_id, self)
        dialog.exec_()
    
    def toggle_favorite(self, element_id):
        """Toggle favorite status of element."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')
        
        is_fav = self.db.is_favorite(element_id, user, machine)
        
        if is_fav:
            self.db.remove_favorite(element_id, user, machine)
        else:
            self.db.add_favorite(element_id, user, machine)
        
        # Refresh display to update star icons
        if self.current_list_id:
            self.load_elements(self.current_list_id)
    
    def edit_element(self, element_id):
        """Show edit element dialog."""
        try:
            dialog = EditElementDialog(self.db, element_id, self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                # Refresh display
                if self.current_list_id:
                    self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to open edit dialog: {}".format(str(e)))
    
    def toggle_deprecated(self, element_id):
        """Toggle deprecated status of element."""
        try:
            element = self.db.get_element_by_id(element_id)
            if not element:
                return
            
            # Toggle deprecated status
            new_status = 0 if element.get('is_deprecated') else 1
            self.db.update_element(element_id, is_deprecated=new_status)
            
            status_text = "deprecated" if new_status else "active"
            QtWidgets.QMessageBox.information(self, "Success", "Element marked as {}.".format(status_text))
            
            # Refresh display
            if self.current_list_id:
                self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to update element: {}".format(str(e)))
    
    def delete_element(self, element_id):
        """Delete element after confirmation (admin only)."""
        # Check admin permission
        if self.main_window and not self.main_window.check_admin_permission("delete elements"):
            return
        
        try:
            element = self.db.get_element_by_id(element_id)
            if not element:
                return
            
            # Confirmation dialog
            reply = QtWidgets.QMessageBox.question(
                self,
                "Confirm Deletion",
                "Are you sure you want to delete '{}'?\n\nThis action cannot be undone.".format(element['name']),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                removal_errors = []
                preview_keys = ('preview_path', 'gif_preview_path', 'video_preview_path', 'geometry_preview_path')
                for key in preview_keys:
                    resolved_path = self._resolve_path(element.get(key))
                    if resolved_path and os.path.exists(resolved_path):
                        try:
                            os.remove(resolved_path)
                            self.preview_cache.remove(resolved_path)
                        except OSError as err:
                            removal_errors.append((resolved_path, str(err)))

                # Delete from database
                deleted = self.db.delete_element(element_id)

                if not deleted:
                    QtWidgets.QMessageBox.warning(self, "Delete Failed", "Element could not be removed from the database.")
                    return

                if removal_errors:
                    error_lines = ["{}: {}".format(path, message) for path, message in removal_errors]
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Partial Cleanup",
                        "Element removed, but some preview files could not be deleted:\n\n{}".format("\n".join(error_lines))
                    )
                else:
                    QtWidgets.QMessageBox.information(self, "Success", "Element deleted successfully.")
                
                # Refresh display
                if self.current_list_id:
                    self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete element: {}".format(str(e)))
    
    def _populate_bulk_menu(self, menu, selected_ids, is_admin, with_header):
        """Add the shared bulk-operation actions to `menu`; return {name: QAction}."""
        if with_header:
            header_label = QtWidgets.QLabel("  {} items selected  ".format(len(selected_ids)))
            header_label.setStyleSheet("font-weight: bold; color: #16c6b0; padding: 5px;")
            header_action = QtWidgets.QWidgetAction(self)
            header_action.setDefaultWidget(header_label)
            menu.addAction(header_action)
            menu.addSeparator()

        actions = {}
        actions['fav'] = menu.addAction(get_icon('favorite', size=16), "Add All to Favorites")
        actions['playlist'] = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")
        actions['tag'] = menu.addAction(get_icon('add', size=16), "Add Tag to All...")
        actions['edit'] = menu.addAction(get_icon('edit', size=16), "Batch Edit Metadata...")

        menu.addSeparator()

        actions['deprecate'] = menu.addAction(get_icon('deprecated', size=16), "Mark All as Deprecated")
        actions['delete'] = menu.addAction(get_icon('delete', size=16), "Delete All Selected")
        if not is_admin:
            actions['deprecate'].setEnabled(False)
            actions['delete'].setEnabled(False)
        return actions

    def _dispatch_bulk_action(self, action, actions, selected_ids):
        """Route a chosen bulk QAction to its handler."""
        if action == actions['fav']:
            self.bulk_add_to_favorites(selected_ids)
        elif action == actions['playlist']:
            self.bulk_add_to_playlist(selected_ids)
        elif action == actions['tag']:
            self.bulk_add_tag(selected_ids)
        elif action == actions['edit']:
            self.open_batch_edit(selected_ids)
        elif action == actions['deprecate']:
            self.bulk_mark_deprecated(selected_ids)
        elif action == actions['delete']:
            self.bulk_delete(selected_ids)

    def show_bulk_menu(self):
        """Show bulk operations menu."""
        # Get selected elements
        selected_ids = self.get_selected_element_ids()

        if not selected_ids:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select one or more elements.\n\nTip: Hold Ctrl/Cmd to select multiple items.")
            return

        # Create menu
        menu = QtWidgets.QMenu(self)
        # is_admin=True reproduces this menu's prior behavior: unlike the context
        # menu, it never disabled the destructive actions.
        actions = self._populate_bulk_menu(menu, selected_ids, is_admin=True, with_header=False)
        action = menu.exec_(QtGui.QCursor.pos())
        self._dispatch_bulk_action(action, actions, selected_ids)

    def open_batch_edit(self, element_ids=None):
        """Open batch metadata editor for selected elements."""
        if element_ids is None:
            element_ids = self.get_selected_element_ids()

        if len(element_ids) < 2:
            QtWidgets.QMessageBox.information(
                self,
                "No Selection",
                "Please select at least two elements for batch edit."
            )
            return

        try:
            from src.ui.batch_edit_dialog import BatchEditDialog

            dialog = BatchEditDialog(element_ids, self.db, self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                if self.current_list_id:
                    self.load_elements(self.current_list_id)
                elif self.current_elements is not None:
                    self._update_views_with_elements(self.current_elements)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to open batch edit dialog: {}".format(str(e)))
    
    def get_selected_element_ids(self):
        """Get list of selected element IDs from current view."""
        selected_ids = []
        
        if self.view_mode == 'gallery':
            for item in self.gallery_view.selectedItems():
                element_id = item.data(QtCore.Qt.UserRole)
                if element_id:
                    selected_ids.append(element_id)
        else:  # list view
            for item in self.table_view.selectedItems():
                # Only get from first column to avoid duplicates
                if item.column() == 0:
                    element_id = item.data(QtCore.Qt.UserRole)
                    if element_id:
                        selected_ids.append(element_id)
        
        return selected_ids
    
    def bulk_add_to_favorites(self, element_ids):
        """Add multiple elements to favorites."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')
        
        added_count = 0
        for element_id in element_ids:
            if not self.db.is_favorite(element_id, user, machine):
                self.db.add_favorite(element_id, user, machine)
                added_count += 1
        
        QtWidgets.QMessageBox.information(
            self,
            "Success",
            "Added {} element(s) to favorites.".format(added_count)
        )
        
        # Refresh display
        if self.current_list_id:
            self.load_elements(self.current_list_id)
    
    def bulk_add_to_playlist(self, element_ids):
        """Add multiple elements to a playlist."""
        # Get all playlists
        playlists = self.db.get_all_playlists()
        
        if not playlists:
            QtWidgets.QMessageBox.warning(self, "No Playlists", "No playlists available. Create one first.")
            return
        
        # Simple selection dialog
        playlist_names = [p['name'] for p in playlists]
        playlist_name, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Select Playlist",
            "Choose playlist to add {} element(s) to:".format(len(element_ids)),
            playlist_names,
            0,
            False
        )
        
        if ok and playlist_name:
            # Find playlist ID
            playlist_id = None
            for p in playlists:
                if p['name'] == playlist_name:
                    playlist_id = p['playlist_id']
                    break
            
            if playlist_id:
                added_count = 0
                for element_id in element_ids:
                    result = self.db.add_element_to_playlist(playlist_id, element_id)
                    if result is not None:
                        added_count += 1
                
                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    "Added {} element(s) to playlist '{}'.".format(added_count, playlist_name)
                )
    
    def bulk_mark_deprecated(self, element_ids):
        """Mark multiple elements as deprecated."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Bulk Operation",
            "Mark {} element(s) as deprecated?".format(len(element_ids)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            for element_id in element_ids:
                self.db.update_element(element_id, is_deprecated=1)
            
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Marked {} element(s) as deprecated.".format(len(element_ids))
            )
            
            # Refresh display
            if self.current_list_id:
                self.load_elements(self.current_list_id)
    
    def bulk_delete(self, element_ids):
        """Delete multiple elements."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Bulk Deletion",
            "Are you sure you want to delete {} element(s)?\n\nThis action cannot be undone.".format(len(element_ids)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            for element_id in element_ids:
                self.db.delete_element(element_id)
            
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Deleted {} element(s).".format(len(element_ids))
            )
            
            # Refresh display
            if self.current_list_id:
                self.load_elements(self.current_list_id)

    def bulk_add_tag(self, element_ids):
        """Prompt once for a tag, then append it to every selected element.

        Tags are a per-element comma-separated string (the same `tags`
        field EditElementDialog writes via db.update_element(..., tags=...));
        there is no shared "bulk_set_tag" DB method, so each element is
        read, updated, and written back individually -- modeled on the
        neighbouring bulk_add_to_favorites/bulk_mark_deprecated methods.
        """
        if not element_ids:
            return

        tag, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add Tag to All",
            "Tag to add to {} element(s):".format(len(element_ids))
        )
        tag = tag.strip() if (ok and tag) else ""
        if not ok or not tag:
            return

        updated_count = 0
        for element_id in element_ids:
            element = self.db.get_element_by_id(element_id)
            if not element:
                continue
            existing = [t.strip() for t in (element.get('tags') or '').split(',') if t.strip()]
            if tag in existing:
                continue
            existing.append(tag)
            self.db.update_element(element_id, tags=', '.join(existing))
            updated_count += 1

        QtWidgets.QMessageBox.information(
            self,
            "Success",
            "Added tag '{}' to {} element(s).".format(tag, updated_count)
        )

        # Refresh display
        if self.current_list_id:
            self.load_elements(self.current_list_id)

    def refresh_current_view(self):
        """Re-render whatever's currently on screen.

        Used after a bulk rating/label change: MultiSelectActionTray's
        apply_rating/apply_label already write straight to the DB before
        emitting rate_requested/label_requested, so this just needs to
        make the (now stale) rating/label badges on screen catch up.
        """
        if self.current_list_id:
            self.load_elements(self.current_list_id)
        elif self.current_tag_filter:
            self.load_elements_by_tags(self.current_tag_filter)
        elif self.current_elements:
            # Favorites / playlist views: current_list_id/current_tag_filter
            # are both unset, so re-pull each element directly for fresh
            # rating/label values instead of a full reload.
            ids = [e.get('element_id') for e in self.current_elements if e.get('element_id')]
            refreshed = [self.db.get_element_by_id(eid) for eid in ids]
            self.current_elements = [e for e in refreshed if e]
            self._update_views_with_elements(self.current_elements)

    def _on_selection_changed_ep1(self):
        """Feed the multi-select action tray from either view's selection."""
        self.action_tray.set_selection(self.get_selected_element_ids())

    def _show_empty_state(self, kind_key, query=None, list_name=None):
        """Install one of the four EP1 context-aware empty pages.

        kind_key is one of "library" / "list" / "search" / "favorites".
        """
        from ui.empty_state_widget import EmptyStateWidget

        specs = {
            "library": (
                "No assets yet",
                "Ingest footage, sequences, or toolsets to get started.",
                ("Ingest files…", self._request_ingest_files),
                None,
                "action",
            ),
            "list": (
                "This list is empty",
                "Add assets to {}.".format(list_name or "this list"),
                ("Ingest into this list…", self._request_ingest_files),
                None,
                "action",
            ),
            "search": (
                "No matches for '{}'".format(query or ""),
                "Try fewer terms or clear filters.",
                ("Clear filters", self._request_clear_filters),
                None,
                "informational",
            ),
            "favorites": (
                "Nothing here yet",
                "Star assets or add them to a playlist to collect them.",
                ("Browse library", self._request_browse_library),
                None,
                "informational",
            ),
        }
        headline, message, primary, secondary, kind = specs[kind_key]
        self.current_empty_state = EmptyStateWidget(headline, message, primary, secondary, kind)
        self._set_empty_page_widget(self.current_empty_state)

    def _set_empty_page_widget(self, widget):
        """Swap the widget shown on content_stack's empty page (index 0).

        The legacy self.empty_state_widget (and its info_label/hint_label
        children) stays registered as a permanent page of the nested
        _empty_page_stack, so pre-existing direct writers (this widget's
        own show_empty_state/load_elements, and main.py:599-601) keep
        working without AttributeError -- their text just stops being
        what's on screen once an EP1 empty state replaces it as the
        visible page. Previously-installed EP1 pages (but never the
        legacy one) are dropped so repeated calls don't accumulate.
        """
        previous = self._empty_page_stack.currentWidget()
        if self._empty_page_stack.indexOf(widget) == -1:
            self._empty_page_stack.addWidget(widget)
        self._empty_page_stack.setCurrentWidget(widget)
        if (previous is not None and previous is not widget
                and previous is not self.empty_state_widget):
            self._empty_page_stack.removeWidget(previous)
            previous.deleteLater()
        self.content_stack.setCurrentIndex(0)

    def _request_ingest_files(self):
        """Empty-state 'Ingest files…' CTA -> MainWindow.ingest_files()."""
        if self.main_window and hasattr(self.main_window, 'ingest_files'):
            self.main_window.ingest_files()
        else:
            logger.info("Ingest requested from empty state but no MainWindow.ingest_files() is available")

    def _request_clear_filters(self):
        """Empty-state 'Clear filters' CTA.

        Reached from two different zero-result callers that share the same
        "search" empty page (_show_empty_state's "search" entry), and they
        need different recoveries:

        (b) Per-list browse search: on_search() only acts "if
            self.current_list_id:" and never clears that attribute itself,
            so a zero-match search leaves current_list_id still set to the
            list the user was browsing. Recovery must reset the search/
            filter state and reload that SAME list -- not eject the user
            into the unscoped cross-list view.
        (a) Facet/chip filter: apply_filter() unconditionally sets
            current_list_id = None (it's the cross-list search entry
            point -- same as load_favorites/load_playlist/
            load_elements_by_tags), so by the time this CTA is reachable
            through that path current_list_id is already None. Recovery
            here is the unfiltered cross-list view apply_filter(empty_filter())
            produces.

        Fix pass 2: the prior fix pass (39f0dd6) always ran
        apply_filter(empty_filter()) here regardless of which caller reached
        it. Since apply_filter always nulls current_list_id, that silently
        ejected a per-list search (b) user out of the list they were
        browsing into the cross-list view -- a real navigation regression on
        a path that worked before 39f0dd6. Branching on current_list_id
        restores case (b) while keeping case (a) exactly as 39f0dd6 fixed it.
        """
        from filter_spec import empty_filter

        if self.current_list_id is not None:
            # Case (b): reset the filter spec and reconcile the drawer/chip
            # bar to it so no facet selection or chip lingers into the
            # reload below -- this can be reached with a still-armed facet
            # filter underneath an in-list search (apply_filter never
            # touches current_list_id, and load_elements never touches
            # current_filter/facet_drawer/chip_bar, so the two can go out of
            # sync across a list switch). sync_from_filter() never emits
            # filter_changed (see its docstring / Fix 1 above), so this
            # cannot re-enter apply_filter through that connection.
            self.current_filter = empty_filter()
            self.facet_drawer.sync_from_filter(self.current_filter)
            self.facet_drawer.setVisible(False)

            # Clear the search box with signals blocked so on_search() does
            # not also fire and repaint redundantly -- load_elements() below
            # is the single reload this branch performs.
            self.search_box.blockSignals(True)
            try:
                self.search_box.clear()
            finally:
                self.search_box.blockSignals(False)
            self.search_hint_label.hide()

            # Reload the SAME list the user was browsing. current_list_id is
            # deliberately left untouched here (load_elements reassigns it
            # to the same value anyway) -- this is the one call in this
            # branch that repaints, so there is no double-load.
            self.load_elements(self.current_list_id)

            # Bring the chip bar's result count back in sync with the
            # reloaded list now that current_elements reflects it (set_filter
            # above would have shown a stale "0 results" until this).
            self.chip_bar.set_filter(self.current_filter, len(self.current_elements))
            return

        # Case (a): current_list_id is already None here, so this is exactly
        # 39f0dd6's fix, unchanged.
        self.search_box.blockSignals(True)
        try:
            self.search_box.clear()
        finally:
            self.search_box.blockSignals(False)

        self.apply_filter(empty_filter())

    def _request_browse_library(self):
        """Empty-state 'Browse library' CTA.

        No MainWindow handler exists today for "show the whole library"
        (only per-list/per-stack/favorites/playlist/tag navigation), so
        this is a logged no-op rather than inventing new navigation.
        """
        logger.info("Browse library requested from empty state; no whole-library navigation exists yet")

    def load_favorites(self):
        """Load and display favorite elements."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')

        favorites = self.db.get_favorites(user, machine)

        self.current_list_id = None  # Clear current list
        self.current_tag_filter = []
        self.current_elements = favorites
        self.pagination.setVisible(False)
        if favorites:
            self.content_stack.setCurrentIndex(1)
            self.info_label.setText("Favorites ({} items)".format(len(favorites)))
            self._update_views_with_elements(favorites)
        else:
            self._show_empty_state("favorites")
    
    def load_playlist(self, playlist_id):
        """Load and display playlist elements."""
        playlist = self.db.get_playlist_by_id(playlist_id)
        if not playlist:
            return
        
        elements = self.db.get_playlist_elements(playlist_id)
        
        self.current_list_id = None  # Clear current list
        self.current_tag_filter = []
        self.current_elements = elements
        self.pagination.setVisible(False)
        self.info_label.setText("Playlist: {} ({} items)".format(playlist['name'], len(elements)))
        self._update_views_with_elements(elements)
    
    def contextMenuEvent(self, event):
        """Handle context menu request."""
        # Get item under cursor
        if self.view_mode == 'gallery':
            item = self.gallery_view.itemAt(self.gallery_view.viewport().mapFromGlobal(event.globalPos()))
            if item:
                element_id = item.data(QtCore.Qt.UserRole)
                self.show_context_menu(event.globalPos(), element_id)
        else:
            item = self.table_view.itemAt(self.table_view.viewport().mapFromGlobal(event.globalPos()))
            if item:
                element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
                self.show_context_menu(event.globalPos(), element_id)


