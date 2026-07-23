import pytest

from ui.analytics_panel import log_insertion


def _seed_element(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    return stax_db.create_element(lid, "elemA", "2D", format="exr")


@pytest.mark.unit
def test_log_insertion_writes_and_reads_back(stax_db):
    eid = _seed_element(stax_db)
    log_insertion(stax_db, eid, user_id=None, project="proj", host="ws01")
    log_insertion(stax_db, eid, user_id=None, project="proj", host="ws01")

    assert stax_db.get_total_insertions() == 2

    top = stax_db.get_top_inserted_elements(5)
    assert len(top) == 1
    assert top[0]["element_id"] == eid
    assert top[0]["name"] == "elemA"
    assert top[0]["count"] == 2

    by_month = stax_db.get_insertions_by_month()
    assert sum(r["count"] for r in by_month) == 2

    by_user = stax_db.get_insertions_by_user()
    assert by_user[0]["username"] == "Guest"
    assert by_user[0]["count"] == 2


@pytest.mark.unit
def test_analytics_empty_db_returns_empty(stax_db):
    assert stax_db.get_total_insertions() == 0
    assert stax_db.get_top_inserted_elements(5) == []
    assert stax_db.get_insertions_by_month() == []
    assert stax_db.get_insertions_by_user() == []
