# -*- coding: utf-8 -*-
"""
StaX — Lazy Virtual Scroll Gallery  (Feature 2)
================================================
Drop-in replacement for the synchronous thumbnail loader used inside
MediaDisplayWidget's gallery_view (QListWidget).

Problems solved
---------------
  • Old code loaded every thumbnail into a QPixmap at list-selection time,
    freezing the UI for large lists.
  • QListWidget with 500+ items consumed hundreds of MB of pixmap memory
    even for items the user never scrolled to.

New behaviour
-------------
  • Only items within (or near) the visible viewport area have their
    pixmaps loaded.
  • A 200 ms debounce timer prevents excessive reloads during fast scrolling.
  • Thumbnails loaded by the async PreviewWorker are picked up via the
    on_preview_ready slot and injected into the correct item without a
    full reload.
  • Memory is released for items that scroll far out of view (LRU cache).

Integration
-----------
Replace the existing gallery_view widget in MediaDisplayWidget with
LazyGalleryView, then call:

    self.gallery_view = LazyGalleryView(parent=self)
    self.gallery_view.element_clicked.connect(...)
    self.gallery_view.element_double_clicked.connect(...)

The LazyGalleryView stores element dicts internally; populate it with:

    self.gallery_view.set_elements(list_of_element_dicts, previews_dir)

And connect the preview worker:

    from src.preview_worker import get_preview_queue
    get_preview_queue().preview_ready.connect(
        self.gallery_view.on_preview_ready
    )
"""

from __future__ import absolute_import, unicode_literals

import os
import logging
from collections import OrderedDict

from PySide2 import QtWidgets, QtCore, QtGui

log = logging.getLogger(__name__)

# Number of extra rows above/below the visible viewport to keep loaded.
_BUFFER_ROWS = 3
# Max number of pixmaps to keep in the LRU cache.
_MAX_CACHE = 300
# Debounce delay in ms before triggering a lazy-load sweep.
_DEBOUNCE_MS = 150
# Default thumbnail dimensions in gallery mode.
_THUMB_W = 160
_THUMB_H = 120


# ---------------------------------------------------------------------------
# LRU pixmap cache
# ---------------------------------------------------------------------------

class _PixmapCache(object):
    """Thread-safe-ish LRU cache for QPixmap objects, keyed by file path."""

    def __init__(self, maxsize=_MAX_CACHE):
        self._data    = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key, pixmap):
        if key in self._data:
            self._data.move_to_end(key)
        else:
            if len(self._data) >= self._maxsize:
                self._data.popitem(last=False)   # evict oldest
            self._data[key] = pixmap

    def invalidate(self, key):
        self._data.pop(key, None)


_GLOBAL_PIXMAP_CACHE = _PixmapCache()


def _load_pixmap(path, w, h):
    """
    Load a scaled pixmap from *path*, using the global LRU cache.
    Returns a placeholder pixmap if the file is missing or unreadable.
    """
    cached = _GLOBAL_PIXMAP_CACHE.get(path)
    if cached is not None:
        return cached

    if path and os.path.isfile(path):
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            pix = pix.scaled(
                w, h,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            _GLOBAL_PIXMAP_CACHE.put(path, pix)
            return pix

    # Return a grey placeholder
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtGui.QColor(60, 60, 60))
    _GLOBAL_PIXMAP_CACHE.put(path, pix)
    return pix


# ---------------------------------------------------------------------------
# Custom list widget item
# ---------------------------------------------------------------------------

class GalleryItem(QtWidgets.QListWidgetItem):
    """
    A single cell in the gallery grid.

    The item stores the full element dict but defers pixmap loading
    until LazyGalleryView decides the item is near the viewport.
    """

    def __init__(self, element, thumb_w=_THUMB_W, thumb_h=_THUMB_H):
        super(GalleryItem, self).__init__()
        self.element  = element
        self.thumb_w  = thumb_w
        self.thumb_h  = thumb_h
        self._loaded  = False

        name = element.get("name", "")
        self.setText(name)
        self.setToolTip(name)
        self.setSizeHint(QtCore.QSize(thumb_w + 8, thumb_h + 28))

        # Grey placeholder immediately
        pix = QtGui.QPixmap(thumb_w, thumb_h)
        pix.fill(QtGui.QColor(45, 45, 45))
        self.setIcon(QtGui.QIcon(pix))
        self.setData(QtCore.Qt.UserRole, element.get("element_id"))

    def load_pixmap(self):
        """Load the real thumbnail from disk (called lazily)."""
        if self._loaded:
            return
        path = self.element.get("preview_path") or ""
        pix  = _load_pixmap(path, self.thumb_w, self.thumb_h)
        self.setIcon(QtGui.QIcon(pix))
        self._loaded = True

    def update_pixmap(self, new_path):
        """Called when PreviewWorker delivers a freshly generated thumb."""
        _GLOBAL_PIXMAP_CACHE.invalidate(
            self.element.get("preview_path") or ""
        )
        self.element["preview_path"] = new_path
        self._loaded = False
        self.load_pixmap()


# ---------------------------------------------------------------------------
# LazyGalleryView
# ---------------------------------------------------------------------------

class LazyGalleryView(QtWidgets.QListWidget):
    """
    A QListWidget gallery that lazily loads thumbnails as the user scrolls.

    Signals
    -------
    element_clicked(int)         emits element_id on single click
    element_double_clicked(int)  emits element_id on double click
    selection_changed(list)      emits list[int] element_ids on selection change
    """

    element_clicked        = QtCore.Signal(int)
    element_double_clicked = QtCore.Signal(int)
    selection_changed      = QtCore.Signal(list)

    def __init__(self, thumb_w=_THUMB_W, thumb_h=_THUMB_H, parent=None):
        super(LazyGalleryView, self).__init__(parent)
        self.thumb_w = thumb_w
        self.thumb_h = thumb_h

        self._element_index = {}   # element_id → GalleryItem

        # Configure appearance
        self.setViewMode(QtWidgets.QListWidget.IconMode)
        self.setResizeMode(QtWidgets.QListWidget.Adjust)
        self.setMovement(QtWidgets.QListWidget.Static)
        self.setSpacing(6)
        self.setIconSize(QtCore.QSize(thumb_w, thumb_h))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setWordWrap(True)
        self.setTextElideMode(QtCore.Qt.ElideRight)

        # Debounce timer for scroll events
        self._lazy_timer = QtCore.QTimer(self)
        self._lazy_timer.setSingleShot(True)
        self._lazy_timer.setInterval(_DEBOUNCE_MS)
        self._lazy_timer.timeout.connect(self._load_visible)

        # Connect scrollbar to debounce
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)

        # Wire selection / activation
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_elements(self, elements, thumb_w=None, thumb_h=None):
        """
        Populate the gallery with a list of element dicts.

        Parameters
        ----------
        elements : list[dict]   from db_manager.get_elements_*()
        thumb_w, thumb_h : int  optional override for thumbnail dimensions
        """
        if thumb_w:
            self.thumb_w = thumb_w
            self.setIconSize(QtCore.QSize(thumb_w, thumb_h or self.thumb_h))
        if thumb_h:
            self.thumb_h = thumb_h

        self.clear()
        self._element_index.clear()

        for element in elements:
            item = GalleryItem(element, self.thumb_w, self.thumb_h)
            self.addItem(item)
            eid = element.get("element_id")
            if eid is not None:
                self._element_index[eid] = item

        # Trigger first-visible load after Qt has laid out the items
        QtCore.QTimer.singleShot(0, self._load_visible)

    def get_selected_element_ids(self):
        """Return list of selected element_ids."""
        return [
            item.data(QtCore.Qt.UserRole)
            for item in self.selectedItems()
            if item.data(QtCore.Qt.UserRole) is not None
        ]

    def set_thumbnail_size(self, w, h):
        """Resize all thumbnails (called when user drags the size slider)."""
        self.thumb_w = w
        self.thumb_h = h
        self.setIconSize(QtCore.QSize(w, h))
        for i in range(self.count()):
            item = self.item(i)
            if isinstance(item, GalleryItem):
                item.thumb_w = w
                item.thumb_h = h
                item.setSizeHint(QtCore.QSize(w + 8, h + 28))
                item._loaded = False
        self._load_visible()

    # ------------------------------------------------------------------
    # Slot: called by PreviewWorker.preview_ready signal
    # ------------------------------------------------------------------

    @QtCore.Slot(int, str, str)
    def on_preview_ready(self, element_id, preview_path, preview_type):
        """
        Update the gallery item for *element_id* with the newly generated
        preview.  Only 'thumbnail' type triggers an immediate icon update;
        other types (gif, video) are stored on the element dict for later.
        """
        item = self._element_index.get(element_id)
        if item is None:
            return

        if preview_type == "thumbnail":
            item.update_pixmap(preview_path)
        else:
            # Store path for hover / preview-pane use
            key = "preview_{}_path".format(preview_type)
            item.element[key] = preview_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_scroll(self, _value=None):
        """Restart debounce timer on every scroll event."""
        self._lazy_timer.start()

    def _load_visible(self):
        """
        Find all items whose visual rect overlaps the visible viewport
        (plus a buffer of _BUFFER_ROWS rows) and load their pixmaps.
        Items far outside the viewport have their pixmaps released.
        """
        if self.count() == 0:
            return

        viewport_rect = QtCore.QRect(
            QtCore.QPoint(0, 0),
            self.viewport().size(),
        )
        # Expand viewport by buffer rows
        row_h = self.thumb_h + 28 + 6   # item height + label + spacing
        buffer_px = _BUFFER_ROWS * row_h
        expanded  = viewport_rect.adjusted(0, -buffer_px, 0, buffer_px)

        # Eviction zone: more than 3× viewport height away
        evict_margin = 3 * viewport_rect.height()
        evict_zone   = viewport_rect.adjusted(
            0, -evict_margin, 0, evict_margin
        )

        for i in range(self.count()):
            item = self.item(i)
            if not isinstance(item, GalleryItem):
                continue

            rect = self.visualItemRect(item)

            if expanded.intersects(rect):
                item.load_pixmap()
            elif item._loaded and not evict_zone.intersects(rect):
                # Release pixmap memory for far-away items
                placeholder = QtGui.QPixmap(self.thumb_w, self.thumb_h)
                placeholder.fill(QtGui.QColor(45, 45, 45))
                item.setIcon(QtGui.QIcon(placeholder))
                item._loaded = False

    # ------------------------------------------------------------------
    # Signal forwarders
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item):
        eid = item.data(QtCore.Qt.UserRole)
        if eid is not None:
            self.element_clicked.emit(eid)

    def _on_item_double_clicked(self, item):
        eid = item.data(QtCore.Qt.UserRole)
        if eid is not None:
            self.element_double_clicked.emit(eid)

    def _on_selection_changed(self):
        self.selection_changed.emit(self.get_selected_element_ids())

    # ------------------------------------------------------------------
    # Resize event — re-trigger lazy load when the window is resized
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super(LazyGalleryView, self).resizeEvent(event)
        self._lazy_timer.start()
