import pytest


@pytest.mark.unit
def test_create_get_fields(stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    fid = stax_db.create_metadata_field(1, "shot", "Shot", "text")
    stax_db.create_metadata_field(1, "cs", "Colorspace", "choice", choices=["ACES", "sRGB"])
    fields = stax_db.get_metadata_fields(1)
    assert [f["key"] for f in fields] == ["shot", "cs"]
    assert fields[1]["field_type"] == "choice"


@pytest.mark.unit
def test_invalid_type_raises(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with pytest.raises(ValueError):
        stax_db.create_metadata_field(1, "x", "X", "bogus")


@pytest.mark.unit
def test_delete_field_clears_values(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    fid = stax_db.create_metadata_field(1, "shot", "Shot", "text")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO element_metadata (element_fk, field_key, value) VALUES (1,'shot','010')")
    stax_db.delete_metadata_field(fid)
    with stax_db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM element_metadata WHERE field_key='shot'").fetchone()[0] == 0
