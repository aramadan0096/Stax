import pytest


@pytest.mark.gui
def test_health_panel_lists_issues(qtbot, stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'bad name','2D')")
    stax_db.create_quality_rule("naming_regex", {"pattern": r"^plate_\d+$"}, stack_fk=1)
    from ui.health_panel import HealthPanel
    hp = HealthPanel(stax_db)
    qtbot.addWidget(hp)
    hp.load_list(1)
    assert hp.issue_count() >= 1
