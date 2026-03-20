# -*- coding: utf-8 -*-
"""
StaX — Batch Metadata Editor  (Feature 5)
==========================================
Lets the user update tags, type, list assignment, comment, and deprecation
status for multiple selected elements in a single operation.

Usage
-----
Trigger from MediaDisplayWidget's right-click context menu when 2+ items
are selected:

    from src.ui.batch_edit_dialog import BatchEditDialog

    selected_ids = self.gallery_view.get_selected_element_ids()
    if len(selected_ids) < 2:
        return

    dlg = BatchEditDialog(selected_ids, self.db, parent=self)
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        # Reload current list to reflect changes
        self.load_elements(self.current_list_id)

The dialog shows a checkbox next to each field.  Only checked fields are
written; unchecked fields are left untouched on all selected elements.
"""

from __future__ import absolute_import, unicode_literals

import logging

from PySide2 import QtWidgets, QtCore, QtGui

log = logging.getLogger(__name__)

# Available asset type choices — must match the Elements.type ENUM
ASSET_TYPES = ["2D", "3D", "Toolset"]


class _FieldRow(QtWidgets.QWidget):
    """
    A row in the batch editor consisting of:
      [checkbox]  [label]  [editor widget]
    """

    def __init__(self, label, widget, parent=None):
        super(_FieldRow, self).__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setToolTip("Check to apply this field to all selected elements")
        self.checkbox.stateChanged.connect(
            lambda s: widget.setEnabled(s == QtCore.Qt.Checked)
        )

        lbl = QtWidgets.QLabel(label)
        lbl.setMinimumWidth(90)

        widget.setEnabled(False)
        self.editor = widget

        layout.addWidget(self.checkbox)
        layout.addWidget(lbl)
        layout.addWidget(self.editor, 1)

    @property
    def is_active(self):
        return self.checkbox.isChecked()

    def value(self):
        w = self.editor
        if isinstance(w, QtWidgets.QComboBox):
            return w.currentText()
        if isinstance(w, QtWidgets.QCheckBox):
            return w.isChecked()
        if isinstance(w, QtWidgets.QLineEdit):
            return w.text().strip()
        if isinstance(w, QtWidgets.QPlainTextEdit):
            return w.toPlainText().strip()
        return None


class BatchEditDialog(QtWidgets.QDialog):
    """
    Modal dialog for batch-editing metadata on multiple Elements.

    Parameters
    ----------
    element_ids : list[int]
    db          : DatabaseManager
    parent      : QWidget or None
    """

    def __init__(self, element_ids, db, parent=None):
        super(BatchEditDialog, self).__init__(parent)
        self.element_ids = list(element_ids)
        self.db          = db

        self.setWindowTitle(
            "Batch Edit — {} elements".format(len(self.element_ids))
        )
        self.setMinimumWidth(480)
        self.setModal(True)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QtWidgets.QLabel(
            "<b>Editing {} elements.</b><br>"
            "Check a field to apply it to all selected elements.  "
            "Unchecked fields are left unchanged.".format(len(self.element_ids))
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(self._hline())

        # --- Field rows -------------------------------------------------
        form = QtWidgets.QWidget()
        form_layout = QtWidgets.QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)

        # Tags
        self._tags_edit = QtWidgets.QLineEdit()
        self._tags_edit.setPlaceholderText(
            "Comma-separated tags, e.g.: fire, explosion, 4k"
        )
        self._tags_row = _FieldRow("Tags", self._tags_edit)

        # Tag mode (replace vs append)
        self._tag_mode_combo = QtWidgets.QComboBox()
        self._tag_mode_combo.addItems(["Replace existing tags", "Append to existing tags"])
        self._tag_mode_combo.setEnabled(False)
        self._tags_row.checkbox.stateChanged.connect(
            lambda s: self._tag_mode_combo.setEnabled(s == QtCore.Qt.Checked)
        )

        # Asset type
        self._type_combo = QtWidgets.QComboBox()
        self._type_combo.addItems(ASSET_TYPES)
        self._type_row = _FieldRow("Asset type", self._type_combo)

        # Comment
        self._comment_edit = QtWidgets.QPlainTextEdit()
        self._comment_edit.setMaximumHeight(70)
        self._comment_edit.setPlaceholderText("Comment applied to all selected elements")
        self._comment_row = _FieldRow("Comment", self._comment_edit)

        # Deprecated
        self._depr_check = QtWidgets.QCheckBox("Mark as deprecated")
        self._depr_row = _FieldRow("Status", self._depr_check)

        # Move to list
        self._list_combo = QtWidgets.QComboBox()
        self._populate_lists()
        self._list_row = _FieldRow("Move to list", self._list_combo)

        form_layout.addWidget(self._tags_row)

        tag_mode_row = QtWidgets.QHBoxLayout()
        tag_mode_row.addSpacing(108)
        tag_mode_row.addWidget(self._tag_mode_combo)
        form_layout.addLayout(tag_mode_row)

        form_layout.addWidget(self._type_row)
        form_layout.addWidget(self._comment_row)
        form_layout.addWidget(self._depr_row)
        form_layout.addWidget(self._list_row)

        layout.addWidget(form)

        # Preview of selected elements
        layout.addWidget(self._hline())
        self._preview_label = QtWidgets.QLabel(
            self._build_preview_text()
        )
        self._preview_label.setWordWrap(True)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self._preview_label)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(100)
        layout.addWidget(scroll)

        # Buttons
        layout.addWidget(self._hline())
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Apply |
            QtWidgets.QDialogButtonBox.Cancel
        )
        apply_btn = btn_box.button(QtWidgets.QDialogButtonBox.Apply)
        apply_btn.setText("Apply to {} elements".format(len(self.element_ids)))
        apply_btn.clicked.connect(self._apply)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _hline(self):
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        return line

    def _populate_lists(self):
        """Populate the move-to-list combo with all available lists."""
        try:
            stacks = self.db.get_all_stacks()
            self._list_combo.addItem("— select a list —", None)
            for stack in stacks:
                sid = stack["stack_id"]
                lists = self.db.get_lists_by_stack(sid)
                for lst in lists:
                    label = "{}  /  {}".format(
                        stack.get("name", ""), lst.get("name", "")
                    )
                    self._list_combo.addItem(label, lst["list_id"])
        except Exception as exc:
            log.warning("BatchEditDialog: could not load lists: %s", exc)

    def _build_preview_text(self):
        """Return a compact comma-joined preview of selected element names."""
        try:
            elements = [
                self.db.get_element_by_id(eid) for eid in self.element_ids[:20]
            ]
            names = [
                e["name"] for e in elements if e is not None
            ]
            suffix = (
                " … and {} more".format(len(self.element_ids) - 20)
                if len(self.element_ids) > 20
                else ""
            )
            return "<b>Selected:</b> " + ", ".join(names) + suffix
        except Exception:
            return "<b>Selected:</b> {} elements".format(len(self.element_ids))

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _apply(self):
        changes = self._collect_changes()

        if not changes:
            QtWidgets.QMessageBox.information(
                self, "Nothing to apply",
                "Please check at least one field to apply."
            )
            return

        # Confirm
        field_names = list(changes.keys())
        msg = (
            "Apply changes to {} fields on {} elements?\n\n"
            "Fields: {}".format(
                len(field_names),
                len(self.element_ids),
                ", ".join(field_names),
            )
        )
        if QtWidgets.QMessageBox.question(
            self, "Confirm Batch Edit", msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        ) != QtWidgets.QMessageBox.Yes:
            return

        # Write
        errors = []
        progress = QtWidgets.QProgressDialog(
            "Updating elements…", "Cancel", 0, len(self.element_ids), self
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)

        for i, eid in enumerate(self.element_ids):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            try:
                self._write_element(eid, changes)
            except Exception as exc:
                errors.append("Element {}: {}".format(eid, exc))

        progress.setValue(len(self.element_ids))

        if errors:
            QtWidgets.QMessageBox.warning(
                self, "Partial Failure",
                "Some elements could not be updated:\n" + "\n".join(errors[:10])
            )

        log.info(
            "BatchEdit: applied %d field(s) to %d element(s).",
            len(changes), len(self.element_ids)
        )
        self.accept()

    def _collect_changes(self):
        """Return a dict of {field: value} for all checked, active rows."""
        changes = {}

        if self._tags_row.is_active:
            raw_tags = self._tags_row.value()
            tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
            changes["tags"] = {
                "values":  tags_list,
                "mode":    self._tag_mode_combo.currentIndex(),  # 0=replace, 1=append
            }

        if self._type_row.is_active:
            changes["type"] = self._type_row.value()

        if self._comment_row.is_active:
            changes["comment"] = self._comment_row.value()

        if self._depr_row.is_active:
            changes["is_deprecated"] = self._depr_check.isChecked()

        if self._list_row.is_active:
            list_id = self._list_combo.currentData()
            if list_id is not None:
                changes["list_fk"] = list_id

        return changes

    def _write_element(self, element_id, changes):
        """Apply *changes* to a single element via db_manager."""
        elem = self.db.get_element_by_id(element_id)
        if elem is None:
            return

        kwargs = {}

        if "tags" in changes:
            spec = changes["tags"]
            if spec["mode"] == 1:   # append
                existing = [
                    t.strip()
                    for t in (elem.get("tags") or "").split(",")
                    if t.strip()
                ]
                merged = existing + [
                    t for t in spec["values"] if t not in existing
                ]
                kwargs["tags"] = ", ".join(merged)
            else:
                kwargs["tags"] = ", ".join(spec["values"])

        for field in ("type", "comment", "is_deprecated", "list_fk"):
            if field in changes:
                kwargs[field] = changes[field]

        if kwargs:
            self.db.update_element_metadata(element_id, **kwargs)
