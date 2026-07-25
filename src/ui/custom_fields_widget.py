# -*- coding: utf-8 -*-
"""Dynamic per-type custom metadata field editor (EP4)."""

from PySide2 import QtWidgets

from metadata_rules import coerce_to_text


class CustomFieldsWidget(QtWidgets.QWidget):
    def __init__(self, db, parent=None):
        super(CustomFieldsWidget, self).__init__(parent)
        self.db = db
        self._form = QtWidgets.QFormLayout(self)
        self.editors = {}       # field_key -> widget
        self._types = {}        # field_key -> field_type
        self._original_text = {}   # field_key -> text as initially displayed
        self._overridden = set()   # field_key that already had an explicit override

    def load(self, stack_fk, element_id):
        while self._form.rowCount():
            self._form.removeRow(0)
        self.editors = {}
        self._types = {}
        self._original_text = {}
        # element_metadata holds only EXPLICIT per-element overrides, as
        # opposed to get_effective_metadata() which also folds in inherited
        # stack/list defaults (EP4 I2 fix).
        self._overridden = set(
            self.db.get_element_metadata(element_id).keys()) if element_id else set()
        fields = self.db.get_metadata_fields(stack_fk)
        effective = self.db.get_effective_metadata(element_id) if element_id else {}
        for f in fields:
            key, ftype = f["key"], f["field_type"]
            self._types[key] = ftype
            val = effective.get(key)
            # TODO(EP4): render inherited as placeholder per spec Sec3.3
            editor = self._make_editor(ftype, f.get("choices") or [], val)
            self.editors[key] = editor
            self._form.addRow(f["label"] + ":", editor)
            self._original_text[key] = self._editor_text(key)

    def _make_editor(self, ftype, choices, value):
        if ftype == "bool":
            w = QtWidgets.QCheckBox()
            w.setChecked(value in (True, "1", 1, "true"))
            return w
        if ftype == "number":
            w = QtWidgets.QDoubleSpinBox()
            w.setRange(-1e9, 1e9)
            try:
                w.setValue(float(value))
            except (TypeError, ValueError):
                pass
            return w
        if ftype == "choice":
            w = QtWidgets.QComboBox()
            w.addItems([str(c) for c in choices])
            if value is not None:
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            return w
        w = QtWidgets.QLineEdit()
        if value is not None:
            w.setText(str(value))
        return w

    def _editor_text(self, key):
        w = self.editors[key]
        ftype = self._types[key]
        if ftype == "bool":
            return coerce_to_text("bool", w.isChecked())
        if ftype == "number":
            return coerce_to_text("number", w.value())
        if ftype == "choice":
            return w.currentText()
        return w.text()

    def values(self):
        return {k: self._editor_text(k) for k in self.editors}

    def commit(self, element_id):
        """Persist editor values, but only as genuine overrides (EP4 I2 fix).

        A field that is only DISPLAYING an inherited default (from
        get_effective_metadata) must not be frozen into a per-element
        override just because the dialog was saved -- only write it if it
        already had an explicit override, or the displayed text actually
        changed.
        """
        for key, text in self.values().items():
            if key in self._overridden or text != self._original_text.get(key):
                self.db.set_element_metadata(element_id, key, text)
