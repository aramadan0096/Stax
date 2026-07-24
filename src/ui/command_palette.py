# -*- coding: utf-8 -*-
"""Command palette: harvest live actions + a small extra-command registry (EP3)."""

import difflib

from PySide2 import QtWidgets, QtCore


def harvest_actions(menu_bar, toolbar):
    """Collect leaf (label, QAction) pairs from a menu bar and toolbar."""
    entries = []
    seen = set()

    def walk(actions):
        for a in actions:
            if a.isSeparator() or not a.text():
                continue
            sub = a.menu()
            if sub is not None:
                walk(sub.actions())
            elif id(a) not in seen:
                seen.add(id(a))
                entries.append((a.text().replace("&", ""), a))

    if menu_bar is not None:
        walk(menu_bar.actions())
    if toolbar is not None:
        walk(toolbar.actions())
    return entries


class CommandRegistry(object):
    """Extra palette commands: (label, callable)."""

    def __init__(self):
        self._items = []

    def register(self, label, callback):
        self._items.append((label, callback))

    def clear(self):
        self._items = []

    def entries(self):
        return list(self._items)


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
        self._visible = []
        self.filter_text("")
        self.resize(480, 360)

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
