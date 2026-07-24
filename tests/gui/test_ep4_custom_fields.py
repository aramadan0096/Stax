import pytest


def _setup(stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'e','2D')")
    stax_db.create_metadata_field(1, "shot", "Shot", "text")
    stax_db.create_metadata_field(1, "hero", "Hero", "bool")
    return 1


@pytest.mark.gui
def test_widget_renders_fields_and_commits(qtbot, stax_db):
    from ui.custom_fields_widget import CustomFieldsWidget
    eid = _setup(stax_db)
    w = CustomFieldsWidget(stax_db)
    qtbot.addWidget(w)
    w.load(stack_fk=1, element_id=eid)
    assert "shot" in w.editors and "hero" in w.editors
    w.editors["shot"].setText("010")
    w.commit(eid)
    assert stax_db.get_element_metadata(eid)["shot"] == "010"
