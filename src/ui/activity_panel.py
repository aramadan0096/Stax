# -*- coding: utf-8 -*-
"""Activity / audit feed dock (EP8, F043)."""

from PySide2 import QtWidgets, QtCore

_COLUMNS = ["When", "Actor", "Action", "Target", "Detail"]


class ActivityPanel(QtWidgets.QDockWidget):
    def __init__(self, db, parent=None):
        super(ActivityPanel, self).__init__("Activity", parent)
        self.db = db
        self._action = None
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)

        bar = QtWidgets.QHBoxLayout()
        self.action_filter = QtWidgets.QComboBox()
        self.action_filter.addItems(["(all)", "ingest", "delete", "metadata_edit",
                                     "role_change", "export", "import"])
        self.action_filter.currentTextChanged.connect(self._on_action_changed)
        self.actor_filter = QtWidgets.QComboBox()
        self.actor_filter.setEditable(True)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(QtWidgets.QLabel("Action:"))
        bar.addWidget(self.action_filter)
        bar.addWidget(QtWidgets.QLabel("Actor:"))
        bar.addWidget(self.actor_filter)
        bar.addWidget(refresh_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.activity_table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self.activity_table.setHorizontalHeaderLabels(_COLUMNS)
        self.activity_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.activity_table)

        self.setWidget(container)
        self.refresh()

    def set_action_filter(self, action):
        self._action = action

    def _on_action_changed(self, text):
        self._action = None if text == "(all)" else text

    def refresh(self):
        actor = self.actor_filter.currentText().strip() or None
        rows = self.db.get_activity(action=self._action, actor=actor)
        self.activity_table.setRowCount(len(rows))
        for row, ev in enumerate(rows):
            target = "{}#{}".format(ev.get("target_type") or "", ev.get("target_id") or "")
            values = [str(ev.get("at") or ""), ev.get("actor") or "",
                      ev.get("action") or "", target, ev.get("detail") or ""]
            for col, val in enumerate(values):
                self.activity_table.setItem(row, col, QtWidgets.QTableWidgetItem(val))
