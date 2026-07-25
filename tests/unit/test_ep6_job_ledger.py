import pytest


@pytest.mark.unit
def test_create_job_defaults_to_pending(stax_db):
    jid = stax_db.create_job("ingest", "/a/shot.exr", target_list_id=3,
                             payload={"source_path": "/a/shot.exr", "target_list_id": 3})
    job = stax_db.get_job(jid)
    assert job["status"] == "pending"
    assert job["attempts"] == 0
    assert job["payload"]["target_list_id"] == 3


@pytest.mark.unit
def test_status_transitions_and_attempt_bump(stax_db):
    jid = stax_db.create_job("ingest", "/a/x.mov")
    stax_db.bump_job_attempt(jid)
    stax_db.update_job_status(jid, "failed", message="boom")
    job = stax_db.get_job(jid)
    assert job["status"] == "failed"
    assert job["attempts"] == 1
    assert job["message"] == "boom"


@pytest.mark.unit
def test_get_jobs_filters_by_status(stax_db):
    stax_db.create_job("ingest", "/a/1")
    j2 = stax_db.create_job("ingest", "/a/2")
    stax_db.update_job_status(j2, "done")
    pending = stax_db.get_jobs(status="pending")
    assert [j["source_path"] for j in pending] == ["/a/1"]


@pytest.mark.unit
def test_count_and_clear_finished(stax_db):
    a = stax_db.create_job("ingest", "/a/a")
    b = stax_db.create_job("ingest", "/a/b")
    stax_db.update_job_status(a, "done")
    stax_db.update_job_status(b, "failed")
    counts = stax_db.count_jobs_by_status()
    assert counts["done"] == 1 and counts["failed"] == 1
    stax_db.clear_finished_jobs()
    assert stax_db.count_jobs_by_status().get("done") is None
    assert stax_db.count_jobs_by_status().get("failed") == 1
