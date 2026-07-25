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


@pytest.mark.unit
def test_create_element_sets_updated_at(tmp_path):
    """Reproduces the upgraded-DB gap: elements already has a row when v24
    runs, so the migration's ALTER TABLE ... DEFAULT CURRENT_TIMESTAMP
    attempt raises (SQLite refuses a non-constant default on a populated
    table) and it falls back to a plain ADD COLUMN with no default. Without
    Fix 2, any element created after that upgrade would get updated_at=NULL
    until its first edit -- the exact None the sync merge must never see.
    create_element() must stamp updated_at explicitly so this can't happen.
    """
    import sqlite3
    from db_manager import DatabaseManager

    db_path = str(tmp_path / "upgraded.db")

    # Pre-create a pre-v24 elements table (mirrors _create_schema's shape,
    # no updated_at column) with one existing row, plus its stacks/lists
    # parents, so DatabaseManager's migrations run against a POPULATED
    # elements table and take the no-default fallback branch.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE stacks (stack_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT UNIQUE NOT NULL, path TEXT UNIQUE NOT NULL, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE lists (list_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "stack_fk INTEGER NOT NULL, parent_list_fk INTEGER, name TEXT NOT NULL, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE elements (element_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "list_fk INTEGER NOT NULL, name TEXT NOT NULL, "
        "type TEXT NOT NULL CHECK(type IN ('2D', '3D', 'Toolset')), "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute("INSERT INTO stacks (name, path) VALUES ('S', '/tmp/S')")
    conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
    conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'old', '2D')")
    conn.commit()
    conn.close()

    db = DatabaseManager(db_path, enable_logging=False, use_file_lock=False)

    eid = db.create_element(1, "a", "2D")
    row = db.get_element_by_id(eid)
    assert row["updated_at"] is not None
