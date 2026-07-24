import pytest


def _seed_tags(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'x','2D','fire,explosion')")


@pytest.mark.unit
def test_suggest_correction_finds_near_tag(stax_db):
    _seed_tags(stax_db)
    assert stax_db.suggest_correction("frie") == "fire"
    assert stax_db.suggest_correction("zzzzzz") is None


@pytest.mark.unit
def test_recent_searches_capped_and_ordered(stax_db):
    for i in range(25):
        stax_db.add_recent_search("alice", "q{}".format(i), cap=20)
    recent = stax_db.get_recent_searches("alice")
    assert len(recent) == 20
    assert recent[0] == "q24"   # most recent first
