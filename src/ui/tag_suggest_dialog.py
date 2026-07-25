# -*- coding: utf-8 -*-
"""Human-in-the-loop auto-tag accept dialog (EP7). Suggestions are never
written automatically — the user checks the tags to add."""

from PySide2 import QtWidgets, QtCore


class TagSuggestDialog(QtWidgets.QDialog):
    def __init__(self, suggestions, existing_tags=None, parent=None):
        super(TagSuggestDialog, self).__init__(parent)
        self.setWindowTitle("Suggested tags")
        self._boxes = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("AI-suggested tags (check the ones to add):"))
        existing = set(t.strip().lower() for t in (existing_tags or []))
        for tag, score in suggestions:
            cb = QtWidgets.QCheckBox("{}  ({:.0%})".format(tag, score))
            cb.setChecked(score >= 0.35 and tag.lower() not in existing)
            layout.addWidget(cb)
            self._boxes[tag] = cb
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_checked(self, tag, checked):
        if tag in self._boxes:
            self._boxes[tag].setChecked(checked)

    def accepted_tags(self):
        return [tag for tag, cb in self._boxes.items() if cb.isChecked()]

    @staticmethod
    def merge_tags(existing_csv, new_tags):
        out, seen = [], set()
        for t in [x.strip() for x in (existing_csv or "").split(",") if x.strip()]:
            key = t.lower()
            if key not in seen:
                seen.add(key); out.append(t)
        for t in new_tags:
            key = t.strip().lower()
            if key and key not in seen:
                seen.add(key); out.append(t.strip())
        return ", ".join(out)
