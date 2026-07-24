import pytest
from PySide2 import QtCore, QtGui, QtTest

from ui.quicklook_overlay import QuickLookOverlay


@pytest.mark.gui
def test_shows_and_navigates(qtbot):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.show_element({"name": "plate_a"}, preview_path=None)
    assert ov.title_label.text() == "plate_a"
    with qtbot.waitSignal(ov.next_requested, timeout=1000):
        ov.keyPressEvent(QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Right, QtCore.Qt.NoModifier))


# ---------------------------------------------------------------------------
# MediaDisplayWidget wiring: Space opens quicklook for the current selection,
# and prev/next navigation moves the selection within current_elements and
# clamps safely at both ends. (Design doc SS3.2.)
# ---------------------------------------------------------------------------

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    return w


def _seed_elements(stax_db, names):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for name in names:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type) VALUES (1, ?, '2D')",
                (name,),
            )


@pytest.mark.gui
def test_select_next_previous_element_moves_and_clamps(qtbot, stax_db, stax_config):
    _seed_elements(stax_db, ["a", "b", "c"])
    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)
    assert [e["name"] for e in w.current_elements] == ["a", "b", "c"]

    first_id = w.current_elements[0]["element_id"]
    first_item = w.element_items[first_id]
    w.gallery_view.setCurrentItem(first_item)
    first_item.setSelected(True)

    assert w._get_selected_element()["name"] == "a"

    nxt = w.select_next_element()
    assert nxt["name"] == "b"
    assert w.get_selected_element_ids() == [w.current_elements[1]["element_id"]]

    nxt2 = w.select_next_element()
    assert nxt2["name"] == "c"

    # Clamp at the end -- already on the last item, stays put.
    nxt3 = w.select_next_element()
    assert nxt3["name"] == "c"

    prev = w.select_previous_element()
    assert prev["name"] == "b"

    prev2 = w.select_previous_element()
    assert prev2["name"] == "a"

    # Clamp at the start -- already on the first item, stays put.
    prev3 = w.select_previous_element()
    assert prev3["name"] == "a"


@pytest.mark.gui
def test_navigation_is_noop_when_nothing_selected_or_result_set_empty(qtbot, stax_db, stax_config):
    w = _widget(qtbot, stax_db, stax_config)

    # Empty result set: current_elements is [].
    assert w.current_elements == []
    assert w.select_next_element() is None
    assert w.select_previous_element() is None

    # Elements loaded, but nothing selected in the view.
    _seed_elements(stax_db, ["only"])
    w.load_elements(1)
    assert w.get_selected_element_ids() == []
    assert w.select_next_element() is None
    assert w.select_previous_element() is None


@pytest.mark.gui
def test_space_opens_quicklook_for_selection(qtbot, stax_db, stax_config):
    _seed_elements(stax_db, ["a", "b"])
    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)

    first_id = w.current_elements[0]["element_id"]
    first_item = w.element_items[first_id]
    w.gallery_view.setCurrentItem(first_item)
    first_item.setSelected(True)

    # Route a real Space key event through Qt's event dispatch (not a
    # direct eventFilter call) so this also proves the installEventFilter
    # wiring on gallery_view itself is in place.
    QtTest.QTest.keyClick(w.gallery_view, QtCore.Qt.Key_Space)

    assert w._quicklook.isVisible()
    assert w._quicklook.title_label.text() == "a"

    # Right arrow on the overlay advances both the overlay and the
    # underlying gallery selection.
    w._quicklook.next_requested.emit()
    assert w._quicklook.title_label.text() == "b"
    assert w.get_selected_element_ids() == [w.current_elements[1]["element_id"]]
