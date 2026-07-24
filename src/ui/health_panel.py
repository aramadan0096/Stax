# -*- coding: utf-8 -*-
"""Metadata quality Health panel (EP4).

Lists metadata-quality issues (from ``DatabaseManager.check_element_quality``)
for every element in a given list, so a user can spot naming/metadata
problems at a glance and jump straight to the offending element.
"""

import logging

from PySide2 import QtWidgets, QtCore

logger = logging.getLogger(__name__)


class HealthPanel(QtWidgets.QWidget):
    """Bottom-dock panel showing metadata quality issues for a list.

    Consumes ``db.get_elements_by_list(list_id)`` and
    ``db.check_element_quality(element_id)`` (EP4 Task 11). Double-clicking
    a row emits ``element_selected(element_id)`` so a host window can
    navigate to the offending element.
    """

    element_selected = QtCore.Signal(int)

    def __init__(self, db, parent=None):
        super(HealthPanel, self).__init__(parent)
        self.db = db
        layout = QtWidgets.QVBoxLayout(self)
        self.summary_label = QtWidgets.QLabel("No issues")
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Element", "Issue"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_activate)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        self._rows = []

    def load_list(self, list_id):
        """Refresh the panel with quality issues for every element in
        `list_id`."""
        self._rows = []
        for el in self.db.get_elements_by_list(list_id):
            for issue in self.db.check_element_quality(el["element_id"]):
                self._rows.append((el["element_id"], el["name"], issue["message"]))
        self.table.setRowCount(len(self._rows))
        for r, (_eid, name, msg) in enumerate(self._rows):
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(msg))
        self.summary_label.setText("{} issue(s)".format(len(self._rows)))

    def issue_count(self):
        """Return the number of issues currently listed."""
        return len(self._rows)

    def _on_activate(self, item):
        row = item.row()
        if 0 <= row < len(self._rows):
            self.element_selected.emit(self._rows[row][0])
