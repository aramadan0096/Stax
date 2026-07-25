import pytest


@pytest.mark.gui
def test_log_search_writes_event(qtbot, stax_db, stax_config, mock_nuke):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, mock_nuke)
    qtbot.addWidget(w)
    w._log_search("fire", 3)
    assert stax_db.get_search_success_stats()["total"] == 1


@pytest.mark.gui
def test_log_search_skips_empty_query(qtbot, stax_db, stax_config, mock_nuke):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, mock_nuke)
    qtbot.addWidget(w)
    w._log_search("   ", 0)
    assert stax_db.get_search_success_stats()["total"] == 0
