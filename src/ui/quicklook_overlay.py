# -*- coding: utf-8 -*-
"""Spacebar quicklook overlay (EP3)."""

import os

from PySide2 import QtWidgets, QtCore, QtGui


class QuickLookOverlay(QtWidgets.QWidget):
    next_requested = QtCore.Signal()
    prev_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super(QuickLookOverlay, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        # Repeated Space-opens must not accumulate hidden QuickLookOverlay
        # instances for the life of the app: close() destroys this widget
        # instead of just hiding it (mirrors the CommandPalette fix, Task 2).
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        self.title_label = QtWidgets.QLabel("")
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label = QtWidgets.QLabel("")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(480, 360)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)
        self._movie = None
        # Source pixmap kept at full resolution so the preview can be
        # re-scaled to the label's current size whenever the overlay is
        # resized -- otherwise the image stayed at its first-shown size while
        # the window grew around it (UI-scaling fix).
        self._source_pixmap = None

    def show_element(self, element, preview_path, preview_kind='image'):
        """Show the large preview for `element`.

        `preview_path`/`preview_kind` are expected to come from
        MediaDisplayWidget._resolve_element_preview: `preview_kind == 'gif'`
        renders an animated preview via QMovie; anything else renders a
        static preview via QPixmap. A missing/unreadable file (or no path
        at all) is handled safely -- any previous element's image/movie is
        torn down first, so nothing stale is ever left on screen, and a
        bad file simply results in a blank preview rather than a crash.
        """
        self.title_label.setText(element.get("name", ""))

        # Tear down any previous animated movie before doing anything else --
        # otherwise a running QMovie keeps ticking/painting over whatever we
        # show next.
        if self._movie is not None:
            self._movie.stop()
            self.image_label.setMovie(None)
            self._movie.deleteLater()
            self._movie = None
        self._source_pixmap = None
        self.image_label.clear()

        if preview_path and os.path.exists(preview_path):
            if preview_kind == 'gif':
                movie = QtGui.QMovie(preview_path)
                if movie.isValid():
                    movie.setCacheMode(QtGui.QMovie.CacheAll)
                    self.image_label.setMovie(movie)
                    movie.start()
                    self._movie = movie
                # else: corrupt/unreadable GIF -- stays cleared, no crash.
            else:
                pix = QtGui.QPixmap(preview_path)
                if not pix.isNull():
                    self._source_pixmap = pix
                    self._rescale_pixmap()
                # else: corrupt/unreadable image -- stays cleared, no crash.

        self.show()
        self.setFocus()

    def _rescale_pixmap(self):
        """Scale the cached source pixmap to the label's current size."""
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        self.image_label.setPixmap(self._source_pixmap.scaled(
            self.image_label.size(), QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super(QuickLookOverlay, self).resizeEvent(event)
        # Re-fit the static preview to the new size (QMovie scales itself).
        self._rescale_pixmap()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Escape):
            self.close()
        elif key == QtCore.Qt.Key_Right:
            self.next_requested.emit()
        elif key == QtCore.Qt.Key_Left:
            self.prev_requested.emit()
        else:
            super(QuickLookOverlay, self).keyPressEvent(event)
