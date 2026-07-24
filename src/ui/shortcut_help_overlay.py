# -*- coding: utf-8 -*-
"""Keyboard shortcut help overlay (EP3).

Design SS3.3: a read-only cheat sheet, opened via `?` or Help > Keyboard
Shortcuts, listing every bound shortcut grouped by the menu it lives under.

`collect_shortcuts` keeps the flat `(label, key)` shape its callers/tests
depend on. Menu-grouping information is carried by the sibling
`collect_shortcuts_grouped`, which returns `(menu_title, label, key)`
triples; `ShortcutHelpOverlay` accepts either shape so a caller without
grouping info (e.g. a hand-built list of static keys) still renders fine,
with a blank "Menu" column for those rows.
"""

from PySide2 import QtWidgets, QtCore


def _walk_menu_actions(actions, group, pairs):
    """Depth-first walk of `actions`, recursing into submenus.

    Every bound leaf action is appended to `pairs` as `(group, label, key)`.
    `group` is carried through unchanged into nested submenus, so a shortcut
    three levels deep is still attributed to its top-level menu.
    """
    for a in actions:
        if a.menu():
            _walk_menu_actions(a.menu().actions(), group, pairs)
        elif a.text() and not a.shortcut().isEmpty():
            pairs.append((group, a.text().replace("&", ""), a.shortcut().toString()))


def collect_shortcuts_grouped(menu_bar):
    """Return `(menu_title, label, key)` for every action with a shortcut.

    `menu_title` is the top-level menu (e.g. "File", "View", "Help") the
    action lives under -- submenu items inherit their top-level ancestor's
    title. Actions with no shortcut set are skipped.
    """
    triples = []
    if menu_bar is not None:
        for top_action in menu_bar.actions():
            top_menu = top_action.menu()
            if not top_menu:
                continue
            top_title = top_action.text().replace("&", "")
            _walk_menu_actions(top_menu.actions(), top_title, triples)
    return triples


def collect_shortcuts(menu_bar):
    """Return (label, key) for every action with a shortcut."""
    return [(label, key) for (_group, label, key) in collect_shortcuts_grouped(menu_bar)]


class ShortcutHelpOverlay(QtWidgets.QDialog):
    """Read-only keyboard-shortcut cheat sheet.

    `shortcuts` is a list of entries, each either a 2-tuple `(label, key)`
    or a 3-tuple `(group, label, key)`; the two shapes may be mixed freely
    in the same list. The table always has a "Menu" column -- it is left
    blank for 2-tuple entries that carry no grouping information.
    """

    def __init__(self, shortcuts, parent=None):
        super(ShortcutHelpOverlay, self).__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(len(shortcuts), 3)
        self.table.setHorizontalHeaderLabels(["Menu", "Command", "Shortcut"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for row, entry in enumerate(shortcuts):
            if len(entry) == 3:
                group, label, key = entry
            else:
                group, label, key = "", entry[0], entry[1]
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(group))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(label))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(key))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        self.resize(480, 480)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super(ShortcutHelpOverlay, self).keyPressEvent(event)
