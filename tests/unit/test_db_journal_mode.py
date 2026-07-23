import pytest


@pytest.mark.unit
def test_journal_mode_is_delete_not_wal(stax_db):
    with stax_db.get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "delete"
