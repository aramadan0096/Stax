import pytest


@pytest.mark.unit
def test_versioned_artifacts_exist_on_fresh_db(stax_db):
    with stax_db.get_connection() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        elem_cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)")}
    assert "schema_version" in tables
    assert "insertion_log" in tables
    assert "phash" in elem_cols
    # lowercase only — the orphaned capitalized artifacts must NOT appear
    assert "InsertionLog" not in tables


@pytest.mark.unit
def test_run_migrations_is_idempotent(stax_db):
    from db_migrations import run_migrations, CURRENT_SCHEMA_VERSION
    with stax_db.get_connection() as conn:
        run_migrations(conn)  # second run
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == CURRENT_SCHEMA_VERSION
