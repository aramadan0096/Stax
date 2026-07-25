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

    for w in list(getattr(win, "_watch_ingest_workers", [])):
        w.wait(3000)


@pytest.mark.gui
def test_on_watched_files_does_not_clobber_prior_worker(qtbot, mock_nuke, monkeypatch, tmp_path):
    """Regression: WatchFolderScanner.scan_once loops over ALL enabled
    folders in one pass and can emit files_detected for two+ folders
    back-to-back, so two _on_watched_files calls land in quick succession.
    Storing the IngestWorker in a single overwritable attribute
    (self._watch_ingest_worker) would let the second call's assignment drop
    the only reference to the first, still-running worker -- a premature
    QThread-GC crash risk. The fix keeps a list (self._watch_ingest_workers)
    and only forgets an entry once its `finished` signal fires."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    fa = dir_a / "a.exr"
    fa.write_bytes(b"x")
    fb = dir_b / "b.exr"
    fb.write_bytes(b"x")

    wid_a = win.db.create_watch_folder(str(dir_a), target_list_id=5)
    wid_b = win.db.create_watch_folder(str(dir_b), target_list_id=6)

    win._on_watched_files(wid_a, [str(fa)])
    assert len(win._watch_ingest_workers) >= 1
    worker_a = win._watch_ingest_workers[-1]

    win._on_watched_files(wid_b, [str(fb)])
    worker_b = win._watch_ingest_workers[-1]

    # The core regression check: worker_a's reference must not have been
    # clobbered by the second call's assignment. Either it is still sitting
    # in the list (both workers held simultaneously -- the common case,
    # since these two calls execute back-to-back with no yield point in
    # between), or it already completed and was cleanly removed via the
    # `finished` cleanup -- never silently dropped while still running.
    assert worker_a is not worker_b
    assert (worker_a in win._watch_ingest_workers) or worker_a.isFinished()

    for w in list(win._watch_ingest_workers):
        w.wait(3000)
