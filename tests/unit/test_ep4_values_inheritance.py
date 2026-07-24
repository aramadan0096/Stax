import pytest


def _stack_list_element(stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'seqA')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1,'e','2D')")
    stax_db.create_metadata_field(1, "cs", "Colorspace", "text")
    return 1  # element_id, list_id, stack_id all == 1


@pytest.mark.unit
def test_element_override_beats_defaults(stax_db):
    _stack_list_element(stax_db)
    stax_db.set_metadata_default("stack", 1, "cs", "sRGB")
    stax_db.set_metadata_default("list", 1, "cs", "ACES")
    stax_db.set_element_metadata(1, "cs", "Rec709")
    assert stax_db.get_effective_metadata(1)["cs"] == "Rec709"


@pytest.mark.unit
def test_list_default_beats_stack_default(stax_db):
    _stack_list_element(stax_db)
    stax_db.set_metadata_default("stack", 1, "cs", "sRGB")
    stax_db.set_metadata_default("list", 1, "cs", "ACES")
    assert stax_db.get_effective_metadata(1)["cs"] == "ACES"


@pytest.mark.unit
def test_stack_default_when_no_override(stax_db):
    _stack_list_element(stax_db)
    stax_db.set_metadata_default("stack", 1, "cs", "sRGB")
    assert stax_db.get_effective_metadata(1)["cs"] == "sRGB"
