import pytest
from PySide2 import QtCore, QtWidgets
from PySide2.QtTest import QTest

from ui.command_palette import CommandPalette


@pytest.mark.gui
def test_filter_and_run(qtbot):
    fired = {"n": 0}
    entries = [
        ("Ingest Files", lambda: fired.__setitem__("n", fired["n"] + 1)),
        ("Exit", lambda: None),
    ]
    pal = CommandPalette(entries)
    qtbot.addWidget(pal)
    pal.filter_text("ingest")
    assert pal.results_list.count() == 1
    pal.results_list.setCurrentRow(0)
    pal.run_current()
    assert fired["n"] == 1


@pytest.mark.gui
def test_arrow_keys_move_selection_via_real_key_events(qtbot):
    entries = [
        ("Alpha", lambda: None),
        ("Bravo", lambda: None),
        ("Charlie", lambda: None),
    ]
    pal = CommandPalette(entries)
    qtbot.addWidget(pal)
    pal.search_box.setFocus()
    assert pal.results_list.currentRow() == 0

    # Down moves forward.
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Down)
    assert pal.results_list.currentRow() == 1
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Down)
    assert pal.results_list.currentRow() == 2

    # Clamp at the bottom — no row past the last item.
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Down)
    assert pal.results_list.currentRow() == 2

    # Up moves back.
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Up)
    assert pal.results_list.currentRow() == 1
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Up)
    assert pal.results_list.currentRow() == 0

    # Clamp at the top — no negative row.
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Up)
    assert pal.results_list.currentRow() == 0


@pytest.mark.gui
def test_arrow_keys_are_noop_on_empty_results(qtbot):
    entries = [("Alpha", lambda: None)]
    pal = CommandPalette(entries)
    qtbot.addWidget(pal)
    pal.filter_text("nomatch")
    assert pal.results_list.count() == 0

    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Down)
    assert pal.results_list.currentRow() == -1
    QTest.keyClick(pal.search_box, QtCore.Qt.Key_Up)
    assert pal.results_list.currentRow() == -1
