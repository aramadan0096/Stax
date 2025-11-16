# -*- coding: utf-8 -*-
"""
Media Display Widget with Gallery/List Views
"""

import os
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon, get_pixmap
from src.preview_cache import get_preview_cache
from src.ui.media_info_popup import MediaInfoPopup
from src.ui.drag_gallery_view import DragGalleryView
from src.ui.pagination_widget import PaginationWidget


class MediaDisplayWidget(QtWidgets.QWidget):
    """Central widget for displaying media elements."""
    
    # Signals
    element_selected = QtCore.Signal(int)  # element_id
    element_double_clicked = QtCore.Signal(int)  # element_id
    
    def __init__(self, db_manager, config, nuke_bridge, main_window=None, parent=None):
        super(MediaDisplayWidget, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.nuke_bridge = nuke_bridge
        self.main_window = main_window  # Reference to MainWindow for permission checks
        self.current_list_id = None
        self.current_elements = []  # Store all elements for pagination
        self.view_mode = 'gallery'  # 'gallery' or 'list'
        self.alt_pressed = False  # Track Alt key state
        self.hover_timer = QtCore.QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_info_popup)
        self.hover_item = None
        self.media_popup = MediaInfoPopup(self)
        self.media_popup.insert_requested.connect(self.on_popup_insert)
        self.media_popup.reveal_requested.connect(self.on_popup_reveal)
        self.preview_cache = get_preview_cache()  # Initialize preview cache
        self.gif_movies = {}  # Cache for QMovie objects {element_id: QMovie}
        self.current_gif_item = None  # Currently hovering item with GIF
        self.element_items = {}  # Map element_id -> QListWidgetItem
        self.element_flags = {}  # Map element_id -> status flags (favorite/deprecated)
        self.setup_ui()
        
        # Enable mouse tracking for hover events
        self.setMouseTracking(True)
    
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
        search_layout.addWidget(self.search_box)
        
        # Search hint label
        self.search_hint_label = QtWidgets.QLabel()
        self.search_hint_label.setStyleSheet("color: #888888; font-size: 10px; font-style: italic;")
        self.search_hint_label.hide()  # Hidden by default
        search_layout.addWidget(self.search_hint_label)
        
        toolbar.addWidget(search_container, 1)  # Give it stretch priority
        
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
        
        # Stacked widget for different views
        self.view_stack = QtWidgets.QStackedWidget()
        
        # Gallery view (grid of thumbnails with drag & drop)
        self.gallery_view = DragGalleryView(self.db, self.nuke_bridge)
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
        self.table_view.setColumnCount(6)
        self.table_view.setHorizontalHeaderLabels(['Name', 'Format', 'Frames', 'Type', 'Size', 'Comment'])
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Multi-select
        self.table_view.itemClicked.connect(self.on_table_item_clicked)
        self.table_view.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        self.table_view.setMouseTracking(True)  # Enable hover tracking
        self.table_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.table_view)
        
        layout.addWidget(self.view_stack)
        
        # Pagination widget
        self.pagination = PaginationWidget()
        self.pagination.page_changed.connect(self.on_page_changed)
        self.pagination.setVisible(self.config.get('pagination_enabled', True))
        layout.addWidget(self.pagination)
        
        # Info label
        self.info_label = QtWidgets.QLabel("Select a list to view elements")
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("color: gray; font-size: 12px; padding: 20px;")
        layout.addWidget(self.info_label)
    
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
        """Handle thumbnail size change - reload elements with new size."""
        self.gallery_view.setIconSize(QtCore.QSize(value, value))
        
        # Reload visible items to rescale images
        if not self.current_elements:
            return
        if self.config.get('pagination_enabled', True) and self.current_list_id:
            self._display_current_page()
        else:
            self._update_views_with_elements(self.current_elements)
    
    def load_elements(self, list_id):
        """Load elements for a list with preview caching and pagination."""
        self.current_list_id = list_id
        elements = self.db.get_elements_by_list(list_id)
        
        # Store all elements for pagination
        self.current_elements = elements
        
        self.info_label.setVisible(len(elements) == 0)
        
        if len(elements) > 0:
            self.info_label.setText("")
        else:
            lst = self.db.get_list_by_id(list_id)
            if lst:
                self.info_label.setText("No elements in '{}'".format(lst['name']))
        
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
    
    def on_search(self, text):
        """Handle search text change (live filter) with tag support and pagination."""
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
        
        # Display current page
        self._display_current_page()
    
    
    def _update_views_with_elements(self, elements):
        """Update gallery and table views with given elements."""
        self.stop_current_gif()
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

            gif_path = element.get('gif_preview_path')
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
                        scaled_pixmap = pixmap.scaled(
                            icon_size,
                            QtCore.Qt.KeepAspectRatio,
                            QtCore.Qt.SmoothTransformation
                        )
                        scaled_pixmap = self._apply_status_badges(scaled_pixmap, element_id)
                        item.setIcon(QtGui.QIcon(scaled_pixmap))
                else:
                    has_gif = False

            if not has_gif:
                static_pixmap = self._load_preview_pixmap(element, icon_size)
                if static_pixmap:
                    item.setIcon(QtGui.QIcon(static_pixmap))
                else:
                    item.setIcon(self._get_default_icon_for_type(element.get('type')))

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
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element.get('frame_range') or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element.get('type') or ''))

            size_str = ''
            if element.get('file_size'):
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))

            comment_text = element.get('comment') or ''
            if element.get('tags'):
                comment_text += " [Tags: " + element['tags'] + "]"
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(comment_text))

            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element_id)

    def _load_preview_pixmap(self, element, icon_size):
        """Load and scale a static preview pixmap for an element."""
        preview_path = element.get('preview_path')
        if not preview_path or not os.path.exists(preview_path):
            return None

        cached_pixmap = self.preview_cache.get(preview_path)
        if not cached_pixmap:
            cached_pixmap = QtGui.QPixmap(preview_path)
            if not cached_pixmap.isNull():
                self.preview_cache.put(preview_path, cached_pixmap)

        if cached_pixmap and not cached_pixmap.isNull():
            scaled_pixmap = cached_pixmap.scaled(
                icon_size,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            element_id = element.get('element_id')
            if element_id:
                scaled_pixmap = self._apply_status_badges(scaled_pixmap, element_id)
            return scaled_pixmap
        return None

    def _get_default_icon_for_type(self, element_type):
        """Return a fallback icon when no preview is available."""
        if element_type == '2D':
            return self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        if element_type == '3D':
            return self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon)
        return self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView)

    def _apply_status_badges(self, pixmap, element_id):
        """Overlay favorite/deprecated badges onto a pixmap."""
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
    
    def eventFilter(self, obj, event):
        """Event filter to handle Alt+Hover."""
        # Check if widgets are initialized
        if not hasattr(self, 'gallery_view') or not hasattr(self, 'table_view'):
            return super(MediaDisplayWidget, self).eventFilter(obj, event)
        
        if obj in [self.gallery_view.viewport(), self.table_view.viewport()]:
            if event.type() == QtCore.QEvent.MouseMove:
                # Check if Alt is pressed
                modifiers = QtWidgets.QApplication.keyboardModifiers()
                self.alt_pressed = (modifiers & QtCore.Qt.AltModifier)
                
                if self.alt_pressed:
                    # Get item under cursor
                    pos = event.pos()
                    
                    if obj == self.gallery_view.viewport():
                        item = self.gallery_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                    elif obj == self.table_view.viewport():
                        item = self.table_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                else:
                    # Hide popup if Alt released
                    if self.media_popup.isVisible():
                        self.media_popup.hide()
                    self.hover_timer.stop()
                    self.hover_item = None
                    
                # Handle GIF preview on hover (without Alt key)
                if not self.alt_pressed and obj == self.gallery_view.viewport():
                    pos = event.pos()
                    item = self.gallery_view.itemAt(pos)
                    
                    if item and item != self.current_gif_item:
                        # Stop previous GIF
                        self.stop_current_gif()
                        
                        # Start new GIF if available
                        element_id = item.data(QtCore.Qt.UserRole)
                        if element_id:
                            self.play_gif_for_item(item, element_id)
                            self.current_gif_item = item
                    elif not item and self.current_gif_item:
                        # Mouse left all items, stop GIF
                        self.stop_current_gif()
                        self.current_gif_item = None
            
            elif event.type() == QtCore.QEvent.Leave:
                # Hide popup when leaving widget
                self.hover_timer.stop()
                self.hover_item = None
                
                # Stop GIF playback
                self.stop_current_gif()
                self.current_gif_item = None
        
        return super(MediaDisplayWidget, self).eventFilter(obj, event)
    
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
        scaled_pixmap = pixmap.scaled(
            icon_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        scaled_pixmap = self._apply_status_badges(scaled_pixmap, element_id)

        try:
            item.setIcon(QtGui.QIcon(scaled_pixmap))
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
            element_id = self.table_view.item(self.hover_item.row(), 0).data(QtCore.Qt.UserRole)
        
        if element_id:
            element_data = self.db.get_element_by_id(element_id)
            if element_data:
                # Get global cursor position
                cursor_pos = QtGui.QCursor.pos()
                self.media_popup.show_element(element_data, cursor_pos)
    
    def on_popup_insert(self, element_id):
        """Handle insert request from popup - insert element into Nuke."""
        self.gallery_view.insert_to_nuke([element_id])
        self.element_double_clicked.emit(element_id)
    
    def on_popup_reveal(self, filepath):
        """Handle reveal request from popup."""
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
        
        # If multiple items selected, show bulk operations menu
        if len(selected_ids) > 1:
            # Bulk operations header
            header_label = QtWidgets.QLabel("  {} items selected  ".format(len(selected_ids)))
            header_label.setStyleSheet("font-weight: bold; color: #16c6b0; padding: 5px;")
            header_action = QtWidgets.QWidgetAction(self)
            header_action.setDefaultWidget(header_label)
            menu.addAction(header_action)
            
            menu.addSeparator()
            
            # Bulk add to favorites
            bulk_fav_action = menu.addAction(get_icon('favorite', size=16), "Add All to Favorites")
            
            # Bulk add to playlist
            bulk_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")
            
            menu.addSeparator()
            
            # Bulk mark as deprecated (admin only)
            bulk_deprecate_action = menu.addAction(get_icon('deprecated', size=16), "Mark All as Deprecated")
            if not self.parent().is_admin:
                bulk_deprecate_action.setEnabled(False)
            
            # Bulk delete (admin only)
            bulk_delete_action = menu.addAction(get_icon('delete', size=16), "Delete All Selected")
            if not self.parent().is_admin:
                bulk_delete_action.setEnabled(False)
            
            # Execute menu
            action = menu.exec_(position)
            
            if action == bulk_fav_action:
                self.bulk_add_to_favorites(selected_ids)
            elif action == bulk_playlist_action:
                self.bulk_add_to_playlist(selected_ids)
            elif action == bulk_deprecate_action:
                self.bulk_mark_deprecated(selected_ids)
            elif action == bulk_delete_action:
                self.bulk_delete(selected_ids)
        
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
            
            # Insert into Nuke action
            insert_action = menu.addAction("Insert into Nuke")
            
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
            elif action == insert_action:
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
                # Delete from database
                self.db.delete_element(element_id)
                
                # TODO: Optionally delete physical files
                # filepath = element.get('filepath_hard') or element.get('filepath_soft')
                # if filepath and os.path.exists(filepath):
                #     os.remove(filepath)
                
                QtWidgets.QMessageBox.information(self, "Success", "Element deleted successfully.")
                
                # Refresh display
                if self.current_list_id:
                    self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete element: {}".format(str(e)))
    
    def show_bulk_menu(self):
        """Show bulk operations menu."""
        # Get selected elements
        selected_ids = self.get_selected_element_ids()
        
        if not selected_ids:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select one or more elements.\n\nTip: Hold Ctrl/Cmd to select multiple items.")
            return
        
        # Create menu
        menu = QtWidgets.QMenu(self)
        
        # Bulk add to favorites
        bulk_fav_action = menu.addAction(get_icon('favorite', size=16), "Add All to Favorites")
        
        # Bulk add to playlist
        bulk_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")
        
        menu.addSeparator()
        
        # Bulk mark as deprecated
        bulk_deprecate_action = menu.addAction(get_icon('deprecated', size=16), "Mark All as Deprecated")
        
        # Bulk delete
        bulk_delete_action = menu.addAction(get_icon('delete', size=16), "Delete All Selected")
        
        # Execute menu
        action = menu.exec_(QtGui.QCursor.pos())
        
        if action == bulk_fav_action:
            self.bulk_add_to_favorites(selected_ids)
        elif action == bulk_playlist_action:
            self.bulk_add_to_playlist(selected_ids)
        elif action == bulk_deprecate_action:
            self.bulk_mark_deprecated(selected_ids)
        elif action == bulk_delete_action:
            self.bulk_delete(selected_ids)
    
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
    
    def load_favorites(self):
        """Load and display favorite elements."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')
        
        favorites = self.db.get_favorites(user, machine)
        
        self.current_list_id = None  # Clear current list
        self.current_elements = favorites
        self.pagination.setVisible(False)
        self.info_label.setText("Favorites ({} items)".format(len(favorites)))
        self._update_views_with_elements(favorites)
    
    def load_playlist(self, playlist_id):
        """Load and display playlist elements."""
        playlist = self.db.get_playlist_by_id(playlist_id)
        if not playlist:
            return
        
        elements = self.db.get_playlist_elements(playlist_id)
        
        self.current_list_id = None  # Clear current list
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


