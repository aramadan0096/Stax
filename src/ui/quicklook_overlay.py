# -*- coding: utf-8 -*-
"""Spacebar quicklook overlay (EP3)."""

from PySide2 import QtWidgets, QtCore, QtGui


class QuickLookOverlay(QtWidgets.QWidget):
    next_requested = QtCore.Signal()
    prev_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super(QuickLookOverlay, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        layout = QtWidgets.QVBoxLayout(self)
        self.title_label = QtWidgets.QLabel("")
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label = QtWidgets.QLabel("")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(480, 360)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)

    def show_element(self, element, preview_path):
        self.title_label.setText(element.get("name", ""))
        self.image_label.clear()
        if preview_path:
            pix = QtGui.QPixmap(preview_path)
            if not pix.isNull():
                self.image_label.setPixmap(pix.scaled(
                    self.image_label.size(), QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation))
        self.show()
        self.setFocus()

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
