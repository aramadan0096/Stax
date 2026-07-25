import pytest


@pytest.mark.gui
def test_search_tab_shows_success_and_failures(qtbot, stax_db):
    stax_db.log_search_event("fire", 5, "alice")
    stax_db.log_search_event("zzzzz", 0, "bob")
    from ui.analytics_panel import AnalyticsPanel
    panel = AnalyticsPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    assert "50" in panel._search_summary.text()        # 50% success
    assert panel._zero_table.rowCount() == 1
    assert panel._zero_table.item(0, 0).text() == "zzzzz"
