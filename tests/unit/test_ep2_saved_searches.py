import pytest


@pytest.mark.unit
def test_create_and_scope_by_user(stax_db):
    sid = stax_db.create_saved_search("Fire 2D", {"types": ["2D"], "tags_any": ["fire"]}, "alice")
    stax_db.create_saved_search("Bob only", {"types": ["3D"]}, "bob")
    alice = stax_db.get_saved_searches("alice")
    assert [s["name"] for s in alice] == ["Fire 2D"]
    assert alice[0]["filter"]["types"] == ["2D"]
    assert alice[0]["saved_search_id"] == sid


@pytest.mark.unit
def test_delete(stax_db):
    sid = stax_db.create_saved_search("X", {"text": "a"}, "alice")
    stax_db.delete_saved_search(sid)
    assert stax_db.get_saved_searches("alice") == []
