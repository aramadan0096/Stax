# -*- coding: utf-8 -*-
"""Collapsible faceted filter drawer (EP2)."""

from PySide2 import QtWidgets, QtCore

# facet key -> (include list-key, exclude list-key or None)
#
# NOTE on "status": filter_spec.empty_filter() has no "status" key at all --
# current_filter() special-cases the "status" facet directly (mapping its
# "deprecated" value to spec["is_deprecated"]) and `continue`s before this
# table is ever consulted for it. The entry below is a documented no-op
# placeholder so every facet iterated in set_facets() has a row here; it
# must never be treated as a real (include, exclude) key pair.
_FACET_KEYS = {
    "type":   ("types", None),
    "format": ("formats", "formats_exclude"),
    "tag":    ("tags_any", "tags_exclude"),
    "rating": ("rating_min", None),
    "label":  ("label_fks", None),
    "status": (None, None),  # unused -- see NOTE above
}

# Mirrors _on_state's {0: None, 1: "exclude", 2: "include"} mapping in
# reverse, so a set_facets() rebuild can restore a checkbox's visual state
# from self._state without re-deriving the Qt tri-state semantics.
_STATE_TO_QT_CHECKSTATE = {
    "include": QtCore.Qt.Checked,
    "exclude": QtCore.Qt.PartiallyChecked,
}


class FacetDrawer(QtWidgets.QWidget):
    filter_changed = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super(FacetDrawer, self).__init__(parent)
        self._state = {}   # (facet, value) -> 'include' | 'exclude'
        self._layout = QtWidgets.QVBoxLayout(self)
        self._groups = {}
        self._checkboxes = {}  # (facet, str(value)) -> QCheckBox; rebuilt each set_facets()

    def set_facets(self, counts):
        # rebuild group boxes from counts
        for i in reversed(range(self._layout.count())):
            w = self._layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._groups = {}
        self._checkboxes = {}
        for facet in ("type", "format", "tag", "rating", "label", "status"):
            values = counts.get(facet, {})
            if not values and facet not in ("type", "format"):
                continue
            box = QtWidgets.QGroupBox(facet.capitalize())
            box.setCheckable(True)
            box.setChecked(False)
            vbox = QtWidgets.QVBoxLayout(box)
            for value, count in sorted(values.items(), key=lambda kv: str(kv[0])):
                row = self._make_row(facet, value, count)
                vbox.addWidget(row)
                self._checkboxes[(facet, str(value))] = row.checkbox
            self._layout.addWidget(box)
            self._groups[facet] = box
        # A refresh must not silently drop the user's existing selections,
        # but the freshly-built checkboxes come up unchecked -- restore
        # their visual state from self._state. This must never look like a
        # user edit (no filter_changed), or it could feedback-loop with
        # Task 6's apply_filter.
        self._restore_checkbox_states()

    def _make_row(self, facet, value, count):
        row = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        cb = QtWidgets.QCheckBox("{} ({})".format(value, count))
        cb.setTristate(True)
        cb.stateChanged.connect(
            lambda st, f=facet, v=value: self._on_state(f, v, st))
        h.addWidget(cb)
        row.checkbox = cb
        return row

    def _restore_checkbox_states(self):
        """Re-apply self._state onto the checkboxes set_facets() just
        rebuilt, without emitting filter_changed."""
        for key, cb in self._checkboxes.items():
            qt_state = _STATE_TO_QT_CHECKSTATE.get(self._state.get(key))
            if qt_state is None:
                continue
            cb.blockSignals(True)
            try:
                cb.setCheckState(qt_state)
            finally:
                cb.blockSignals(False)

    def _on_state(self, facet, value, qt_state):
        mapping = {0: None, 1: "exclude", 2: "include"}  # unchecked/partial/checked
        state = mapping.get(qt_state)
        key = (facet, str(value))
        if state is None:
            self._state.pop(key, None)
        else:
            self._state[key] = state
        self.filter_changed.emit(self.current_filter())

    def set_value_state(self, facet, value, state):
        """Programmatic setter used by tests and chip removal."""
        key = (facet, str(value))
        if state is None:
            self._state.pop(key, None)
        else:
            self._state[key] = state
        self.filter_changed.emit(self.current_filter())

    def current_filter(self):
        from filter_spec import empty_filter
        spec = empty_filter()
        for (facet, value), state in self._state.items():
            inc_key, exc_key = _FACET_KEYS[facet]
            if facet == "rating":
                if state == "include":
                    spec["rating_min"] = int(value)
                continue
            if facet == "status":
                if value == "deprecated":
                    spec["is_deprecated"] = (state == "include")
                continue
            target = inc_key if state == "include" else (exc_key or inc_key)
            if state == "exclude" and exc_key is None:
                continue
            coerced = int(value) if facet == "label" else value
            spec[target].append(coerced)
        return spec
