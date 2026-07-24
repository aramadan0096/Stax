# -*- coding: utf-8 -*-
"""Collapsible faceted filter drawer (EP2)."""

from PySide2 import QtWidgets, QtCore

# facet key -> (include list-key, exclude list-key or None)
#
# NOTE on "status": filter_spec.empty_filter() has no "status" key at all --
# current_filter() resolves the "status" facet's "active"/"deprecated" rows
# directly onto spec["is_deprecated"] *before* the per-(facet, value) loop
# runs (see the resolution block at the top of current_filter()). That loop
# still indexes this table unconditionally for every (facet, value) pair,
# including "status" ones -- it is only the resulting (inc_key, exc_key)
# tuple that goes unused for "status", which hits its own `continue` before
# any list-key would be touched. The entry below is a documented no-op
# placeholder so every facet iterated in set_facets() has a row here; it
# must never be treated as a real (include, exclude) key pair.
_FACET_KEYS = {
    "type":   ("types", None),
    "format": ("formats", "formats_exclude"),
    "tag":    ("tags_any", "tags_exclude"),
    "rating": ("rating_min", None),
    "label":  ("label_fks", None),
    "status": (None, None),  # placeholder only -- see NOTE above; unused by current_filter()
}

# Mirrors _on_state's {0: None, 1: "exclude", 2: "include"} mapping in
# reverse, so a set_facets() rebuild (or a programmatic set_value_state()
# call) can restore a checkbox's visual state from self._state without
# re-deriving the Qt tri-state semantics.
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
        self._checkboxes = {}  # (facet, str(value)) -> QCheckBox; rebuilt each set_facets()

    def set_facets(self, counts):
        # rebuild group boxes from counts
        for i in reversed(range(self._layout.count())):
            w = self._layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._checkboxes = {}
        for facet in ("type", "format", "tag", "rating", "label", "status"):
            values = counts.get(facet, {})
            # Values the user has already selected for this facet but that
            # this refresh no longer reports (e.g. the last remaining
            # element carrying a tag got re-tagged elsewhere). Keep them
            # visible at a count of 0 rather than dropping the group box --
            # the group box is the only in-drawer control that can clear
            # them, and current_filter() will otherwise keep reporting an
            # invisible, unclearable selection.
            selected = {v for (f, v) in self._state if f == facet}
            known = {str(v) for v in values}
            orphaned = selected - known
            if not values and not orphaned and facet not in ("type", "format"):
                continue
            box = QtWidgets.QGroupBox(facet.capitalize())
            vbox = QtWidgets.QVBoxLayout(box)
            display_items = list(values.items()) + [(v, 0) for v in orphaned]
            for value, count in sorted(display_items, key=lambda kv: str(kv[0])):
                row = self._make_row(facet, value, count)
                vbox.addWidget(row)
                self._checkboxes[(facet, str(value))] = row.checkbox
            self._layout.addWidget(box)
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

    def _sync_checkbox(self, key):
        """Reflect self._state.get(key) (or its absence) onto the rendered
        checkbox for key, if one is currently rendered, without emitting
        filter_changed. Shared by set_facets()'s post-rebuild restore and
        by set_value_state(), so a programmatic state change never leaves
        a visible checkbox stale."""
        cb = self._checkboxes.get(key)
        if cb is None:
            return
        qt_state = _STATE_TO_QT_CHECKSTATE.get(self._state.get(key), QtCore.Qt.Unchecked)
        cb.blockSignals(True)
        try:
            cb.setCheckState(qt_state)
        finally:
            cb.blockSignals(False)

    def _restore_checkbox_states(self):
        """Re-apply self._state onto the checkboxes set_facets() just
        rebuilt, without emitting filter_changed."""
        for key in self._checkboxes:
            self._sync_checkbox(key)

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
        # Keep a currently-rendered checkbox visually in sync -- guarded by
        # blockSignals inside _sync_checkbox so this doesn't double-emit;
        # the single emit below is the only one for this call.
        self._sync_checkbox(key)
        self.filter_changed.emit(self.current_filter())

    def current_filter(self):
        from filter_spec import empty_filter
        spec = empty_filter()
        # The "status" facet's two rows -- "active" and "deprecated" -- both
        # map onto the single is_deprecated flag and are mutually exclusive
        # filters on the same axis. Resolve them up front, before the
        # per-(facet, value) loop below, so the result never depends on
        # self._state's iteration/insertion order: if both rows are set at
        # once, "deprecated" wins, since asking to see deprecated assets is
        # the more specific of the two requests. Either row's state
        # (include or exclude) fully determines is_deprecated on its own --
        # "include deprecated"/"exclude active" both mean True, "exclude
        # deprecated"/"include active" both mean False.
        deprecated_state = self._state.get(("status", "deprecated"))
        active_state = self._state.get(("status", "active"))
        if deprecated_state is not None:
            spec["is_deprecated"] = (deprecated_state == "include")
        elif active_state is not None:
            spec["is_deprecated"] = (active_state == "exclude")

        for (facet, value), state in self._state.items():
            inc_key, exc_key = _FACET_KEYS[facet]
            if facet == "rating":
                if state == "include":
                    spec["rating_min"] = int(value)
                continue
            if facet == "status":
                continue
            target = inc_key if state == "include" else (exc_key or inc_key)
            if state == "exclude" and exc_key is None:
                continue
            coerced = int(value) if facet == "label" else value
            spec[target].append(coerced)
        return spec
