import os

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
# Review finding 1: GIF and static-image preview kinds must actually render
# (not be silently dropped), and a missing/unreadable file must be handled
# safely without crashing or leaving a stale image on screen.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_show_element_gif_kind_renders_via_qmovie(qtbot, tiny_gif):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.show_element({"name": "clip_a"}, tiny_gif, "gif")
    movie = ov.image_label.movie()
    assert movie is not None
    assert movie.isValid()
    pix = ov.image_label.pixmap()
    assert pix is None or pix.isNull()


@pytest.mark.gui
def test_show_element_image_kind_renders_via_qpixmap(qtbot, tiny_png):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.show_element({"name": "frame_a"}, tiny_png, "image")
    assert ov.image_label.movie() is None
    pix = ov.image_label.pixmap()
    assert pix is not None and not pix.isNull()


@pytest.mark.gui
def test_show_element_missing_preview_is_safe_and_clears_stale_image(qtbot, tiny_png):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)

    # Show a real image first so there is something to go stale.
    ov.show_element({"name": "frame_a"}, tiny_png, "image")
    pix = ov.image_label.pixmap()
    assert pix is not None and not pix.isNull()

    # No preview path at all -- must not crash, must not keep frame_a's image.
    ov.show_element({"name": "no_preview"}, None, "image")
    pix = ov.image_label.pixmap()
    assert pix is None or pix.isNull()
    assert ov.image_label.movie() is None

    # Re-show a real image, then navigate to a nonexistent file -- same guarantee.
    ov.show_element({"name": "frame_a"}, tiny_png, "image")
    ov.show_element({"name": "missing"}, "Z:/does/not/exist.png", "image")
    pix = ov.image_label.pixmap()
    assert pix is None or pix.isNull()
    assert ov.image_label.movie() is None


@pytest.mark.gui
def test_show_element_missing_gif_is_safe(qtbot, tiny_gif):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.show_element({"name": "clip_a"}, tiny_gif, "gif")
    assert ov.image_label.movie() is not None

    ov.show_element({"name": "missing_gif"}, "Z:/does/not/exist.gif", "gif")
    assert ov.image_label.movie() is None
    pix = ov.image_label.pixmap()
    assert pix is None or pix.isNull()


# ---------------------------------------------------------------------------
# Review Minor: Space and Esc must both close the overlay, and closing must
# destroy the instance (WA_DeleteOnClose), not just hide it -- mirrors the
# CommandPalette fix in Task 2, so repeated Space-opens don't accumulate
# hidden QuickLookOverlay instances.
# ---------------------------------------------------------------------------

@pytest.mark.gui
@pytest.mark.parametrize("key", [QtCore.Qt.Key_Space, QtCore.Qt.Key_Escape])
def test_space_and_escape_close_and_destroy_overlay(qtbot, key):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.show_element({"name": "plate_a"}, preview_path=None)
    assert ov.isVisible()

    with qtbot.waitSignal(ov.destroyed, timeout=1000):
        QtTest.QTest.keyClick(ov, key)


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


# ---------------------------------------------------------------------------
# Review finding 1 (widget level): _resolve_element_preview precedence --
# animated GIF is preferred over a static image when both exist (richest
# quicklook representation); geometry_preview_path (3D) is out of scope and
# must never be returned.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_resolve_element_preview_prefers_gif_over_static(qtbot, stax_db, stax_config, tiny_png, tiny_gif):
    w = _widget(qtbot, stax_db, stax_config)
    element = {"preview_path": tiny_png, "gif_preview_path": tiny_gif}
    assert w._resolve_element_preview(element) == (os.path.normpath(tiny_gif), "gif")


@pytest.mark.gui
def test_resolve_element_preview_falls_back_to_static_image(qtbot, stax_db, stax_config, tiny_png):
    w = _widget(qtbot, stax_db, stax_config)
    element = {"preview_path": tiny_png, "gif_preview_path": None}
    assert w._resolve_element_preview(element) == (os.path.normpath(tiny_png), "image")


@pytest.mark.gui
def test_resolve_element_preview_gif_only_element_is_not_blank(qtbot, stax_db, stax_config, tiny_gif):
    # This is the exact bug from finding 1: an element whose only preview
    # asset is a GIF must resolve to something renderable, not None.
    w = _widget(qtbot, stax_db, stax_config)
    element = {"preview_path": None, "gif_preview_path": tiny_gif}
    assert w._resolve_element_preview(element) == (os.path.normpath(tiny_gif), "gif")


@pytest.mark.gui
def test_resolve_element_preview_ignores_geometry_preview_path(qtbot, stax_db, stax_config, tmp_path):
    w = _widget(qtbot, stax_db, stax_config)
    glb = tmp_path / "model.glb"
    glb.write_bytes(b"glTF")
    element = {"geometry_preview_path": str(glb)}
    assert w._resolve_element_preview(element) == (None, None)


@pytest.mark.gui
def test_resolve_element_preview_none_when_nothing_exists(qtbot, stax_db, stax_config):
    w = _widget(qtbot, stax_db, stax_config)
    assert w._resolve_element_preview({"name": "no_preview"}) == (None, None)


# ---------------------------------------------------------------------------
# Review finding 2: cross-page navigation must switch the pagination page
# before selecting, so the gallery selection, the pagination widget, and
# element_selected all agree on the same element -- instead of the previous
# element staying highlighted while element_selected names the new one.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_navigation_across_page_boundary_switches_page_and_selects(qtbot, stax_db, stax_config):
    stax_config.set('items_per_page', 2)
    _seed_elements(stax_db, ["a", "b", "c", "d", "e"])
    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)

    assert w.pagination.items_per_page == 2
    assert w.pagination.current_page == 0
    assert w.gallery_view.count() == 2  # only page 0 ("a", "b") is rendered

    first_id = w.current_elements[0]["element_id"]
    first_item = w.element_items[first_id]
    w.gallery_view.setCurrentItem(first_item)
    first_item.setSelected(True)
    assert w._get_selected_element()["name"] == "a"

    received = []
    w.element_selected.connect(received.append)

    nxt1 = w.select_next_element()  # a -> b, still page 0
    assert nxt1["name"] == "b"
    assert w.pagination.current_page == 0
    assert w.get_selected_element_ids() == [w.current_elements[1]["element_id"]]
    assert received[-1] == w.current_elements[1]["element_id"]

    nxt2 = w.select_next_element()  # b -> c, crosses into page 1
    assert nxt2["name"] == "c"
    target_id = w.current_elements[2]["element_id"]

    # Page switched to the one containing "c" ...
    assert w.pagination.current_page == 1
    assert w.gallery_view.count() == 2  # page 1 ("c", "d") now rendered

    # ... "c" is actually selected in the freshly rendered view ...
    assert w.get_selected_element_ids() == [target_id]

    # ... and element_selected named that same element, not a stale one.
    assert received[-1] == target_id
    assert target_id not in (
        w.current_elements[0]["element_id"], w.current_elements[1]["element_id"]
    )


@pytest.mark.gui
def test_navigation_works_when_pagination_disabled(qtbot, stax_db, stax_config):
    stax_config.set('pagination_enabled', False)
    _seed_elements(stax_db, ["a", "b", "c"])
    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)
    assert w.pagination.isVisible() is False
    assert w.gallery_view.count() == 3  # all elements rendered, non-paginated path

    first_id = w.current_elements[0]["element_id"]
    first_item = w.element_items[first_id]
    w.gallery_view.setCurrentItem(first_item)
    first_item.setSelected(True)

    received = []
    w.element_selected.connect(received.append)

    nxt = w.select_next_element()
    assert nxt["name"] == "b"
    assert w.get_selected_element_ids() == [w.current_elements[1]["element_id"]]
    assert received[-1] == w.current_elements[1]["element_id"]
