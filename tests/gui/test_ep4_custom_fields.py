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


@pytest.mark.gui
def test_commit_does_not_freeze_untouched_inherited_value(qtbot, stax_db):
    """I2: an editor that only displays an inherited default (no explicit
    override on this element) must NOT be written by commit() unless its
    text was actually changed -- otherwise inheritance is permanently
    defeated the first time the dialog is saved."""
    from ui.custom_fields_widget import CustomFieldsWidget

    eid = _setup(stax_db)
    stax_db.set_metadata_default("stack", 1, "shot", "INH")

    w = CustomFieldsWidget(stax_db)
    qtbot.addWidget(w)
    w.load(stack_fk=1, element_id=eid)

    # Sanity: the editor is showing the inherited value, not an override.
    assert w._editor_text("shot") == "INH"
    assert "shot" not in stax_db.get_element_metadata(eid)

    # Commit without touching anything -- must NOT freeze the inherited value.
    w.commit(eid)
    assert "shot" not in stax_db.get_element_metadata(eid)

    # Now actually change it -- must become a real override.
    w.load(stack_fk=1, element_id=eid)
    w.editors["shot"].setText("020")
    w.commit(eid)
    assert stax_db.get_element_metadata(eid)["shot"] == "020"
