import pytest


@pytest.mark.gui
def test_mainwindow_constructs(qtbot, stax_config, mock_nuke, monkeypatch, tmp_path):
    # Point the app's DB at the temp location via STOCK_DB so no shared file is touched.
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from main import MainWindow

    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)
    assert win is not None
