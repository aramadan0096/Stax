import pytest
from ui.job_queue_dashboard import JobQueueDashboard


@pytest.mark.gui
def test_dashboard_lists_jobs(qtbot, stax_db):
    stax_db.create_job("ingest", "/a/a.exr")
    j = stax_db.create_job("ingest", "/a/b.exr")
    stax_db.update_job_status(j, "failed", message="bad")
    dash = JobQueueDashboard(stax_db)
    qtbot.addWidget(dash)
    dash.refresh()
    assert dash.jobs_table.rowCount() == 2


@pytest.mark.gui
def test_retry_enabled_only_for_failed(qtbot, stax_db):
    j = stax_db.create_job("ingest", "/a/b.exr")
    stax_db.update_job_status(j, "failed", message="bad")
    dash = JobQueueDashboard(stax_db)
    qtbot.addWidget(dash)
    dash.refresh()
    dash.jobs_table.selectRow(0)
    dash._sync_buttons()
    assert dash.retry_button.isEnabled() is True
    with qtbot.waitSignal(dash.retry_requested, timeout=1000) as blk:
        dash.retry_button.click()
    assert blk.args == [j]
