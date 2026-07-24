import pytest
from PySide2 import QtWidgets

from ui.command_palette import harvest_actions, CommandRegistry, fuzzy_filter


@pytest.mark.gui
def test_harvest_collects_leaf_actions(qtbot):
    bar = QtWidgets.QMenuBar()
    file_menu = bar.addMenu("File")
    a_ingest = file_menu.addAction("Ingest Files")
    file_menu.addSeparator()
    a_exit = file_menu.addAction("Exit")
    toolbar = QtWidgets.QToolBar()
    a_search = toolbar.addAction("Search")

    entries = harvest_actions(bar, toolbar)
    labels = [label for label, _ in entries]
    assert "Ingest Files" in labels and "Exit" in labels and "Search" in labels
    assert "File" not in labels  # submenu parents excluded


@pytest.mark.unit
def test_registry_and_fuzzy():
    reg = CommandRegistry()
    reg.register("Go to stack: Plates", lambda: None)
    assert reg.entries()[0][0] == "Go to stack: Plates"
    order = fuzzy_filter("exit", ["Ingest Files", "Exit", "Advanced Search"])
    assert order[0] == 1  # 'Exit' ranks first
