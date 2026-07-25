# -*- coding: utf-8 -*-
"""Visible multi-select action tray for bulk curation (EP1)."""

import logging

from PySide2 import QtWidgets, QtCore

logger = logging.getLogger(__name__)


class MultiSelectActionTray(QtWidgets.QWidget):
    """Bottom bar shown when >=2 items are selected.

    Rate/Label act directly via bulk DB calls; the rest emit signals the
    host (MediaDisplayWidget) connects to its existing bulk handlers.
    """

    rate_requested     = QtCore.Signal(int)
    label_requested    = QtCore.Signal(object)   # label_id or None
    tag_requested      = QtCore.Signal()
    favorite_requested = QtCore.Signal()
    playlist_requested = QtCore.Signal()
    deprecate_requested = QtCore.Signal()
    delete_requested   = QtCore.Signal()
    edit_requested     = QtCore.Signal()

    def __init__(self, db, main_window, parent=None):
        super(MultiSelectActionTray, self).__init__(parent)
        self.db = db
        self.main_window = main_window
        self._selection = []

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)

        self.count_label = QtWidgets.QLabel("0 selected")
        row.addWidget(self.count_label)
        row.addStretch(1)

        self.rate_button     = self._add_button(row, "Rate", self._show_rate_menu)
        self.label_button    = self._add_button(row, "Label", self._show_label_menu)
        self.tag_button      = self._add_button(row, "Add tag", self.tag_requested.emit)
        self.favorite_button = self._add_button(row, "Favorite", self.favorite_requested.emit)
        self.playlist_button = self._add_button(row, "Add to playlist", self.playlist_requested.emit)
        self.deprecate_button = self._add_button(row, "Deprecate", self.deprecate_requested.emit)
        self.delete_button   = self._add_button(row, "Delete", self.delete_requested.emit)
        self.edit_button     = self._add_button(row, "Edit…", self.edit_requested.emit)

        # Reserve the tray's row *height* even while hidden, so the media view
        # doesn't jump up/down each time the selection count crosses the
        # 2-item threshold that toggles this bar. The horizontal policy is set
        # to Ignored so the 8-button row's wide size hint is NOT folded into
        # the media pane's -- and thus the window's -- minimum width (that
        # would permanently widen the app). Height-only reservation (UI-scaling
        # fix).
        sp = self.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
        self.setSizePolicy(sp)

        self.hide()

    def _add_button(self, row, text, slot):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(slot)
        row.addWidget(b)
        return b

    def set_selection(self, element_ids):
        self._selection = list(element_ids)
        n = len(self._selection)
        self.count_label.setText("{} selected".format(n))
        # State query, not an action gate: read the flag directly rather than
        # calling check_admin_permission(), which is interactive (pops a login
        # dialog / warning box) and must never run on a selection-changed path
        # (see MediaDisplayWidget._is_admin_user(); this hung the suite twice).
        is_admin = bool(getattr(self.main_window, 'is_admin', False))
        self.delete_button.setEnabled(is_admin)
        self.deprecate_button.setEnabled(is_admin)
        self.setVisible(n >= 2)

    # --- Rate ---
    def _show_rate_menu(self):
        menu = QtWidgets.QMenu(self)
        for stars in range(1, 6):
            act = menu.addAction("{} star{}".format(stars, "s" if stars > 1 else ""))
            act.triggered.connect(lambda checked=False, s=stars: self.apply_rating(s))
        clear = menu.addAction("Clear rating")
        clear.triggered.connect(lambda: self.apply_rating(0))
        menu.exec_(self.rate_button.mapToGlobal(self.rate_button.rect().bottomLeft()))

    def apply_rating(self, stars):
        if not self._selection:
            return
        self.db.bulk_set_rating(self._selection, stars)
        self.rate_requested.emit(stars)

    # --- Label ---
    def _show_label_menu(self):
        menu = QtWidgets.QMenu(self)
        for lbl in self.db.get_labels():
            act = menu.addAction(lbl["name"])
            act.triggered.connect(
                lambda checked=False, lid=lbl["label_id"]: self.apply_label(lid))
        clear = menu.addAction("Clear label")
        clear.triggered.connect(lambda: self.apply_label(None))
        menu.exec_(self.label_button.mapToGlobal(self.label_button.rect().bottomLeft()))

    def apply_label(self, label_id):
        if not self._selection:
            return
        self.db.bulk_set_label(self._selection, label_id)
        self.label_requested.emit(label_id)
