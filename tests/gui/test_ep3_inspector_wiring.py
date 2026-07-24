# -*- coding: utf-8 -*-
"""EP3 Task 6 review fix: `main.py`'s right-pane wiring must keep the
sticky inspector (design SS3.4) reachable regardless of selection state.

Before this fix, `on_selection_changed()`'s multi-selection branch called
`collapse_preview_pane()`, which drove `main_splitter`'s 3rd column
straight to a requested width of 0 -- correct back when that column WAS
the preview, but wrong now that `right_splitter` nests `video_player_pane`
and `InspectorPanel` together in that column: requesting 0 also targets
the always-should-be-reachable inspector, including its "No selection"
state. The empty-selection branch never re-requested a width either, so a
multi-select -> deselect-all sequence left nothing to recover it.

Note: `main_splitter.setChildrenCollapsible(False)` plus the inspector's
own non-zero `minimumSizeHint()` mean Qt often clamps the *rendered*
column width above 0 regardless of what's requested, which would make
plain `main_splitter.sizes()` assertions an unreliable RED/GREEN signal.
These tests instead spy on `main_splitter.setSizes()` to check what width
`collapse_preview_pane()` actually *requests* for the 3rd column -- that
is the direct, deterministic expression of the bug and the fix.

These tests build a real `MainWindow` (per the EP2 Task 9
`_mainwindow_with_temp_db` pattern in `test_ep2_nav.py`, duplicated here so
this file stays self-contained) and assert the *wiring*, not just that
construction succeeds.
"""

import pytest


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    `Config` reads STOCK_DB only at construction time (src/config.py:107),
    so the env var must be set *before* `Config(...)` is built -- a
    `monkeypatch.setenv` inside the test body comes too late once a
    `Config` object already exists (e.g. the shared `stax_config` fixture),
    and `MainWindow` would silently build against the real project database
    at `./data/stax.db` instead of an isolated tmp_path db. Same helper as
    `tests/gui/test_ep2_nav.py::_mainwindow_with_temp_db`.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


def _two_elements(db):
    """One stack/list, two distinct elements ('a', 'b'). Returns their ids."""
    db.create_stack("S", "/tmp/S")
    with db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        cur_a = conn.execute(
            "INSERT INTO elements (list_fk,name,type,file_size) VALUES (1,'a','2D',2048)"
        )
        cur_b = conn.execute(
            "INSERT INTO elements (list_fk,name,type,file_size) VALUES (1,'b','2D',2048)"
        )
        return cur_a.lastrowid, cur_b.lastrowid


def _spy_setSizes(monkeypatch, splitter):
    """Record every `sizes` list passed to `splitter.setSizes()` while
    still performing the real resize, so assertions can inspect exactly
    what width was *requested* for each column."""
    requested = []
    real_setSizes = splitter.setSizes

    def _spy(sizes):
        requested.append(list(sizes))
        return real_setSizes(sizes)

    monkeypatch.setattr(splitter, "setSizes", _spy)
    return requested


@pytest.mark.gui
def test_main_splitter_has_exactly_three_children(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    assert win.main_splitter.count() == 3


@pytest.mark.gui
def test_multi_selection_keeps_right_column_reachable_and_clears_inspector(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    eid_a, eid_b = _two_elements(win.db)
    requested = _spy_setSizes(monkeypatch, win.main_splitter)

    # Put the inspector in a known "showing something" state first.
    win.inspector.show_element(eid_a)
    assert win.inspector.isEnabled() is True

    monkeypatch.setattr(
        win.media_display, "get_selected_element_ids", lambda: [eid_a, eid_b]
    )
    win.on_selection_changed()

    assert win.main_splitter.count() == 3
    assert requested, "collapse_preview_pane() must resize main_splitter"
    assert requested[-1][2] > 0, (
        "collapse_preview_pane() must not request width 0 for the right "
        "column -- InspectorPanel now lives in that column too and must "
        "stay reachable, including its 'No selection' state"
    )
    # The inspector itself must have been cleared.
    assert win.inspector.isEnabled() is False


@pytest.mark.gui
def test_multiselect_then_deselect_all_keeps_right_column_reachable(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    eid_a, eid_b = _two_elements(win.db)
    requested = _spy_setSizes(monkeypatch, win.main_splitter)

    monkeypatch.setattr(
        win.media_display, "get_selected_element_ids", lambda: [eid_a, eid_b]
    )
    win.on_selection_changed()
    assert requested[-1][2] > 0

    monkeypatch.setattr(win.media_display, "get_selected_element_ids", lambda: [])
    win.on_selection_changed()

    assert win.main_splitter.count() == 3
    # The empty-selection branch does not itself resize the splitter, so
    # the last *requested* width is still the one from the multi-select
    # collapse above -- it must remain nonzero, not the pre-fix 0.
    assert requested[-1][2] > 0, (
        "after multi-select -> deselect-all the right column must still be "
        "reachable, not stuck at a requested width of 0"
    )
    assert win.main_splitter.sizes()[2] > 0
    assert win.inspector.isEnabled() is False


@pytest.mark.gui
def test_single_selection_expands_preview_and_shows_element_in_inspector(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    eid_a, _eid_b = _two_elements(win.db)

    expand_calls = []
    real_expand = win.expand_preview_pane
    monkeypatch.setattr(
        win, "expand_preview_pane",
        lambda: (expand_calls.append(True), real_expand())[-1],
    )

    # Isolate this test from VideoPlayerWidget's real media-loading/dialog
    # logic (covered elsewhere, e.g. test_video_player_previews_root.py) --
    # only the *wiring* (is expand called, is load_element called, does the
    # inspector show the element) is under test here.
    load_calls = []
    monkeypatch.setattr(
        win.video_player_pane, "load_element", lambda eid_: load_calls.append(eid_)
    )

    monkeypatch.setattr(win.media_display, "get_selected_element_ids", lambda: [eid_a])
    win.on_selection_changed()

    assert expand_calls == [True], "single-selection must still expand the preview pane"
    assert load_calls == [eid_a]
    assert win.inspector.isEnabled() is True
    assert win.inspector.name_edit.text() == "a"
    assert win.main_splitter.count() == 3


@pytest.mark.gui
def test_repeated_collapse_does_not_corrupt_remembered_preview_width(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Regression guard for a related ordering bug this fix also closes:
    the old code captured `preview_pane_expanded_width` from
    `main_splitter.sizes()[2]` *after* a previous collapse had already
    narrowed it, silently forgetting the real preferred preview width on
    a second collapse call in a row."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    eid_a, _eid_b = _two_elements(win.db)
    monkeypatch.setattr(win.video_player_pane, "load_element", lambda eid_: None)

    monkeypatch.setattr(win.media_display, "get_selected_element_ids", lambda: [eid_a])
    win.on_selection_changed()
    expanded_width = win.preview_pane_expanded_width
    assert expanded_width > 0

    win.collapse_preview_pane()
    once_collapsed = win.preview_pane_expanded_width
    win.collapse_preview_pane()
    twice_collapsed = win.preview_pane_expanded_width

    assert once_collapsed == expanded_width
    assert twice_collapsed == expanded_width, (
        "a repeated collapse_preview_pane() call must not overwrite "
        "preview_pane_expanded_width with the already-collapsed width"
    )


# ---------------------------------------------------------------------------
# Whole-branch review Finding 3: element_updated -> refresh_item_badge ->
# _refresh_item previously only ever touched the gallery QListWidgetItem's
# icon (`self.element_items` holds gallery items exclusively). Two gaps:
#   - in list/table view, a rating/label edit produced no visible change at
#     all until the list was reloaded (Rating/Label columns untouched);
#   - _commit_name/_commit_tags/_commit_comment never emitted
#     element_updated at all, so renaming/retagging/commenting via the
#     inspector left the gallery caption and the table's Name/Comment cells
#     showing stale values.
# These tests wire MediaDisplayWidget + InspectorPanel exactly the way
# main.py does (inspector.element_updated -> media_display.refresh_item_badge)
# and exercise both view modes directly, without needing a full MainWindow.
# ---------------------------------------------------------------------------

from PySide2 import QtCore

from ui.media_display_widget import MediaDisplayWidget
from ui.inspector_panel import InspectorPanel
from nuke_bridge import NukeBridge


def _wired_widget(qtbot, stax_db, stax_config):
    """MediaDisplayWidget + InspectorPanel wired identically to main.py's
    `self.inspector.element_updated.connect(self.media_display.refresh_item_badge)`."""
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.element_updated.connect(w.refresh_item_badge)
    return w, ip


def _one_element(stax_db):
    """One stack/list/element with a known rating/tags/comment so edits are
    detectable against a non-default baseline. Returns the element id."""
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        cur = conn.execute(
            "INSERT INTO elements (list_fk,name,type,file_size,rating,tags,comment) "
            "VALUES (1,'orig_name','2D',1000,2,'orig_tag','orig_comment')"
        )
        return cur.lastrowid


def _table_row_for(w, element_id):
    for row in range(w.table_view.rowCount()):
        cell = w.table_view.item(row, 0)
        if cell is not None and cell.data(QtCore.Qt.UserRole) == element_id:
            return row
    return None


@pytest.mark.gui
def test_inspector_rating_edit_updates_table_row(qtbot, stax_db, stax_config):
    eid = _one_element(stax_db)
    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.set_view_mode('list')
    w.load_elements(1)
    ip.show_element(eid)

    row = _table_row_for(w, eid)
    assert row is not None
    assert w.table_view.item(row, 6).text() == "★★"  # rating 2

    ip.set_rating(4)

    assert w.table_view.item(row, 6).text() == "★★★★"


@pytest.mark.gui
def test_inspector_label_edit_updates_table_row(qtbot, stax_db, stax_config):
    eid = _one_element(stax_db)
    labels = stax_db.get_labels()
    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.set_view_mode('list')
    w.load_elements(1)
    ip.show_element(eid)

    row = _table_row_for(w, eid)
    label_id = labels[0]["label_id"]
    ip.label_combo.setCurrentIndex(ip.label_combo.findData(label_id))

    label_item = w.table_view.item(row, 7)
    assert label_item.toolTip() == labels[0]["name"]


@pytest.mark.gui
def test_inspector_name_edit_updates_gallery_caption(qtbot, stax_db, stax_config):
    eid = _one_element(stax_db)
    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.load_elements(1)
    ip.show_element(eid)

    item = w.element_items[eid]
    assert item.text() == "orig_name [orig_tag]"

    ip.name_edit.setText("renamed")
    ip.name_edit.editingFinished.emit()

    assert item.text() == "renamed [orig_tag]"


@pytest.mark.gui
def test_inspector_tags_edit_updates_gallery_caption(qtbot, stax_db, stax_config):
    eid = _one_element(stax_db)
    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.load_elements(1)
    ip.show_element(eid)

    item = w.element_items[eid]

    ip.tags_edit.setText("new_tag, extra")
    ip.tags_edit.editingFinished.emit()

    assert item.text() == "orig_name [new_tag, extra]"


@pytest.mark.gui
def test_inspector_name_edit_also_updates_table_row_name_column(qtbot, stax_db, stax_config):
    eid = _one_element(stax_db)
    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.set_view_mode('list')
    w.load_elements(1)
    ip.show_element(eid)
    row = _table_row_for(w, eid)

    ip.name_edit.setText("renamed_row")
    ip.name_edit.editingFinished.emit()

    assert w.table_view.item(row, 0).text() == "renamed_row"


@pytest.mark.gui
def test_inspector_comment_edit_updates_table_comment_column(qtbot, stax_db, stax_config):
    eid = _one_element(stax_db)
    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.set_view_mode('list')
    w.load_elements(1)
    ip.show_element(eid)
    row = _table_row_for(w, eid)

    ip.comment_edit.setText("new comment")
    ip.comment_edit.editingFinished.emit()

    assert w.table_view.item(row, 5).text() == "new comment [Tags: orig_tag]"


# ---------------------------------------------------------------------------
# Final fix-pass Minor: _refresh_item's `pixmap = self._load_preview_pixmap
# (...)` returns None for an element with no GIF and no preview file on
# disk (EP3 Task 7's pending-skeleton population -- a toolset registered
# with no preview, a library ingested with generate_previews off, an
# offline previews dir, ...). The old `if pixmap: item.setIcon(...)` guard
# then skipped the repaint entirely, so a rating/label edit on exactly
# that population never moved the gallery badge. _refresh_item must fall
# back to the same skeleton-with-badges tile _update_views_with_elements
# would render, so the edit's badge actually repaints.
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inspector_rating_edit_repaints_gallery_badge_when_no_preview_file(
    qtbot, stax_db, stax_config
):
    eid = _one_element(stax_db)  # rating=2, preview_path/gif_preview_path NULL
    # A label's badge is a solid-colour fillRect (unlike the star strip,
    # which is drawn text and can be a no-op under the offscreen platform's
    # missing font directory) -- assert against that so the test isolates
    # the fallback wiring itself, not font rendering.
    labels = stax_db.get_labels()
    assert labels, "expected default labels to be seeded"
    stax_db.set_element_label(eid, labels[0]["label_id"])

    w, ip = _wired_widget(qtbot, stax_db, stax_config)
    w.load_elements(1)
    ip.show_element(eid)

    item = w.element_items[eid]
    icon_size = w.gallery_view.iconSize()
    before_image = item.icon().pixmap(icon_size).toImage()

    ip.set_rating(4)

    after_image = item.icon().pixmap(icon_size).toImage()
    assert after_image != before_image, (
        "the gallery badge for a no-preview-file element must repaint "
        "after an inspector rating edit (on the pending-skeleton tile), "
        "not stay frozen at its pre-edit rendering"
    )
