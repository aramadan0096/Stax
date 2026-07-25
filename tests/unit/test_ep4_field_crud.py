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
    with stax_db.get_connection(write=True) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        list_id = cur.lastrowid
        cur.execute("INSERT INTO elements (list_fk, name, type) VALUES (?, 'e', '2D')", (list_id,))
        element_id = cur.lastrowid
        cur.execute("INSERT INTO element_metadata (element_fk, field_key, value) VALUES (?, 'shot', '010')",
                    (element_id,))
    stax_db.delete_metadata_field(fid)
    with stax_db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM element_metadata WHERE field_key='shot'").fetchone()[0] == 0


@pytest.mark.unit
def test_delete_field_scoped_to_its_own_stack(stax_db):
    """I1: deleting a field in one stack must not wipe same-named-key values
    (or defaults) belonging to a DIFFERENT stack's field of the same key."""
    stack_a = stax_db.create_stack("StackA", "/tmp/A")
    stack_b = stax_db.create_stack("StackB", "/tmp/B")

    field_a = stax_db.create_metadata_field(stack_a, "shot", "Shot", "text")
    field_b = stax_db.create_metadata_field(stack_b, "shot", "Shot", "text")

    with stax_db.get_connection(write=True) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO lists (stack_fk, name) VALUES (?, 'L')", (stack_a,))
        list_a = cur.lastrowid
        cur.execute("INSERT INTO lists (stack_fk, name) VALUES (?, 'L')", (stack_b,))
        list_b = cur.lastrowid
        cur.execute("INSERT INTO elements (list_fk, name, type) VALUES (?, 'eA', '2D')", (list_a,))
        elem_a = cur.lastrowid
        cur.execute("INSERT INTO elements (list_fk, name, type) VALUES (?, 'eB', '2D')", (list_b,))
        elem_b = cur.lastrowid

    stax_db.set_element_metadata(elem_a, "shot", "A")
    stax_db.set_element_metadata(elem_b, "shot", "B")
    stax_db.set_metadata_default("stack", stack_a, "shot", "DEFAULT_A")
    stax_db.set_metadata_default("stack", stack_b, "shot", "DEFAULT_B")

    stax_db.delete_metadata_field(field_a)

    assert "shot" not in stax_db.get_element_metadata(elem_a)
    assert stax_db.get_element_metadata(elem_b)["shot"] == "B"

    with stax_db.get_connection() as conn:
        remaining_defaults = conn.execute(
            "SELECT scope_id FROM metadata_defaults WHERE field_key = 'shot'"
        ).fetchall()
    assert [r[0] for r in remaining_defaults] == [stack_b]
