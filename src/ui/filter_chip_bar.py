# -*- coding: utf-8 -*-
"""Removable active-filter chips + result count (EP2)."""

from PySide2 import QtWidgets, QtCore

from src.icon_loader import get_icon

# clause list-keys rendered as chips: (spec_key, label_prefix)
_CHIP_LISTS = [
    ("types", "type"), ("formats", "format"), ("formats_exclude", "not format"),
    ("tags_any", "tag"), ("tags_all", "tag"), ("tags_exclude", "not tag"),
    ("label_fks", "label"),
]


class FilterChipBar(QtWidgets.QWidget):
    chip_removed = QtCore.Signal(str, object)
    cleared = QtCore.Signal()

    def __init__(self, parent=None):
        super(FilterChipBar, self).__init__(parent)
        self._row = QtWidgets.QHBoxLayout(self)
        self._row.setContentsMargins(6, 2, 6, 2)
        self.count_label = QtWidgets.QLabel("0 results")
        self.clear_button = QtWidgets.QPushButton("Clear all")
        self.clear_button.clicked.connect(self.cleared.emit)
        self._chips = []

    def chip_count(self):
        return len(self._chips)

    def set_filter(self, spec, result_count):
        # Fully clear the previous render first. count_label and
        # clear_button are created once in __init__ and re-added at the end
        # of every call, so they must be reparented (not disposed) here --
        # but every chip button from the previous call is disposable and
        # must not linger, and the addStretch(1) spacer from the previous
        # call must not accumulate either. self._row.takeAt(i) removes the
        # item from the layout outright (unlike the brief's bare
        # itemAt(i).widget() check, which silently skips non-widget spacer
        # items and would leave a fresh stretch behind on every call).
        # setParent(None) detaches a chip widget from the layout/parent
        # immediately, which is enough to keep it out of chip_count() and
        # off screen; deleteLater() on top schedules the underlying C++
        # object for actual destruction instead of leaking it (mirrors the
        # fix already applied to FacetDrawer.set_facets()).
        for i in reversed(range(self._row.count())):
            item = self._row.takeAt(i)
            w = item.widget()
            if w is None:
                continue  # stretch/spacer item -- just drop it
            if w is not self.count_label and w is not self.clear_button:
                w.deleteLater()
            w.setParent(None)
        self._chips = []

        for key, prefix in _CHIP_LISTS:
            for value in (spec.get(key) or []):
                self._add_chip(key, value, "{}: {}".format(prefix, value))
        if spec.get("text"):
            self._add_chip("text", spec["text"], "text: {}".format(spec["text"]))
        if spec.get("rating_min"):
            self._add_chip("rating_min", spec["rating_min"], "rating ≥ {}".format(spec["rating_min"]))
        if spec.get("is_deprecated") is not None:
            self._add_chip("is_deprecated", spec["is_deprecated"],
                           "deprecated" if spec["is_deprecated"] else "active")

        self._row.addStretch(1)
        self.count_label.setText("{} results".format(result_count))
        self._row.addWidget(self.count_label)
        self._row.addWidget(self.clear_button)

    def _add_chip(self, key, value, text):
        # Icon (SVG) sits after the label: RightToLeft puts the close glyph on
        # the trailing edge, matching the old "text  ✕" affordance.
        btn = QtWidgets.QPushButton(text)
        btn.setIcon(get_icon('close', size=12))
        btn.setLayoutDirection(QtCore.Qt.RightToLeft)
        btn.clicked.connect(lambda: self.chip_removed.emit(key, value))
        self._row.addWidget(btn)
        self._chips.append(btn)
