import pytest


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    `Config` reads STOCK_DB only at construction time (src/config.py:107),
    so the env var must be set *before* `Config(...)` is built -- a
    `monkeypatch.setenv` inside the test body comes too late once a
    `Config` object already exists (e.g. the shared `stax_config` fixture),
    and `MainWindow` would silently build against the real project database
    at `./data/stax.db` instead of an isolated tmp_path db. Same helper as
    `tests/gui/test_ep4_related_navigation.py::_mainwindow_with_temp_db` /
    `tests/gui/test_ep6_dashboard_wiring.py::_mainwindow_with_temp_db`.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


@pytest.mark.gui
def test_start_watch_scanner_builds_from_enabled_rows(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win.db.create_watch_folder("/inbox", enabled=True)
    win.db.create_watch_folder("/off", enabled=False)

    win._start_watch_scanner()
    assert win._watch_scanner is not None
    assert [f["path"] for f in win._watch_scanner.folders] == ["/inbox"]
    win._stop_watch_scanner()


@pytest.mark.gui
def test_on_watched_files_records_jobs(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    f = tmp_path / "a.exr"
    f.write_bytes(b"x")
    wid = win.db.create_watch_folder(str(tmp_path), target_list_id=4)

    win._on_watched_files(wid, [str(f)])

    pending = win.db.get_jobs(status="pending")
    assert pending and pending[0]["target_list_id"] == 4

    if getattr(win, "_watch_ingest_worker", None):
        win._watch_ingest_worker.wait(3000)
