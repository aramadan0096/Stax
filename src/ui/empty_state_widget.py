# -*- coding: utf-8 -*-
"""Reusable context-aware empty-state widget (EP1)."""

from PySide2 import QtWidgets, QtCore

_KINDS = ("informational", "action", "celebratory")


class EmptyStateWidget(QtWidgets.QWidget):
    """A centered empty-state: headline, one sentence, and up to two actions.

    Each action is a (label, callable) tuple. `kind` is one of
    informational | action | celebratory (selects tone/icon).
    """

    def __init__(self, headline, message, primary_action=None,
                 secondary_action=None, kind="informational", parent=None):
        super(EmptyStateWidget, self).__init__(parent)
        if kind not in _KINDS:
            kind = "informational"
        self.kind = kind

        outer = QtWidgets.QVBoxLayout(self)
        outer.setAlignment(QtCore.Qt.AlignCenter)

        self.headline_label = QtWidgets.QLabel(headline)
        self.headline_label.setAlignment(QtCore.Qt.AlignCenter)
        f = self.headline_label.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        self.headline_label.setFont(f)

        self.message_label = QtWidgets.QLabel(message)
        self.message_label.setAlignment(QtCore.Qt.AlignCenter)
        self.message_label.setWordWrap(True)

        outer.addStretch(1)
        outer.addWidget(self.headline_label)
        outer.addWidget(self.message_label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setAlignment(QtCore.Qt.AlignCenter)
        self.primary_button = None
        self.secondary_button = None

        if primary_action is not None:
            label, cb = primary_action
            self.primary_button = QtWidgets.QPushButton(label)
            self.primary_button.setDefault(True)
            self.primary_button.clicked.connect(cb)
            buttons.addWidget(self.primary_button)

        if secondary_action is not None:
            label, cb = secondary_action
            self.secondary_button = QtWidgets.QPushButton(label)
            self.secondary_button.clicked.connect(cb)
            buttons.addWidget(self.secondary_button)

        outer.addLayout(buttons)
        outer.addStretch(1)
