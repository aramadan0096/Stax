import pytest


@pytest.mark.unit
def test_ep4_tables_exist(stax_db):
    with stax_db.get_connection() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("metadata_fields", "element_metadata", "metadata_defaults"):
        assert t in names
