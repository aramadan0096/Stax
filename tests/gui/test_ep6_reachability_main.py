import pytest


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    `Config` reads STOCK_DB only at construction time (src/config.py:107),
    so the env var must be set *before* `Config(...)` is built. Same helper
    as `tests/gui/test_ep6_watch_wiring.py::_mainwindow_with_temp_db`.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


@pytest.mark.gui
def test_job_queue_view_action_toggles_dock(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    # QWidget.isVisible() reflects the whole ancestor chain, including the
    # top-level window itself -- without an explicit show() here a freshly
    # constructed (never-shown) top-level widget makes isVisible() report
    # False for every child regardless of its own setVisible() calls (see
    # tests/gui/test_ep2_search_help.py for the same note).
    win.show()
    qtbot.waitExposed(win)

    assert hasattr(win, "jobqueue_view_action")

    win.toggle_job_queue(True)
    assert win.job_queue_dock.isVisible() is True
    assert win.jobqueue_view_action.isChecked() is True

    win.toggle_job_queue(False)
    assert win.job_queue_dock.isVisible() is False


@pytest.mark.gui
def test_settings_change_restarts_watch_scanner(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win.db.create_watch_folder(str(tmp_path), enabled=True)

    win.on_settings_changed()

    assert win._watch_scanner is not None
    assert str(tmp_path) in [f["path"] for f in win._watch_scanner.folders]

    win._stop_watch_scanner()


@pytest.mark.gui
def test_watch_scan_error_records_notification(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win._on_watch_scan_error(1, "boom")

    notifications = win.db.get_notifications()
    assert any(n["title"] == "Watch folder error" for n in notifications)
