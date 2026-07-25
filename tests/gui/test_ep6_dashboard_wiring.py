import pytest


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    `Config` reads STOCK_DB only at construction time (src/config.py:107),
    so the env var must be set *before* `Config(...)` is built -- a
    `monkeypatch.setenv` inside the test body comes too late once a
    `Config` object already exists (e.g. the shared `stax_config` fixture),
    and `MainWindow` would silently build against the real project database
    at `./data/stax.db` instead of an isolated tmp_path db. Same helper as
    `tests/gui/test_ep4_related_navigation.py::_mainwindow_with_temp_db`.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


@pytest.mark.gui
def test_record_ingest_jobs_creates_pending_rows(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    ids = win._record_ingest_jobs(["/a/x.exr", "/a/y.exr"], target_list_id=2)
    assert len(ids) == 2

    pending = win.db.get_jobs(status="pending")
    assert {j["source_path"] for j in pending} == {"/a/x.exr", "/a/y.exr"}
    assert pending[0]["payload"]["target_list_id"] == 2


@pytest.mark.gui
def test_ingest_finished_emits_notification(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win._on_ingest_finished_notify(3, 1, 0)

    notes = win.db.get_notifications()
    assert notes and "3" in notes[0]["body"]


@pytest.mark.gui
def test_retry_job_starts_worker(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    jid = win.db.create_job("ingest", "/a/x.exr", target_list_id=2,
                             payload={"source_path": "/a/x.exr", "target_list_id": 2})
    win.db.update_job_status(jid, "failed", message="boom")

    win._retry_job(jid)

    assert win.db.get_job(jid)["status"] in ("pending", "running")
    assert win._ingest_worker is not None

    win._ingest_worker.wait(3000)
