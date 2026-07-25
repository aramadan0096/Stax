# -*- coding: utf-8 -*-
"""Persistent editable inspector for the selected element (EP3 Task 6).

Sits below the preview pane, in a vertical splitter with
``VideoPlayerWidget``, and reflects/edits the single currently-selected
element: read-only Type/Format/Frames/Size (via the shared
``element_field_rows`` formatter), plus editable Name/Tags/Comment/Rating/
Label that commit straight to the DB.
"""

import logging

from PySide2 import QtWidgets, QtCore

from src.ui.custom_fields_widget import CustomFieldsWidget
from src.ui.metadata_format import element_field_rows

logger = logging.getLogger(__name__)

_READONLY_LABELS = ("Type", "Format", "Frames", "Size")


class InspectorPanel(QtWidgets.QWidget):
    """Editable inspector bound to a single element.

    ``show_element(element_id)`` is a pure display operation -- it never
    writes to the DB, even though the rating spinbox and label combo are
    also wired to DB-writing slots for user edits. That is achieved by
    blocking each widget's signals while it is being populated.
    """

    # Emitted with the element_id after a rating/label/name/tags/comment
    # edit commits successfully, so the gallery/table grid can repaint
    # that one item's badge, caption, and table row in place (design
    # SS3.4). _commit_name/_commit_tags/_commit_comment emit this too --
    # not just the rating/label widgets -- since a stale gallery caption
    # or table cell is just as much a visible desync as a stale badge.
    element_updated = QtCore.Signal(int)

    # Emitted with the *other* element_id when a Related-list entry is
    # activated (double-click / Enter), so the main window can route it
    # through its normal element-select path (EP4 Task 15).
    related_activated = QtCore.Signal(int)

    def __init__(self, db, parent=None):
        super(InspectorPanel, self).__init__(parent)
        self.db = db
        self._element_id = None

        form = QtWidgets.QFormLayout(self)

        self.readonly_labels = {}
        for label in _READONLY_LABELS:
            w = QtWidgets.QLabel("")
            self.readonly_labels[label] = w
            form.addRow(label + ":", w)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.editingFinished.connect(self._commit_name)
        form.addRow("Name:", self.name_edit)

        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.editingFinished.connect(self._commit_tags)
        form.addRow("Tags:", self.tags_edit)

        self.comment_edit = QtWidgets.QLineEdit()
        self.comment_edit.editingFinished.connect(self._commit_comment)
        form.addRow("Comment:", self.comment_edit)

        self.rating_spin = QtWidgets.QSpinBox()
        self.rating_spin.setRange(0, 5)
        self.rating_spin.valueChanged.connect(self.set_rating)
        form.addRow("Rating:", self.rating_spin)

        self.label_combo = QtWidgets.QComboBox()
        self.label_combo.currentIndexChanged.connect(self._commit_label)
        form.addRow("Label:", self.label_combo)
        self._reload_labels()

        # Custom fields (EP4) -- dynamic per-stack metadata fields, shown as
        # a full-width collapsible-looking group below the fixed fields
        # above. Additive: Task 15 adds a "Related" section the same way.
        custom_fields_group = QtWidgets.QGroupBox("Custom Fields")
        custom_fields_layout = QtWidgets.QVBoxLayout(custom_fields_group)
        self.custom_fields_widget = CustomFieldsWidget(self.db)
        custom_fields_layout.addWidget(self.custom_fields_widget)
        form.addRow(custom_fields_group)

        # Related elements (EP4 Task 14/15) -- shows both directions of
        # element_relationships for the current element (this element as
        # either the "from" or the "to" side), added the same additive way
        # as the Custom Fields group above so both coexist.
        related_group = QtWidgets.QGroupBox("Related")
        related_layout = QtWidgets.QVBoxLayout(related_group)
        self.related_list = QtWidgets.QListWidget()
        self.related_list.itemActivated.connect(self._on_related_activated)
        related_layout.addWidget(self.related_list)
        self.link_related_btn = QtWidgets.QPushButton("Link selected…")
        self.link_related_btn.clicked.connect(self._link_selected)
        related_layout.addWidget(self.link_related_btn)
        form.addRow(related_group)

        # Constructed last, once every widget referenced below exists.
        self.clear()

    # -------------------------------------------------------------------
    # Display
    # -------------------------------------------------------------------

    def _reload_labels(self):
        """Repopulate the label combo from the DB.

        Cheap (one indexed SELECT) and safe to call every time an element
        is shown, so labels created after construction (e.g. via the EP1
        admin Labels settings tab) still appear.
        """
        current_data = self.label_combo.currentData() if self.label_combo.count() else None
        self.label_combo.blockSignals(True)
        try:
            self.label_combo.clear()
            self.label_combo.addItem("(none)", None)
            for lbl in self.db.get_labels():
                self.label_combo.addItem(lbl["name"], lbl["label_id"])
            idx = self.label_combo.findData(current_data)
            self.label_combo.setCurrentIndex(max(0, idx))
        finally:
            self.label_combo.blockSignals(False)

    def clear(self):
        """Reset to the empty "no selection" state: disabled, no stale text."""
        self._element_id = None
        for w in self.readonly_labels.values():
            w.setText("")
        self.name_edit.setText("")
        self.tags_edit.setText("")
        self.comment_edit.setText("")
        self.rating_spin.blockSignals(True)
        self.rating_spin.setValue(0)
        self.rating_spin.blockSignals(False)
        self.label_combo.blockSignals(True)
        self.label_combo.setCurrentIndex(0)
        self.label_combo.blockSignals(False)
        self.custom_fields_widget.load(stack_fk=None, element_id=None)
        self.related_list.clear()
        self.setEnabled(False)

    def show_element(self, element_id):
        """Populate every field from the DB for *element_id*.

        Pure display: widget signals are blocked while populating so the
        rating spinbox / label combo don't fire their DB-writing slots
        just from being set programmatically, and so a spurious write
        can never land on the *previous* element while widgets still
        reflect it mid-update.
        """
        el = self.db.get_element_by_id(element_id)
        if not el:
            self.clear()
            return

        # Refresh labels (cheap) before populating so a freshly-created
        # label is selectable even on the very first show.
        self._reload_labels()

        # Only bind to the new element once every field has actually been
        # populated below, so no partially-updated state is ever visible
        # under self._element_id.
        self.setEnabled(True)

        for label, value in element_field_rows(el):
            if label in self.readonly_labels:
                self.readonly_labels[label].setText(str(value))
            elif label == "Name":
                self.name_edit.setText(str(value))
        self.tags_edit.setText(el.get("tags") or "")
        self.comment_edit.setText(el.get("comment") or "")

        self.rating_spin.blockSignals(True)
        self.rating_spin.setValue(el.get("rating") or 0)
        self.rating_spin.blockSignals(False)

        self.label_combo.blockSignals(True)
        idx = self.label_combo.findData(el.get("label_fk"))
        self.label_combo.setCurrentIndex(max(0, idx))
        self.label_combo.blockSignals(False)

        self._load_custom_fields(el, element_id)
        self._load_related(element_id)

        self._element_id = element_id

    def _load_custom_fields(self, el, element_id):
        """Populate the Custom Fields section for *el*.

        Never raises: an element whose stack can't be resolved, or has no
        custom fields defined, just leaves the section empty rather than
        breaking the rest of show_element().
        """
        try:
            stack_fk = None
            list_fk = el.get("list_fk")
            if list_fk:
                list_row = self.db.get_list_by_id(list_fk)
                stack_fk = list_row.get("stack_fk") if list_row else None
            self.custom_fields_widget.load(stack_fk=stack_fk, element_id=element_id)
        except Exception:
            logger.exception(
                "InspectorPanel: failed to load custom fields for element %s",
                element_id,
            )
            self.custom_fields_widget.load(stack_fk=None, element_id=None)

    def _load_related(self, element_id):
        """Populate the Related list for *element_id* from both directions
        of ``element_relationships`` (EP4 Task 14: a relationship row can
        have *element_id* on either the "from" or the "to" side).

        Never raises: same defensive shape as ``_load_custom_fields`` --
        a lookup failure just leaves the section empty.
        """
        self.related_list.clear()
        try:
            for rel in self.db.get_relationships(element_id):
                other_id = (
                    rel["to_element_fk"]
                    if rel["from_element_fk"] == element_id
                    else rel["from_element_fk"]
                )
                other = self.db.get_element_by_id(other_id)
                if other:
                    item = QtWidgets.QListWidgetItem(
                        "{} ({})".format(other["name"], rel["rel_type"]))
                    item.setData(QtCore.Qt.UserRole, other_id)
                    self.related_list.addItem(item)
        except Exception:
            logger.exception(
                "InspectorPanel: failed to load relationships for element %s",
                element_id,
            )
            self.related_list.clear()

    def _on_related_activated(self, item):
        other_id = item.data(QtCore.Qt.UserRole)
        if other_id is not None:
            self.related_activated.emit(other_id)

    def _link_selected(self):
        """Prompt for a target element id and relationship type, then link
        the currently-inspected element to it via ``add_relationship``.

        A lightweight two-prompt flow (element id + free-text rel type)
        rather than a full picker dialog -- there is no gallery-selection
        channel wired into InspectorPanel yet, so the "selected" element is
        whatever id the user enters here.
        """
        if self._element_id is None:
            return
        other_id, ok = QtWidgets.QInputDialog.getInt(
            self, "Link selected…", "Other element id:", minValue=1)
        if not ok:
            return
        rel_type, ok = QtWidgets.QInputDialog.getText(
            self, "Link selected…", "Relationship type:", text="related_to")
        if not ok or not rel_type:
            return
        try:
            self.db.add_relationship(self._element_id, other_id, rel_type)
        except Exception:
            logger.exception(
                "InspectorPanel: failed to add relationship %s -> %s (%s)",
                self._element_id, other_id, rel_type,
            )
            return
        self._load_related(self._element_id)

    # -------------------------------------------------------------------
    # Commit-on-edit handlers
    # -------------------------------------------------------------------

    def _commit_name(self):
        if self._element_id is not None:
            element_id = self._element_id
            if self._safe_update(name=self.name_edit.text()):
                self.element_updated.emit(element_id)

    def _commit_tags(self):
        if self._element_id is not None:
            element_id = self._element_id
            if self._safe_update(tags=self.tags_edit.text()):
                self.element_updated.emit(element_id)

    def _commit_comment(self):
        if self._element_id is not None:
            element_id = self._element_id
            if self._safe_update(comment=self.comment_edit.text()):
                self.element_updated.emit(element_id)

    def _safe_update(self, **kwargs):
        """Write `kwargs` to the current element. Returns True on success,
        False (after logging) on failure -- callers use this to decide
        whether to emit `element_updated` (whole-branch review Finding 3:
        name/tags/comment commits didn't emit it at all before, leaving
        the gallery caption and table Name/Comment cells stale)."""
        try:
            self.db.update_element(self._element_id, **kwargs)
        except Exception:
            logger.exception(
                "InspectorPanel: failed to update element %s with %s",
                self._element_id, kwargs,
            )
            return False
        return True

    def set_rating(self, value):
        if self._element_id is None:
            return
        try:
            self.db.set_element_rating(self._element_id, value)
        except Exception:
            logger.exception(
                "InspectorPanel: failed to set rating %s on element %s",
                value, self._element_id,
            )
        else:
            self.element_updated.emit(self._element_id)

    def _commit_label(self, _index):
        if self._element_id is None:
            return
        element_id = self._element_id
        try:
            self.db.set_element_label(element_id, self.label_combo.currentData())
        except Exception:
            logger.exception(
                "InspectorPanel: failed to set label on element %s", element_id,
            )
        else:
            self.element_updated.emit(element_id)
