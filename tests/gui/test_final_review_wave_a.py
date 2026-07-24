# -*- coding: utf-8 -*-
"""Final whole-branch review (exec/ep3), Wave A.

Finding 1: the StartPage installed at MainWindow construction
(main.py:260-267) used to be destroyed the first time any EP1 empty state
replaced it on the nested `media_display._empty_page_stack` (via
`_set_empty_page_widget`'s `previous.deleteLater()`), and nothing ever
re-installed it -- `MainWindow.start_page` became a dangling wrapper
around a deleted C++ object, and returning to "nothing selected" showed
EP1's generic "library" empty page instead of the personalized start page.
"""

import pytest

from ui.layout_manager import LAYOUT_PRESETS, apply_preset


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    Same pattern as `tests/gui/test_ep3_layout_apply.py` /
    `tests/gui/test_ep3_inspector_wiring.py`, duplicated here so this file
    stays self-contained. `Config` reads `STOCK_DB` only at construction
    time, so the env var must be set before `Config(...)` is built.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    # QSplitter.sizes() / QWidget.isVisible() are only meaningful once the
    # window has actually been shown/laid out at least once (see
    # test_ep3_layout_apply.py's docstring for the same caveat) -- Finding
    # 3's tests below need real splitter geometry and real hide()/show()
    # visibility, not just construction to succeed.
    win.show()
    qtbot.waitExposed(win)
    return win


def _empty_list(db):
    """One stack, one list, zero elements."""
    db.create_stack("S", "/tmp/S")
    with db.get_connection() as conn:
        cur = conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'Empty')")
        return cur.lastrowid


@pytest.mark.gui
def test_start_page_survives_empty_state_and_returns_on_no_selection(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    # StartPage is installed as the empty page at construction.
    assert win.media_display._empty_page_stack.currentWidget() is win.start_page

    # Selecting an empty list must still route through EP1's own
    # context-aware "list" empty state -- that path is untouched.
    list_id = _empty_list(win.db)
    win.on_list_selected(list_id)
    current = win.media_display._empty_page_stack.currentWidget()
    assert current is win.media_display.current_empty_state
    assert current is not win.start_page

    # The StartPage must still be a *live* widget -- refresh() must not
    # raise RuntimeError("Internal C++ object ... already deleted").
    win.start_page.refresh()

    # Returning to "nothing selected" must re-show the live StartPage, not
    # EP1's generic library empty page.
    win.active_view = ("none", None)
    win.restore_active_view()
    assert win.media_display._empty_page_stack.currentWidget() is win.start_page
    win.start_page.refresh()  # still alive; must not raise


@pytest.mark.gui
def test_ep1_list_empty_state_still_shown_on_its_own_path(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Regression guard: this fix must not eject EP1's own empty-state
    wiring -- selecting an empty list must show the contextual "This list
    is empty" page, never the StartPage or the legacy generic page."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    list_id = _empty_list(win.db)
    win.on_list_selected(list_id)

    assert win.media_display.current_empty_state is not None
    assert "empty" in win.media_display.current_empty_state.headline_label.text().lower()


# ---------------------------------------------------------------------------
# Finding 2: the Accessibility tab must not restyle the whole host
# QApplication -- inside Nuke that is Nuke's own QApplication, so toggling
# High contrast used to black out the entire DCC UI.
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_accessibility_target_widget_changes_without_touching_qapplication(
    qtbot, stax_db, stax_config
):
    from PySide2 import QtWidgets

    from ui.accessibility import reset_cache
    from ui.settings_panel import SettingsPanel

    app = QtWidgets.QApplication.instance()
    reset_cache()
    original_app_qss = app.styleSheet()
    original_app_pt = app.font().pointSize()

    target = QtWidgets.QWidget()
    qtbot.addWidget(target)

    panel = SettingsPanel(stax_config, stax_db, accessibility_target=target)
    qtbot.addWidget(panel)

    panel.a11y_high_contrast_checkbox.setChecked(True)

    # The target widget picked up the high-contrast overlay...
    assert "#000000" in target.styleSheet()
    # ...but the QApplication -- Nuke's own, in the embedded shell -- is
    # completely untouched.
    assert app.styleSheet() == original_app_qss
    assert app.font().pointSize() == original_app_pt


@pytest.mark.nuke
def test_staxpanel_applies_persisted_accessibility_at_startup_scoped_to_panel(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """nuke_launcher.StaXPanel must honor an already-persisted a11y
    preference at startup (previously inert until the user re-toggled it
    in Settings), and must apply it to the panel widget, not to Nuke's own
    QApplication."""
    from PySide2 import QtWidgets

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)

    import json
    import os

    os.makedirs(str(tmp_path / "config"), exist_ok=True)
    with open(str(tmp_path / "config" / "config.json"), "w") as f:
        json.dump({"a11y_high_contrast": True}, f)

    from ui.accessibility import reset_cache
    reset_cache()

    app = QtWidgets.QApplication.instance()
    original_app_qss = app.styleSheet()

    import nuke_launcher

    # Neutralize the QTimer.singleShot(100, self.show_login) StaXPanel.
    # __init__ schedules in standalone/mock mode -- left live, it fires
    # ~100ms later, possibly after this test (and its panel) has already
    # torn down, tripping a RuntimeError in a later test's event-loop
    # processing (confirmed by temporarily removing all neutralization:
    # with none at all, that exact RuntimeError is raised against this
    # panel's already-deleted widgets, attributed to an unrelated *later*
    # test since Qt only surfaces it once something else pumps the event
    # loop).
    #
    # Whole-branch re-review Minor: a bare class-wide
    # `monkeypatch.setattr(QtCore.QTimer, "singleShot", lambda *a, **k:
    # None)` (this line's previous form) is too blunt -- it silently
    # swallows every OTHER deferred callback scheduled anywhere in the
    # process while active too, e.g. MediaDisplayWidget's own gallery
    # `refresh_visible` kick, not just this one login modal. The suggested
    # narrower fix -- patching `StaXPanel.show_login` directly to a no-op
    # and leaving `singleShot` itself alone -- turns out to trade that
    # problem for a different one: it still lets a real QTimer object get
    # scheduled (it only neutralizes what fires 100ms later, not whether
    # anything gets scheduled at all), and that dangling live timer was
    # observed to intermittently destabilize *other*, unrelated tests
    # later in this same file when run in the same process -- its
    # harmless no-op firing during a later test's own event-loop pump
    # reproducibly tripped pytest-qt's "Exceptions caught in Qt event
    # loop" teardown machinery in a handful of runs out of a dozen.
    #
    # Wrapping `singleShot` to skip scheduling *only* calls whose target
    # is `StaXPanel.show_login` gets both properties at once: no real
    # timer for the login callback is ever created (matching the original
    # blunt patch's safety), while every unrelated `singleShot` call --
    # present or future, e.g. the gallery kick -- still runs through the
    # real implementation, untouched.
    _real_single_shot = nuke_launcher.QtCore.QTimer.singleShot

    def _skip_show_login_timer(msec, callback, *args, **kwargs):
        if getattr(callback, "__func__", None) is nuke_launcher.StaXPanel.show_login:
            return None
        return _real_single_shot(msec, callback, *args, **kwargs)

    monkeypatch.setattr(nuke_launcher.QtCore.QTimer, "singleShot", _skip_show_login_timer)

    panel = nuke_launcher.StaXPanel()
    qtbot.addWidget(panel)

    assert "#000000" in panel.styleSheet()
    assert app.styleSheet() == original_app_qss


@pytest.mark.gui
def test_login_timer_neutralization_does_not_suppress_other_singleshot_callbacks(
    qtbot, monkeypatch
):
    """Regression guard for the scoping fix above: the neutralization
    must skip scheduling *only* the `StaXPanel.show_login` callback --
    every other `QtCore.QTimer.singleShot` call, present or future (e.g.
    MediaDisplayWidget's own gallery `refresh_visible` kick), must still
    run through the real Qt implementation."""
    from PySide2 import QtCore

    import nuke_launcher

    _real_single_shot = nuke_launcher.QtCore.QTimer.singleShot

    def _skip_show_login_timer(msec, callback, *args, **kwargs):
        if getattr(callback, "__func__", None) is nuke_launcher.StaXPanel.show_login:
            return None
        return _real_single_shot(msec, callback, *args, **kwargs)

    monkeypatch.setattr(nuke_launcher.QtCore.QTimer, "singleShot", _skip_show_login_timer)

    # The show_login target: bound via types.MethodType directly against
    # the wrapper function (not through QtCore.QTimer.singleShot, and
    # never actually invoked) so this assertion can't accidentally run
    # the real dialog-opening body.
    import types

    class _Dummy(object):
        pass

    bound_show_login = types.MethodType(nuke_launcher.StaXPanel.show_login, _Dummy())
    assert _skip_show_login_timer(100, bound_show_login) is None, (
        "a singleShot call targeting StaXPanel.show_login must be "
        "skipped (never scheduled), not merely neutered once it fires"
    )

    # Any other callback -- unrelated to show_login -- must still be
    # scheduled and fire normally through the real Qt implementation.
    fired = []
    QtCore.QTimer.singleShot(0, lambda: fired.append(True))
    qtbot.wait(50)

    assert fired == [True], (
        "an unrelated QtCore.QTimer.singleShot callback must still fire "
        "-- the scoped neutralization must not collaterally suppress it "
        "the way the old class-wide stub did"
    )


# ---------------------------------------------------------------------------
# Finding 3: the Review/Ingest/Curation layout presets were undone by the
# very next click -- setChildrenCollapsible(False) means a preset's
# main_sizes[0]==0 (Review's collapsed nav) can never actually collapse via
# setSizes() alone, and expand_preview_pane() reads a preview_pane_expanded_
# width that apply_preset() never updates, so the first single selection
# snaps Review's 860px preview column back to the constructor's stale 360.
# ---------------------------------------------------------------------------


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


@pytest.mark.gui
def test_review_preset_collapses_nav_via_hide_not_a_clamped_zero_size(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Review's main_sizes[0] is 0 -- but main_splitter.setChildrenCollapsible
    (False) means Qt clamps a bare setSizes([0, ...]) request back up to
    stacks_panel's minimumWidth(). apply_preset() must actually hide the
    nav (the same hide()/show() path toggle_focus_mode already uses) so
    "nav collapsed" -- Review's defining property per spec Sec3.6 -- really
    happens, and must restore it when switching to a preset that wants the
    nav back."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    assert win.stacks_panel.isVisible() is True

    apply_preset(win, "Review")
    assert win.stacks_panel.isVisible() is False

    apply_preset(win, "Browse")
    assert win.stacks_panel.isVisible() is True


@pytest.mark.gui
def test_review_preset_preview_width_survives_a_subsequent_selection(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """apply_preset() must update preview_pane_expanded_width from the
    preset's own right-column size, so the first single-selection after
    picking Review expands the preview back to Review's 860px column
    instead of snapping to the constructor's stale 360px default."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    eid_a, _eid_b = _two_elements(win.db)

    # The app's real default window size (main.py: self.resize(1400, 800)).
    # This is the bracket that matters: expand_preview_pane()'s separate
    # "at most 1/3 of available space" heuristic is tight enough here that
    # a naive `min(expanded_width, available // 3)` cap clips Review's
    # remembered 860px column right back down to ~370 -- byte-identical to
    # the pre-fix behavior -- even though preview_pane_expanded_width was
    # correctly updated by apply_preset(). Only a window resized well past
    # every preset's main_sizes (e.g. 3000x900) would hide that clipping,
    # so this test asserts at the size that actually exercises it.
    win.resize(1400, 800)
    qtbot.wait(50)

    apply_preset(win, "Review")
    assert win.preview_pane_expanded_width == LAYOUT_PRESETS["Review"]["main_sizes"][2]

    monkeypatch.setattr(win.video_player_pane, "load_element", lambda eid_: None)
    monkeypatch.setattr(win.media_display, "get_selected_element_ids", lambda: [eid_a])
    win.on_selection_changed()

    preview_width = win.main_splitter.sizes()[2]
    assert preview_width >= 600, (
        "Review's preview column (main_sizes[2]=860) must substantially "
        "survive a subsequent single selection at the app's default "
        "1400x800 window size, not snap back down to ~360-400 the way it "
        "did before the explicit-preset-width cap fix (got {})".format(
            preview_width
        )
    )

    center_width = win.main_splitter.sizes()[1]
    assert center_width >= 400, (
        "the center pane's floor must hold even when the remembered "
        "preset width is allowed past the available//3 cap (got {})".format(
            center_width
        )
    )


@pytest.mark.gui
def test_apply_every_preset_never_zeroes_right_column_after_this_fix(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Regression guard: Task 6's collapse_preview_pane() floor (keeping
    the sticky inspector reachable) must survive this fix -- Ingest's
    collapsed preview must still sit at the inspector-derived floor, never
    at width 0, and preview_pane_expanded_width must not be poisoned by
    Ingest's placeholder 240 (the module docstring is explicit that value
    is a shape-valid placeholder, not a real remembered width)."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    apply_preset(win, "Review")
    remembered = win.preview_pane_expanded_width
    assert remembered == 860

    apply_preset(win, "Ingest")
    floor = win._right_column_collapsed_width()
    assert win.main_splitter.sizes()[2] == floor
    # Ingest's placeholder 240 must not have overwritten the real
    # remembered preview width from Review.
    assert win.preview_pane_expanded_width == remembered


# ---------------------------------------------------------------------------
# "Also fix": StartPage card activation must select the element / open its
# list (spec Sec3.9), not insert it into Nuke like a gallery double-click.
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_start_page_activation_selects_and_reveals_not_inserts(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    eid_a, eid_b = _two_elements(win.db)

    insert_calls = []
    monkeypatch.setattr(
        win.nuke_integration, "insert_element", lambda eid_: insert_calls.append(eid_)
    )
    # Isolate from VideoPlayerWidget's real media-loading logic (the
    # selection this test drives fires on_selection_changed ->
    # video_player_pane.load_element for a fake element with no real
    # media file on disk) -- same isolation test_ep3_inspector_wiring.py
    # uses; only the activation wiring is under test here.
    monkeypatch.setattr(win.video_player_pane, "load_element", lambda eid_: None)

    win.start_page.element_activated.emit(eid_a)

    assert insert_calls == [], "activating a start-page card must not insert into Nuke"
    assert win.media_display.current_list_id == 1
    assert win.media_display.get_selected_element_ids() == [eid_a]
