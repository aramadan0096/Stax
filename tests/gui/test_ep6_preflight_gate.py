import pytest


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    Same helper as `tests/gui/test_ep6_watch_wiring.py::_mainwindow_with_temp_db`.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


@pytest.mark.gui
def test_preflight_ok_passes_clean_files(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    good = tmp_path / "good.exr"
    good.write_bytes(b"data")

    assert win._preflight_ok([str(good)]) is True


@pytest.mark.gui
def test_preflight_ok_blocks_on_error(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    monkeypatch.setattr("ui.preflight_dialog.PreflightDialog.exec_", lambda self: 0)

    assert win._preflight_ok(["/definitely/missing.exr"]) is False


@pytest.mark.gui
def test_perform_ingestion_aborts_when_preflight_fails(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win._preflight_ok = lambda files: False

    win.perform_ingestion(["/x.exr"], 1)

    assert win.db.get_jobs() == []
