import pytest


def _seed_element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'plate_a', '2D')")
        conn.commit()
    return 1


@pytest.mark.unit
def test_delete_with_actor_audits(stax_db):
    eid = _seed_element(stax_db)
    stax_db.delete_element(eid, actor="alice")
    rows = stax_db.get_activity(action="delete")
    assert rows and rows[0]["actor"] == "alice" and rows[0]["target_id"] == eid


@pytest.mark.unit
def test_delete_without_actor_writes_no_activity(stax_db):
    eid = _seed_element(stax_db)
    stax_db.delete_element(eid)
    assert stax_db.get_activity(action="delete") == []


@pytest.mark.unit
def test_update_with_actor_audits_metadata_edit(stax_db):
    eid = _seed_element(stax_db)
    stax_db.update_element(eid, _actor="bob", comment="new note")
    rows = stax_db.get_activity(action="metadata_edit")
    assert rows and rows[0]["actor"] == "bob"


@pytest.mark.unit
def test_ingest_success_with_actor_audits(stax_db):
    # ingestion_history.element_fk carries a real FOREIGN KEY (enforced,
    # PRAGMA foreign_keys=ON in get_connection()); seed an element with
    # id=7 so the brief's hardcoded element_id=7 satisfies the constraint
    # instead of raising sqlite3.IntegrityError unrelated to this feature.
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute(
            "INSERT INTO elements (element_id, list_fk, name, type) "
            "VALUES (7, 1, 'plate_g', '2D')"
        )
        conn.commit()
    stax_db.log_ingestion("ingest", "/src/a.exr", "L", "success", actor="carol", element_id=7)
    rows = stax_db.get_activity(action="ingest")
    assert rows and rows[0]["actor"] == "carol" and rows[0]["target_id"] == 7
