import pytest
from PySide2 import QtCore, QtWidgets

from ui.dialogs import AdvancedSearchDialog


@pytest.mark.gui
def test_double_click_emits_result_activated(qtbot, stax_db):
    dlg = AdvancedSearchDialog(stax_db)
    qtbot.addWidget(dlg)

    # Seed one result row with an element_id in column 0's UserRole.
    dlg.results_table.setRowCount(1)
    cell = QtWidgets.QTableWidgetItem("elem")
    cell.setData(QtCore.Qt.UserRole, 42)
    dlg.results_table.setItem(0, 0, cell)

    with qtbot.waitSignal(dlg.result_activated, timeout=1000) as blocker:
        dlg.on_result_double_clicked(cell)
    assert blocker.args == [42]


@pytest.mark.gui
def test_mainwindow_has_on_advanced_search_result(qtbot, stax_config, mock_nuke, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from main import MainWindow

    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)
    assert callable(getattr(win, "on_advanced_search_result", None))

    # A non-existent id makes on_element_double_clicked's except-branch pop a modal
    # QMessageBox.critical. That call is unrelated to M4 but crashes the interpreter
    # under this environment's offscreen QPA platform (pre-existing PySide2/Qt
    # issue, reproduces even for a bare QMessageBox.critical() with no StaX code
    # involved) -- stub it so the test verifies routing/no-AttributeError without
    # tripping that unrelated, pre-existing crash.
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: None)
    win.on_advanced_search_result(999999)  # non-existent id -> handled, no crash
