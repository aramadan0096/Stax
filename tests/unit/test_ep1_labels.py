import pytest


def _element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'e', '2D')")
    return 1


@pytest.mark.unit
def test_get_labels_returns_seeded_palette(stax_db):
    labels = stax_db.get_labels()
    assert len(labels) == 7
    assert labels[0]["name"] == "Reject"
    assert labels[0]["color_hex"] == "#E5484D"


@pytest.mark.unit
def test_create_label_validates_color(stax_db):
    with pytest.raises(ValueError):
        stax_db.create_label("Bad", "red")
    lid = stax_db.create_label("Teal", "#12A594", "custom", sort_order=9)
    assert any(l["label_id"] == lid and l["name"] == "Teal" for l in stax_db.get_labels())


@pytest.mark.unit
def test_set_element_label_and_clear(stax_db):
    eid = _element(stax_db)
    stax_db.set_element_label(eid, 2)
    assert stax_db.get_element_by_id(eid)["label_fk"] == 2
    stax_db.set_element_label(eid, None)
    assert stax_db.get_element_by_id(eid)["label_fk"] is None


@pytest.mark.unit
def test_delete_label_nulls_referencing_elements(stax_db):
    eid = _element(stax_db)
    stax_db.set_element_label(eid, 3)
    stax_db.delete_label(3)
    assert stax_db.get_element_by_id(eid)["label_fk"] is None
    assert all(l["label_id"] != 3 for l in stax_db.get_labels())


@pytest.mark.unit
def test_bulk_set_label_returns_count(stax_db):
    _element(stax_db)
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'e2', '2D')")
    assert stax_db.bulk_set_label([1, 2], 1) == 2
