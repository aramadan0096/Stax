import pytest


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    eid = stax_db.create_element(lid, "e1", "2D", format="exr", tags="a")
    return lid, eid


@pytest.mark.unit
def test_count_elements_by_list(stax_db):
    lid, eid = _seed(stax_db)
    assert stax_db.count_elements_by_list(lid) == 1
    stax_db.update_element(eid, is_deprecated=1)
    assert stax_db.count_elements_by_list(lid) == 0  # deprecated excluded


@pytest.mark.unit
def test_update_element_metadata_whitelist(stax_db):
    lid, eid = _seed(stax_db)
    stax_db.update_element_metadata(
        eid, name="renamed", comment="c", bogus="ignored"
    )
    elem = stax_db.get_element_by_id(eid)
    assert elem["name"] == "renamed"
    assert elem["comment"] == "c"
    assert "bogus" not in elem


@pytest.mark.unit
def test_phash_roundtrip(stax_db):
    lid, eid = _seed(stax_db)
    assert stax_db.get_elements_with_phash() == []
    stax_db.update_element_phash(eid, "abcd1234")
    rows = stax_db.get_elements_with_phash()
    assert len(rows) == 1
    assert rows[0]["element_id"] == eid
    assert rows[0]["phash"] == "abcd1234"
