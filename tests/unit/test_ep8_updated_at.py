import time
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'a', '2D')")
        conn.commit()
    return 1


@pytest.mark.unit
def test_updated_at_column_exists(stax_db):
    eid = _seed(stax_db)
    row = stax_db.get_element_by_id(eid)
    assert "updated_at" in row


@pytest.mark.unit
def test_update_bumps_updated_at(stax_db):
    eid = _seed(stax_db)
    before = stax_db.get_element_by_id(eid)["updated_at"]
    time.sleep(1.1)
    stax_db.update_element(eid, comment="x")
    after = stax_db.get_element_by_id(eid)["updated_at"]
    assert after >= before
