import pytest
from ui.analytics_panel import log_insertion


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'hero_plate', '2D')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'bg_plate', '2D')")
    # hero_plate inserted 3x, bg_plate 1x
    for _ in range(3):
        log_insertion(stax_db, 1, user_id=None)
    log_insertion(stax_db, 2, user_id=None)


@pytest.mark.gui
def test_top_assets_dashboard_renders_real_data(qtbot, stax_db):
    _seed(stax_db)
    from ui.analytics_panel import AnalyticsPanel
    panel = AnalyticsPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    # details table populated, ranked hero_plate first
    assert panel._top_table.rowCount() == 2
    assert panel._top_table.item(0, 1).text() == "hero_plate"
    assert panel._top_table.item(0, 4).text() == "3"
    assert "4" in panel._total_label.text()   # 4 total insertions logged
