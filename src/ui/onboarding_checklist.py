# -*- coding: utf-8 -*-
"""First-run onboarding checklist (EP3, design SS3.8).

`OnboardingChecklist` is a small, dismissible "Getting started" panel shown
on first run and re-openable from the Help menu. It lists three steps:

    * Create a stack
    * Ingest files
    * Insert into Nuke

Each step's done-check is *derived live from DB state* on every call to
`step_states()` -- nothing is cached on the instance and nothing but
`onboarding_dismissed` is ever written to `Config`:

    * "Create a stack"    -> `db.get_all_stacks()` is non-empty.
    * "Ingest files"      -> at least one non-deprecated element exists in
                              any top-level list of any stack
                              (`db.get_lists_by_stack` + `db.get_elements_count`).
    * "Insert into Nuke"  -> `db.get_total_insertions() > 0` (a row exists in
                              `insertion_log`, i.e. an insertion actually
                              happened -- never a stored config flag).

The widget stays decoupled from `MainWindow`: rather than importing or
calling into the host window, it exposes an `action_requested(str)` Qt
signal that fires the step name when that step's one-click action button is
clicked. The host (main.py) connects the signal and performs the real
action (open the "Add Stack" dialog, open the ingest file picker, ...).

"Insert into Nuke" intentionally has no action button: inserting requires a
specific selected element, and there is no generic single click that can
perform that without a target, so no button is created for it rather than
shipping a dead one.
"""

from __future__ import absolute_import, unicode_literals

import logging

from PySide2 import QtCore, QtWidgets

log = logging.getLogger(__name__)

# Steps that get a one-click action button, mapped to the button's label.
# "Insert into Nuke" is deliberately absent -- see module docstring.
_ACTIONABLE_STEPS = (
    ("Create a stack", "Create Stack..."),
    ("Ingest files", "Ingest Files..."),
)

_ALL_STEPS = ("Create a stack", "Ingest files", "Insert into Nuke")


class OnboardingChecklist(QtWidgets.QWidget):
    """First-run "Getting started" checklist.

    Signals
    -------
    action_requested(str)
        Emitted with the step name when that step's one-click action button
        is clicked. The host is responsible for wiring this to a real
        entry point (e.g. `stacks_panel.add_stack`, `ingest_files`).
    """

    action_requested = QtCore.Signal(str)

    def __init__(self, db, config, parent=None):
        super(OnboardingChecklist, self).__init__(parent)
        self.db = db
        self.config = config

        self.setWindowTitle("Getting Started")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Getting started</b>"))

        self._checks = {}
        self.action_buttons = {}
        actionable = dict(_ACTIONABLE_STEPS)

        for step in _ALL_STEPS:
            row = QtWidgets.QHBoxLayout()
            cb = QtWidgets.QCheckBox(step)
            cb.setEnabled(False)
            self._checks[step] = cb
            row.addWidget(cb)

            if step in actionable:
                btn = QtWidgets.QPushButton(actionable[step])
                btn.clicked.connect(
                    lambda checked=False, s=step: self.action_requested.emit(s)
                )
                self.action_buttons[step] = btn
                row.addWidget(btn)
            else:
                hint = QtWidgets.QLabel("(double-click an element to insert)")
                hint.setEnabled(False)
                row.addWidget(hint)

            row.addStretch(1)
            layout.addLayout(row)

        self.dismiss_button = QtWidgets.QPushButton("Dismiss")
        self.dismiss_button.clicked.connect(self.dismiss)
        layout.addWidget(self.dismiss_button)

        self.refresh()

    # -------------------------------------------------------------------
    # State
    # -------------------------------------------------------------------

    def step_states(self):
        """Recompute and return {step_name: done} live from the DB.

        Nothing is cached: every call re-reads the DB so the checklist
        reflects the current state, including changes made after the
        widget was constructed.
        """
        has_stack = self._has_any_stack()
        has_element = self._has_any_element()
        has_insertion = self._has_any_insertion()
        return {
            "Create a stack": has_stack,
            "Ingest files": has_element,
            "Insert into Nuke": has_insertion,
        }

    def _has_any_stack(self):
        try:
            stacks = self.db.get_all_stacks()
        except Exception:
            log.warning("onboarding: get_all_stacks failed", exc_info=True)
            return False
        return len(stacks) > 0

    def _has_any_element(self):
        """True as soon as one non-deprecated element is found anywhere.

        Scans stacks -> top-level lists -> element count, short-circuiting
        the moment a non-empty list is found (O(stacks x lists) worst case,
        acceptable because this only matters on a near-empty first-run DB).

        Note: `get_lists_by_stack(stack_id)` defaults to top-level lists
        only. Lists are nestable, so an element filed only inside a
        sub-list is not counted here. This is a deliberate simplification
        for a first-run checklist (see module docstring / task report) --
        it is not a full recursive scan.

        Only the DB calls are guarded, and only the failing stack/list is
        skipped (with a logged warning) -- a broken query does not silently
        report "no elements" for the whole DB.
        """
        try:
            stacks = self.db.get_all_stacks()
        except Exception:
            log.warning("onboarding: get_all_stacks failed", exc_info=True)
            return False

        for stack in stacks:
            stack_id = stack.get("stack_id")
            try:
                lists = self.db.get_lists_by_stack(stack_id)
            except Exception:
                log.warning(
                    "onboarding: get_lists_by_stack failed for stack %r",
                    stack_id, exc_info=True,
                )
                continue
            for lst in lists:
                list_id = lst.get("list_id")
                try:
                    count = self.db.get_elements_count(list_id)
                except Exception:
                    log.warning(
                        "onboarding: get_elements_count failed for list %r",
                        list_id, exc_info=True,
                    )
                    continue
                if count > 0:
                    return True
        return False

    def _has_any_insertion(self):
        try:
            return self.db.get_total_insertions() > 0
        except Exception:
            log.warning("onboarding: get_total_insertions failed", exc_info=True)
            return False

    def refresh(self):
        """Re-read DB state and update the checkbox display."""
        for step, done in self.step_states().items():
            self._checks[step].setChecked(done)

    # -------------------------------------------------------------------
    # Dismissal
    # -------------------------------------------------------------------

    def dismiss(self):
        """Mark the checklist dismissed (persisted) and hide the widget.

        Only `onboarding_dismissed` is ever written to Config -- per-step
        completion is derived, never stored.
        """
        self.config.set("onboarding_dismissed", True)
        self.hide()
