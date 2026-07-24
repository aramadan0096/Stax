import pytest


@pytest.mark.gui
def test_start_page_renders_recent(qtbot, stax_db):
    from ui.start_page import StartPage
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
    sp = StartPage(stax_db, user_name="alice", machine_name="ws01")
    qtbot.addWidget(sp)
    assert sp.recent_count() >= 1


@pytest.mark.gui
def test_start_page_most_used_hidden_when_empty(qtbot, stax_db):
    """Design §5: Most-used must be hidden when there is no insertion
    history at all -- db.get_top_inserted_elements(20) returns []."""
    from ui.start_page import StartPage
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")

    assert stax_db.get_top_inserted_elements(20) == []

    sp = StartPage(stax_db, user_name="alice", machine_name="ws01")
    qtbot.addWidget(sp)
    # QWidget.isVisible() reflects the whole ancestor chain, including the
    # top-level window itself -- without an explicit show() here a freshly
    # constructed (never-shown) top-level widget makes isVisible() report
    # False for every child regardless of its own setVisible() calls (see
    # tests/gui/test_ep2_search_help.py::_widget for the same note).
    sp.show()
    assert sp._top_section.isVisible() is False


@pytest.mark.gui
def test_start_page_most_used_shown_when_populated(qtbot, stax_db):
    """Design §5: Most-used must render (and be visible) once real
    insertion_log rows exist. Uses the same real mechanism Task 10 used
    (ui.analytics_panel.log_insertion) rather than stubbing the DB call."""
    from ui.start_page import StartPage
    from ui.analytics_panel import log_insertion

    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
    element_id = stax_db.create_element(1, "elemA", "2D")

    log_insertion(stax_db, element_id)
    assert stax_db.get_top_inserted_elements(20) != []

    sp = StartPage(stax_db, user_name="alice", machine_name="ws01")
    qtbot.addWidget(sp)
    sp.show()
    assert sp._top_section.isVisible() is True
    assert sp._top_list.count() >= 1
