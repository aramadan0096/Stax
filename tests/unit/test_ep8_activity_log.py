import pytest


@pytest.mark.unit
def test_log_and_read_newest_first(stax_db):
    stax_db.log_activity("alice", "ingest", "element", 1, "plate_a")
    stax_db.log_activity("bob", "delete", "element", 1, "plate_a")
    rows = stax_db.get_activity()
    assert rows[0]["action"] == "delete"
    assert rows[0]["actor"] == "bob"
    assert rows[1]["action"] == "ingest"


@pytest.mark.unit
def test_filter_by_action_and_actor(stax_db):
    stax_db.log_activity("alice", "ingest", "element", 1)
    stax_db.log_activity("bob", "ingest", "element", 2)
    stax_db.log_activity("alice", "delete", "element", 1)
    assert len(stax_db.get_activity(action="ingest")) == 2
    assert len(stax_db.get_activity(actor="alice")) == 2
    assert len(stax_db.get_activity(action="delete", actor="alice")) == 1


@pytest.mark.unit
def test_limit(stax_db):
    for i in range(5):
        stax_db.log_activity("alice", "ingest", "element", i)
    assert len(stax_db.get_activity(limit=2)) == 2
