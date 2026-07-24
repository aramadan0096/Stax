import pytest
from PySide2 import QtWidgets

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
