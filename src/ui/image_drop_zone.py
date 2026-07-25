# -*- coding: utf-8 -*-
"""Reference-image drop zone for visual search (EP7, F002)."""

import os

from PySide2 import QtWidgets, QtCore

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".exr")


class ImageDropZone(QtWidgets.QFrame):
    image_dropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(ImageDropZone, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        layout = QtWidgets.QVBoxLayout(self)
        self._label = QtWidgets.QLabel("Drop a reference image\nor click Browse")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._label)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._on_browse)
        layout.addWidget(browse)

    def accept_path(self, path):
        if path and os.path.splitext(path)[1].lower() in _IMAGE_EXTS:
            self.image_dropped.emit(path)

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose reference image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.exr)")
        if path:
            self.accept_path(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.accept_path(url.toLocalFile())
            break
