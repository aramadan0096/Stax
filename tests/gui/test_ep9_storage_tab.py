import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        for name, size, phash in [("a", 1000, "hh"), ("b", 800, "hh"), ("c", 500, "zz")]:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, file_size, phash) "
                "VALUES (1, ?, '2D', ?, ?)", (name, size, phash))


@pytest.mark.gui
def test_storage_tab_reports_reclaimable(qtbot, stax_db):
    _seed(stax_db)
    from ui.analytics_panel import AnalyticsPanel
    panel = AnalyticsPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    text = panel._storage_summary.text()
    assert "3" in text                 # 3 elements
    assert "800" in text or "KB" in text  # reclaimable 800 bytes shown (raw or humanized)


@pytest.mark.gui
def test_fmt_bytes():
    from ui.analytics_panel import AnalyticsPanel
    assert AnalyticsPanel._fmt_bytes(0) == "0 B"
    assert AnalyticsPanel._fmt_bytes(1024) == "1.0 KB"
    assert AnalyticsPanel._fmt_bytes(1536) == "1.5 KB"
