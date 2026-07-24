# -*- coding: utf-8 -*-
"""Command palette: harvest live actions + a small extra-command registry (EP3)."""

import difflib

from PySide2 import QtWidgets, QtCore


def harvest_actions(menu_bar, toolbar):
    """Collect leaf (label, QAction) pairs from a menu bar and toolbar.

    Only *enabled* actions are collected (spec Sec3.1: "each enabled,
    text-bearing QAction") -- a disabled QAction still has a leaf label,
    but running it from the palette would silently no-op, so it must not
    appear there at all (final whole-branch review "also fix").
    """
    entries = []
    seen = set()

    def walk(actions):
        for a in actions:
            if a.isSeparator() or not a.text():
                continue
            sub = a.menu()
            if sub is not None:
                walk(sub.actions())
            elif id(a) not in seen and a.isEnabled():
                seen.add(id(a))
                entries.append((a.text().replace("&", ""), a))

    if menu_bar is not None:
        walk(menu_bar.actions())
    if toolbar is not None:
        walk(toolbar.actions())
    return entries


def _subsequence(query, text):
    it = iter(text)
    return all(ch in it for ch in query)


def fuzzy_filter(query, labels):
    """Return indices of labels matching query, best match first."""
    q = (query or "").strip().lower()
    if not q:
        return list(range(len(labels)))
    scored = []
    for i, label in enumerate(labels):
        low = label.lower()
        if q in low:
            score = 100 - low.index(q)
        elif _subsequence(q, low):
            score = 50 * difflib.SequenceMatcher(None, q, low).ratio()
        else:
            continue
        scored.append((score, i))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [i for _, i in scored]


class CommandPalette(QtWidgets.QDialog):
    def __init__(self, entries, parent=None):
        super(CommandPalette, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup)
        # Repeated Ctrl+K opens must not accumulate hidden widgets for the
        # life of the app: close() destroys the dialog instead of just hiding it.
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._entries = list(entries)   # [(label, target)]
        layout = QtWidgets.QVBoxLayout(self)
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Type a command…")
        self.results_list = QtWidgets.QListWidget()
        layout.addWidget(self.search_box)
        layout.addWidget(self.results_list)
        self.search_box.textChanged.connect(self.filter_text)
        self.search_box.returnPressed.connect(self.run_current)
        self.results_list.itemActivated.connect(lambda _i: self.run_current())
        # Focus always lands in search_box (see MainWindow.open_command_palette),
        # so Up/Down must be caught there and translated into results_list
        # movement rather than relying on keyPressEvent/focus on the list itself.
        self.search_box.installEventFilter(self)
        self._visible = []
        self.filter_text("")
        self.resize(480, 360)

    def eventFilter(self, obj, event):
        if obj is self.search_box and event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            if key == QtCore.Qt.Key_Down:
                self._move_selection(1)
                return True
            if key == QtCore.Qt.Key_Up:
                self._move_selection(-1)
                return True
        return super(CommandPalette, self).eventFilter(obj, event)

    def _move_selection(self, delta):
        """Move results_list's current row by delta, clamped to [0, count-1].

        No-op when the list is empty (currentRow() stays -1).
        """
        count = self.results_list.count()
        if count == 0:
            return
        row = self.results_list.currentRow()
        new_row = min(max(row + delta, 0), count - 1)
        self.results_list.setCurrentRow(new_row)

    def filter_text(self, text):
        labels = [lbl for lbl, _ in self._entries]
        order = fuzzy_filter(text, labels)
        self.results_list.clear()
        self._visible = []
        for i in order:
            self.results_list.addItem(self._entries[i][0])
            self._visible.append(i)
        if self.results_list.count():
            self.results_list.setCurrentRow(0)

    def run_current(self):
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self._visible):
            return
        _, target = self._entries[self._visible[row]]
        self.close()
        if hasattr(target, "trigger"):
            target.trigger()
        else:
            target()


def build_jump_targets(db, config, on_list_selected, on_stack_selected):
    """Build "Go to list/stack" palette entries that always do something real.

    Returns a ``list[(label, callable)]`` in the same shape as
    ``harvest_actions()``, so callers can just concatenate them. (An earlier
    ``CommandRegistry`` class filled the same "extra commands" role but was
    never instantiated anywhere in production code -- this function covers
    the actual need, so ``CommandRegistry`` was deleted as dead code rather
    than wired up; final whole-branch review "also fix".)

    - One "Go to list: <stack name> / <list name>" entry per **top-level**
      list of every stack, targeting ``on_list_selected(list_id)``. Lists are
      nestable, but ``on_list_selected`` has no config gate and always
      navigates regardless of nesting depth, so only top-level lists are
      enumerated here to keep the palette flat and labels unambiguous —
      sub-lists are reachable by drilling in from their parent list in the
      normal UI.
    - One "Go to stack: <name>" entry per stack, targeting
      ``on_stack_selected(stack_id)`` — but **only** when
      ``config.get("show_entire_stack_elements", False)`` is true, since
      ``on_stack_selected`` is a silent no-op when that setting is off. A
      dead command must never appear in the palette.

    ``db`` is a ``DatabaseManager`` (``get_all_stacks()``,
    ``get_lists_by_stack(stack_id)``); ``config`` is anything with
    ``.get(key, default)`` (``src.config.Config`` or a test stub);
    ``on_list_selected``/``on_stack_selected`` are callables taking a single
    id argument (typically bound ``MainWindow`` methods).
    """
    entries = []
    show_stacks = config.get("show_entire_stack_elements", False)
    for stack in db.get_all_stacks():
        stack_id = stack["stack_id"]
        stack_name = stack["name"]
        if show_stacks:
            entries.append((
                "Go to stack: {}".format(stack_name),
                lambda sid=stack_id: on_stack_selected(sid),
            ))
        for lst in db.get_lists_by_stack(stack_id):
            list_id = lst["list_id"]
            entries.append((
                "Go to list: {} / {}".format(stack_name, lst["name"]),
                lambda lid=list_id: on_list_selected(lid),
            ))
    return entries
