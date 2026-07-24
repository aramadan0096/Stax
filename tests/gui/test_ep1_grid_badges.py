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


@pytest.mark.gui
def test_draw_curation_badges_uses_full_element_fast_path(qtbot, stax_db, stax_config, monkeypatch):
    # A real (seeded) label so _label_color() has an actual color_hex to resolve.
    labels = stax_db.get_labels()
    assert labels, "expected default labels to be seeded"
    label_id = labels[0]["label_id"]
    w = _widget(qtbot, stax_db, stax_config)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "get_element_by_id must not be called when a full element row is provided"
        )

    monkeypatch.setattr(w.db, "get_element_by_id", _must_not_be_called)

    px = QtGui.QPixmap(128, 128)
    px.fill()
    element = {"rating": 4, "label_fk": label_id}
    out = w._draw_curation_badges(px, element_id=1, element=element)

    assert isinstance(out, QtGui.QPixmap)
    assert out.size() == px.size()
    # Stars + label chip were actually drawn onto the returned pixmap.
    assert out.toImage() != px.toImage()
