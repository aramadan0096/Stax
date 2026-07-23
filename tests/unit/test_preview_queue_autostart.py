import pytest

import preview_worker
from preview_worker import get_preview_queue, shutdown_preview_queue


@pytest.mark.unit
def test_get_preview_queue_autostarts_worker_for_all_hosts():
    """
    Regression (I1): nuke_launcher.StaXPanel.perform_ingestion calls
    ingestion.ingest_file(...) directly, which submits jobs via
    get_preview_queue() WITHOUT any caller ever calling .start() (that only
    happens in main.py::_start_preview_worker). The docstring promises
    "Creates and starts it on first call" -- verify that promise holds so
    previews are generated in every host, not just MainWindow.
    """
    # Ensure a clean singleton regardless of test order/leakage.
    shutdown_preview_queue()
    assert preview_worker._GLOBAL_WORKER is None

    try:
        worker = get_preview_queue()
        assert worker.isRunning() is True
    finally:
        shutdown_preview_queue()

    assert preview_worker._GLOBAL_WORKER is None


@pytest.mark.unit
def test_get_preview_queue_does_not_double_start_already_running_worker():
    """Calling get_preview_queue() again on an already-running singleton
    must not raise / must remain idempotent (start() is guarded by
    isRunning())."""
    shutdown_preview_queue()
    try:
        w1 = get_preview_queue()
        assert w1.isRunning() is True
        w2 = get_preview_queue()
        assert w2 is w1
        assert w2.isRunning() is True
    finally:
        shutdown_preview_queue()
