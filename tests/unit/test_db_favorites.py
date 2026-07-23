import pytest


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    return stax_db.create_element(lid, "fav", "2D")


@pytest.mark.unit
def test_favorite_roundtrip_user_machine_order(stax_db):
    eid = _seed(stax_db)
    # Call sites pass (element_id, user, machine) — this is the canonical order.
    assert stax_db.is_favorite(eid, "alice", "ws01") is False
    stax_db.add_favorite(eid, "alice", "ws01")
    assert stax_db.is_favorite(eid, "alice", "ws01") is True

    favs = stax_db.get_favorites("alice", "ws01")
    assert any(r["element_id"] == eid for r in favs)

    # A different identity must NOT see alice's favorite.
    assert stax_db.is_favorite(eid, "bob", "ws02") is False

    stax_db.remove_favorite(eid, "alice", "ws01")
    assert stax_db.is_favorite(eid, "alice", "ws01") is False
