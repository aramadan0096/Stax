import pytest
from PySide2 import QtWidgets

from ui.command_palette import harvest_actions, fuzzy_filter


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


@pytest.mark.gui
def test_harvest_excludes_disabled_actions(qtbot):
    """Final whole-branch review 'also fix': spec Sec3.1 requires each
    palette entry to be an "enabled, text-bearing QAction" -- a disabled
    command must not appear (it would silently no-op if run)."""
    bar = QtWidgets.QMenuBar()
    file_menu = bar.addMenu("File")
    a_ingest = file_menu.addAction("Ingest Files")
    a_disabled = file_menu.addAction("Locked Feature")
    a_disabled.setEnabled(False)
    toolbar = QtWidgets.QToolBar()
    a_search = toolbar.addAction("Search")
    a_disabled_tool = toolbar.addAction("Disabled Tool")
    a_disabled_tool.setEnabled(False)

    entries = harvest_actions(bar, toolbar)
    labels = [label for label, _ in entries]
    assert "Ingest Files" in labels and "Search" in labels
    assert "Locked Feature" not in labels
    assert "Disabled Tool" not in labels


@pytest.mark.unit
def test_fuzzy_filter_ranks_prefix_match_first():
    order = fuzzy_filter("exit", ["Ingest Files", "Exit", "Advanced Search"])
    assert order[0] == 1  # 'Exit' ranks first
