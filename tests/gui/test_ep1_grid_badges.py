import pytest
from PySide2 import QtGui

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_quick_set_rating_writes_through(qtbot, stax_db, stax_config):
    # seed one element
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1,'e','2D')")
    w = _widget(qtbot, stax_db, stax_config)
    w.quick_set_rating(1, 4)
    assert stax_db.get_element_by_id(1)["rating"] == 4


@pytest.mark.gui
def test_draw_curation_badges_returns_pixmap(qtbot, stax_db, stax_config):
    w = _widget(qtbot, stax_db, stax_config)
    px = QtGui.QPixmap(128, 128)
    px.fill()
    out = w._draw_curation_badges(px, element_id=None)
    assert isinstance(out, QtGui.QPixmap)
    assert out.size() == px.size()
    assert out.toImage() == px.toImage()
