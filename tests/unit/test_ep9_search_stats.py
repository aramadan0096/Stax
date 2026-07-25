import pytest


@pytest.mark.unit
def test_success_stats_computed(stax_db):
    stax_db.log_search_event("fire", 5, "alice")
    stax_db.log_search_event("water", 3, "alice")
    stax_db.log_search_event("zzzzz", 0, "bob")
    stax_db.log_search_event("qqqqq", 0, "bob")
    stats = stax_db.get_search_success_stats()
    assert stats["total"] == 4
    assert stats["zero_result"] == 2
    assert stats["success"] == 2
    assert stats["success_rate"] == 0.5
    assert stats["zero_result_rate"] == 0.5


@pytest.mark.unit
def test_success_stats_empty_db_is_zero(stax_db):
    stats = stax_db.get_search_success_stats()
    assert stats["total"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["zero_result_rate"] == 0.0


@pytest.mark.unit
def test_zero_result_queries_grouped_by_frequency(stax_db):
    for _ in range(3):
        stax_db.log_search_event("greenscreen", 0, "alice")
    stax_db.log_search_event("hologram", 0, "bob")
    stax_db.log_search_event("fire", 9, "bob")   # a hit — excluded
    rows = stax_db.get_zero_result_queries(limit=10)
    assert [r["query_text"] for r in rows] == ["greenscreen", "hologram"]
    assert rows[0]["count"] == 3
