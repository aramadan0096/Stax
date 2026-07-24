import os

import pytest
from PySide2 import QtCore, QtGui

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    return w


def _seed_elements(stax_db, count):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for i in range(count):
            conn.execute(
                "INSERT INTO elements (list_fk, name, type) VALUES (1, ?, '2D')",
                ("elem_{:03d}".format(i),),
            )


# ---------------------------------------------------------------------------
# _skeleton_pixmap: neutral placeholder tile
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_skeleton_pixmap_is_valid(qtbot, stax_db, stax_config):
    w = _widget(qtbot, stax_db, stax_config)
    px = w._skeleton_pixmap(128)
    assert isinstance(px, QtGui.QPixmap)
    assert not px.isNull()
    assert px.width() == 128 and px.height() == 128


@pytest.mark.gui
def test_skeleton_pixmap_accepts_qsize(qtbot, stax_db, stax_config):
    # _build_fixed_thumbnail's dual int/QSize idiom -- _update_views_with_elements
    # calls this with self.gallery_view.iconSize(), a QSize, not an int.
    w = _widget(qtbot, stax_db, stax_config)
    px = w._skeleton_pixmap(QtCore.QSize(64, 64))
    assert isinstance(px, QtGui.QPixmap)
    assert not px.isNull()
    assert px.width() == 64 and px.height() == 64


# ---------------------------------------------------------------------------
# Scroll capture/restore
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_scroll_capture_restore_empty_views_no_raise(qtbot, stax_db, stax_config):
    """The legitimate part of the brief's original test: with nothing
    loaded, capture/restore must not raise."""
    w = _widget(qtbot, stax_db, stax_config)
    w.capture_scroll()
    w.restore_scroll()  # must not raise


@pytest.mark.gui
def test_scroll_capture_restore_round_trip_gallery(qtbot, stax_db, stax_config):
    """Strengthened per the human-approved correction: prove an actual
    round trip, not just "doesn't raise". Populate enough items to make
    the vertical scrollbar genuinely scrollable (verified offscreen: a
    small fixed window + 60 elements at the default 256x256 icon size
    gives a scrollbar maximum in the thousands), scroll away from zero,
    capture, scroll elsewhere, restore, and assert the exact position
    came back.
    """
    _seed_elements(stax_db, 60)
    w = _widget(qtbot, stax_db, stax_config)
    w.resize(500, 400)
    w.show()
    w.load_elements(1)
    qtbot.wait(50)

    bar = w.gallery_view.verticalScrollBar()
    assert bar.maximum() > 0, (
        "scrollbar range collapsed under offscreen QPA -- the round-trip "
        "assertion below would be meaningless without real range"
    )

    known_position = bar.maximum() // 2
    bar.setValue(known_position)
    assert bar.value() == known_position

    w.capture_scroll()

    # Move the scrollbar somewhere else, simulating whatever happens while
    # quicklook is open (e.g. next/prev navigation calling scrollToItem).
    bar.setValue(0)
    assert bar.value() != known_position

    w.restore_scroll()

    assert bar.value() == known_position


@pytest.mark.gui
def test_scroll_capture_restore_round_trip_table_view(qtbot, stax_db, stax_config):
    """Mode-aware decision (see report): quicklook can be opened from either
    view (_select_element_in_view scrollToItem()s whichever of
    gallery_view/table_view is active per self.view_mode), so retention
    must track the currently active view, not gallery_view unconditionally.
    This proves the table_view side of that decision."""
    _seed_elements(stax_db, 60)
    w = _widget(qtbot, stax_db, stax_config)
    w.resize(500, 300)
    w.show()
    w.set_view_mode('list')
    w.load_elements(1)
    qtbot.wait(50)

    bar = w.table_view.verticalScrollBar()
    assert bar.maximum() > 0, (
        "table_view scrollbar range collapsed under offscreen QPA"
    )

    known_position = bar.maximum() // 2
    bar.setValue(known_position)

    w.capture_scroll()
    bar.setValue(0)
    assert bar.value() != known_position

    w.restore_scroll()

    assert bar.value() == known_position


# ---------------------------------------------------------------------------
# Skeleton placement rule (Correction 2):
#   - no GIF and no usable preview file on disk yet -> skeleton
#   - a usable preview file exists -> unchanged type-fallback + lazy-decode
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_no_preview_file_gets_skeleton_not_type_fallback(qtbot, stax_db, stax_config):
    """CORRECTED per whole-branch review Finding 1: the original version of
    this test asserted the tile was a *bare* skeleton -- pure fill colour
    with no type hint at all. That encoded the defect: for elements whose
    preview file will never arrive (toolset registered without a preview,
    generate_previews off, previews dir offline/missing, ...) that bare
    skeleton is never replaced by on_preview_ready and the tile stays a
    featureless grey square forever, indistinguishable from an empty tile
    and a regression from the pre-EP3 type-fallback icon.

    Fix: composite the skeleton *behind* the type-hint icon instead of
    replacing it, so a "no preview file yet" tile still reads "this is a
    2D/3D/Toolset asset" while its skeleton framing still reads as pending.
    This test now asserts both halves of that: skeleton framing at the
    corner, type-hint glyph visibly composited at the center.
    """
    w = _widget(qtbot, stax_db, stax_config)
    elements = [{
        "element_id": 1,
        "name": "pending_elem",
        "type": "2D",
        "preview_path": None,
        "gif_preview_path": None,
    }]

    w._update_views_with_elements(elements)

    item = w.gallery_view.item(0)
    icon_size = w.gallery_view.iconSize()
    image = item.icon().pixmap(icon_size).toImage()

    # _skeleton_pixmap's fill colour, sampled well inside the border stroke:
    # the corner still reads as skeleton (pending framing is preserved).
    assert image.pixelColor(4, 4) == QtGui.QColor("#26282b")

    # The type-hint glyph (film icon for '2D') is composited on top, so the
    # center of the tile is no longer the bare skeleton fill -- the type
    # hint survives even though the preview file doesn't exist yet.
    center = image.width() // 2
    assert image.pixelColor(center, center) != QtGui.QColor("#26282b")

    # There is nothing on disk to lazily decode yet -- on_preview_ready
    # (fired later by SP2's async worker) is what will replace this icon,
    # not the lazy-decode stash used by the "file exists" branch.
    assert item.data(QtCore.Qt.UserRole + 1) is None


@pytest.mark.gui
def test_pending_skeleton_type_hint_differs_by_type(qtbot, stax_db, stax_config):
    """The composited type-hint glyph must actually vary with element type
    (not just always draw the same fallback icon) -- 2D and 3D pending
    tiles must not render identically, or the "type hint" claim is empty."""
    w = _widget(qtbot, stax_db, stax_config)
    elements = [
        {"element_id": 1, "name": "e2d", "type": "2D", "preview_path": None, "gif_preview_path": None},
        {"element_id": 2, "name": "e3d", "type": "3D", "preview_path": None, "gif_preview_path": None},
    ]

    w._update_views_with_elements(elements)

    icon_size = w.gallery_view.iconSize()
    image_2d = w.gallery_view.item(0).icon().pixmap(icon_size).toImage()
    image_3d = w.gallery_view.item(1).icon().pixmap(icon_size).toImage()

    assert image_2d != image_3d


@pytest.mark.gui
def test_existing_preview_file_keeps_type_fallback_and_lazy_stash(qtbot, stax_db, stax_config, tmp_path):
    w = _widget(qtbot, stax_db, stax_config)

    preview_file = tmp_path / "preview.png"
    src_pixmap = QtGui.QPixmap(16, 16)
    src_pixmap.fill(QtGui.QColor("red"))
    assert src_pixmap.save(str(preview_file))

    elements = [{
        "element_id": 2,
        "name": "ready_elem",
        "type": "2D",
        "preview_path": str(preview_file),
        "gif_preview_path": None,
    }]

    w._update_views_with_elements(elements)

    item = w.gallery_view.item(0)

    # Unchanged existing behaviour: type-fallback icon shown immediately,
    # full element dict stashed for _lazy_load_gallery_item to decode when
    # the item scrolls into view.
    assert item.data(QtCore.Qt.UserRole + 1) == elements[0]

    icon_size = w.gallery_view.iconSize()
    image = item.icon().pixmap(icon_size).toImage()
    # Must NOT be the skeleton fill colour -- this is the type-fallback
    # icon (_get_default_icon_for_type / _build_fixed_thumbnail's
    # '#1d2024' card background), not a skeleton.
    assert image.pixelColor(4, 4) != QtGui.QColor("#26282b")


@pytest.mark.gui
def test_on_preview_ready_swaps_out_skeleton(qtbot, stax_db, stax_config, tmp_path):
    """Confirms (rather than assumes) that on_preview_ready still replaces
    whatever icon is currently on the item -- including a skeleton -- with
    the freshly generated real thumbnail, with no change needed to
    on_preview_ready itself."""
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        conn.execute(
            "INSERT INTO elements (list_fk, name, type) VALUES (1, 'ready_soon', '2D')"
        )

    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)

    element_id = w.current_elements[0]["element_id"]
    item = w.element_items[element_id]

    # Before the worker delivers anything: no preview file exists yet, so
    # this item must be showing the skeleton.
    icon_size = w.gallery_view.iconSize()
    image = item.icon().pixmap(icon_size).toImage()
    assert image.pixelColor(4, 4) == QtGui.QColor("#26282b")

    real_preview = tmp_path / "generated_thumb.png"
    real_pixmap = QtGui.QPixmap(32, 32)
    real_pixmap.fill(QtGui.QColor("lime"))
    assert real_pixmap.save(str(real_preview))

    w.on_preview_ready(element_id, str(real_preview), "thumbnail")

    updated_image = item.icon().pixmap(icon_size).toImage()
    assert updated_image.pixelColor(4, 4) != QtGui.QColor("#26282b")
