import pytest
from PySide2 import QtCore, QtGui, QtTest, QtWidgets

from ui.shortcut_help_overlay import ShortcutHelpOverlay, collect_shortcuts


@pytest.mark.gui
def test_collect_and_render(qtbot):
    bar = QtWidgets.QMenuBar()
    m = bar.addMenu("File")
    act = m.addAction("Ingest Files")
    act.setShortcut("Ctrl+I")
    pairs = collect_shortcuts(bar)
    assert ("Ingest Files", "Ctrl+I") in pairs
    ov = ShortcutHelpOverlay(pairs + [("Command palette", "Ctrl+K")])
    qtbot.addWidget(ov)
    assert ov.table.rowCount() == len(pairs) + 1


# ---------------------------------------------------------------------------
# collect_shortcuts must recurse into submenus and skip actions with no
# shortcut set -- otherwise the cheat sheet silently omits nested commands
# or pollutes itself with unbound entries.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_collect_shortcuts_recurses_into_submenus_and_skips_unbound(qtbot):
    bar = QtWidgets.QMenuBar()
    top = bar.addMenu("View")
    bound = top.addAction("History Panel")
    bound.setShortcut("Ctrl+2")
    unbound = top.addAction("No Shortcut Here")
    # unbound has no shortcut set at all -- default is empty.

    sub = top.addMenu("Nested")
    nested_bound = sub.addAction("Deep Action")
    nested_bound.setShortcut("Ctrl+Shift+D")
    nested_unbound = sub.addAction("Deep No Shortcut")

    pairs = collect_shortcuts(bar)

    assert ("History Panel", "Ctrl+2") in pairs
    assert ("Deep Action", "Ctrl+Shift+D") in pairs
    assert not any(label == "No Shortcut Here" for label, _key in pairs)
    assert not any(label == "Deep No Shortcut" for label, _key in pairs)


# ---------------------------------------------------------------------------
# Design SS3.3 requires the cheat sheet to be grouped by menu. collect_shortcuts
# itself must keep returning flat (label, key) pairs (the brief's test above
# depends on that exact shape), so grouping is carried by a sibling function,
# collect_shortcuts_grouped, returning (group, label, key) triples that
# ShortcutHelpOverlay renders into a third "Menu" column.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_grouped_shortcuts_expose_menu_column_in_table(qtbot):
    from ui.shortcut_help_overlay import collect_shortcuts_grouped

    bar = QtWidgets.QMenuBar()
    file_menu = bar.addMenu("File")
    ingest = file_menu.addAction("Ingest Files")
    ingest.setShortcut("Ctrl+I")

    view_menu = bar.addMenu("View")
    history = view_menu.addAction("History Panel")
    history.setShortcut("Ctrl+2")

    triples = collect_shortcuts_grouped(bar)
    assert ("File", "Ingest Files", "Ctrl+I") in triples
    assert ("View", "History Panel", "Ctrl+2") in triples

    ov = ShortcutHelpOverlay(triples)
    qtbot.addWidget(ov)
    assert ov.table.rowCount() == len(triples)
    assert ov.table.columnCount() == 3

    menu_column_values = {
        ov.table.item(row, 0).text() for row in range(ov.table.rowCount())
    }
    assert "File" in menu_column_values
    assert "View" in menu_column_values

    # Plain 2-tuples (as produced by collect_shortcuts / the brief's test)
    # must still render without error, with a blank Menu column.
    ov2 = ShortcutHelpOverlay([("Command palette", "Ctrl+K")])
    qtbot.addWidget(ov2)
    assert ov2.table.item(0, 0).text() == ""
    assert ov2.table.item(0, 1).text() == "Command palette"
    assert ov2.table.item(0, 2).text() == "Ctrl+K"


# ---------------------------------------------------------------------------
# Read-only + Esc closes (design SS3.3). Uses a real key event, not a direct
# keyPressEvent() call, so it also proves Qt's own event dispatch reaches
# the override.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_escape_closes_dialog(qtbot):
    ov = ShortcutHelpOverlay([("Command palette", "Ctrl+K")])
    qtbot.addWidget(ov)
    ov.show()
    assert ov.isVisible()

    QtTest.QTest.keyClick(ov, QtCore.Qt.Key_Escape)

    assert not ov.isVisible()


@pytest.mark.gui
def test_table_is_read_only(qtbot):
    ov = ShortcutHelpOverlay([("Command palette", "Ctrl+K")])
    qtbot.addWidget(ov)
    assert ov.table.editTriggers() == QtWidgets.QAbstractItemView.NoEditTriggers


@pytest.mark.gui
def test_empty_shortcut_list_renders_empty_table(qtbot):
    ov = ShortcutHelpOverlay([])
    qtbot.addWidget(ov)
    assert ov.table.rowCount() == 0
