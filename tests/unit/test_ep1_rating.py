import pytest


def _make_element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute(
            "INSERT INTO elements (list_fk, name, type) VALUES (1, 'e', '2D')"
        )
    return 1


@pytest.mark.unit
def test_set_and_read_rating(stax_db):
    eid = _make_element(stax_db)
    stax_db.set_element_rating(eid, 4)
    assert stax_db.get_element_by_id(eid)["rating"] == 4


@pytest.mark.unit
def test_rating_out_of_range_raises(stax_db):
    eid = _make_element(stax_db)
    with pytest.raises(ValueError):
        stax_db.set_element_rating(eid, 6)
    with pytest.raises(ValueError):
        stax_db.set_element_rating(eid, -1)


@pytest.mark.unit
def test_bulk_set_rating_returns_count(stax_db):
    eid = _make_element(stax_db)
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'e2', '2D')")
    n = stax_db.bulk_set_rating([1, 2], 5)
    assert n == 2
    assert stax_db.get_element_by_id(2)["rating"] == 5
