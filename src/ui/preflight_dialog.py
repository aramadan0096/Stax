# -*- coding: utf-8 -*-
"""Preflight validation checklist dialog (EP6, F038)."""

from PySide2 import QtWidgets


class PreflightDialog(QtWidgets.QDialog):
    def __init__(self, issues, parent=None):
        super(PreflightDialog, self).__init__(parent)
        self.setWindowTitle("Preflight Check")
        self.issues = list(issues or [])
        layout = QtWidgets.QVBoxLayout(self)

        self.issues_table = QtWidgets.QTableWidget(len(self.issues), 3)
        self.issues_table.setHorizontalHeaderLabels(["Level", "File", "Message"])
        import os
        for r, issue in enumerate(self.issues):
            self.issues_table.setItem(r, 0, QtWidgets.QTableWidgetItem(issue.get("level", "")))
            self.issues_table.setItem(r, 1, QtWidgets.QTableWidgetItem(
                os.path.basename(issue.get("path", ""))))
            self.issues_table.setItem(r, 2, QtWidgets.QTableWidgetItem(issue.get("message", "")))
        layout.addWidget(self.issues_table)

        summary = "No issues." if not self.issues else "{} issue(s) found.".format(len(self.issues))
        layout.addWidget(QtWidgets.QLabel(summary))

        buttons = QtWidgets.QDialogButtonBox()
        self.ingest_button = buttons.addButton("Ingest", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        self.ingest_button.setEnabled(self.can_ingest())
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def can_ingest(self):
        """False when any blocking (error-level) issue is present."""
        return not any(i.get("level") == "error" for i in self.issues)
