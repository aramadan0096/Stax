import pytest


@pytest.mark.gui
def test_activity_panel_lists_and_filters(qtbot, stax_db):
    stax_db.log_activity("alice", "ingest", "element", 1, "plate_a")
    stax_db.log_activity("bob", "delete", "element", 1, "plate_a")
    from ui.activity_panel import ActivityPanel
    panel = ActivityPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    assert panel.activity_table.rowCount() == 2
    panel.set_action_filter("delete")
    panel.refresh()
    assert panel.activity_table.rowCount() == 1
