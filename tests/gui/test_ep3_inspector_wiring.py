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
