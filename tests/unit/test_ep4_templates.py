import pytest


def _elem(stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'e','2D','base')")
    stax_db.create_metadata_field(1, "cs", "Colorspace", "text")
    return 1


@pytest.mark.unit
def test_apply_template_sets_fields_and_tags(stax_db):
    eid = _elem(stax_db)
    tid = stax_db.create_metadata_template(1, "ACES plate", {"cs": "ACES", "tags": "graded,hero"})
    stax_db.apply_template(eid, tid)
    assert stax_db.get_element_metadata(eid)["cs"] == "ACES"
    tags = stax_db.get_element_by_id(eid)["tags"]
    assert "graded" in tags and "hero" in tags and "base" in tags


@pytest.mark.unit
def test_delete_metadata_template_removes_it(stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    tid = stax_db.create_metadata_template(1, "ACES plate", {"cs": "ACES"})
    assert len(stax_db.get_metadata_templates(1)) == 1
    stax_db.delete_metadata_template(tid)
    assert stax_db.get_metadata_templates(1) == []
