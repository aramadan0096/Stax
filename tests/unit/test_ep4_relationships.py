import pytest


def _two(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'b','2D')")


@pytest.mark.unit
def test_add_get_both_directions(stax_db):
    _two(stax_db)
    stax_db.add_relationship(1, 2, "variant_of")
    assert len(stax_db.get_relationships(1)) == 1
    assert len(stax_db.get_relationships(2)) == 1   # reverse direction visible


@pytest.mark.unit
def test_remove(stax_db):
    _two(stax_db)
    rid = stax_db.add_relationship(1, 2, "related")
    stax_db.remove_relationship(rid)
    assert stax_db.get_relationships(1) == []
