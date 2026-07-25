import pytest


def _two(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'b','2D')")


@pytest.mark.gui
def test_related_section_shows_links(qtbot, stax_db):
    _two(stax_db)
    stax_db.add_relationship(1, 2, "variant_of")
    from ui.inspector_panel import InspectorPanel
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(1)
    assert ip.related_list.count() == 1
