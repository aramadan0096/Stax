# -*- coding: utf-8 -*-
"""EP3 Task 8: applying a named layout preset to a real MainWindow.

Design Section 5 requires a headless GUI test: "Selecting a layout preset
produces the expected splitter/dock visibility." The task brief's own test
(`tests/unit/test_ep3_layout.py`) only asserts the shape of the
`LAYOUT_PRESETS` dict and never calls `apply_preset()` -- these tests fill
that gap by building a real `MainWindow` (per the
`_mainwindow_with_temp_db` pattern already used in
`tests/gui/test_ep3_inspector_wiring.py` / `tests/gui/test_ep2_nav.py`)
and applying presets to it.

`Config` reads the `STOCK_DB` env var only at construction time
(src/config.py:107), so `monkeypatch.setenv` must run *before* `Config(...)`
is built -- doing it inside the test body would be too late and the window
would silently build against the real `data/stax.db`. `_mainwindow_with_temp_db`
below sets `STOCK_DB` to a `tmp_path` file first, so no test here ever
touches the real project database.
"""

import pytest

from ui.layout_manager import LAYOUT_PRESETS, preset_names, apply_preset


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    Duplicated from `tests/gui/test_ep3_inspector_wiring.py` /
    `tests/gui/test_ep2_nav.py` so this file stays self-contained, per the
    existing convention in this test suite.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    # `QSplitter.sizes()` and `QWidget.isVisible()` are only meaningful
    # once the window has actually been shown/laid out at least once --
    # before that, Qt hasn't run a real resize/polish pass and both can
    # report stale/default values regardless of what was requested. See
    # `tests/gui/test_ep3_inspector_wiring.py`'s docstring for the same
    # caveat (it works around it by spying on `setSizes()` instead).
    win.show()
    qtbot.waitExposed(win)
    return win


@pytest.mark.gui
def test_apply_browse_preset_sets_exact_splitter_sizes_and_hides_docks(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Assert the exact sizes `apply_preset()` *requests* by spying on
    `setSizes()`, the same technique `test_ep3_inspector_wiring.py` uses --
    the window's default 1400px width is narrower than the sum of some
    presets' `main_sizes` (e.g. Browse's 280+920+360=1560), so Qt
    proportionally redistributes the *rendered* sizes once actually laid
    out, making a plain post-hoc `main_splitter.sizes()` equality check an
    unreliable signal (it would fail even though `apply_preset()` did the
    right thing).

    `video_player_pane.isVisible()` is asserted `False` here, not `True`:
    this window has nothing selected, and Browse's `preview_visible: True`
    means "leave room for the preview", not "force it on". The original
    version of this assertion (`is True`) encoded the bug this test file's
    fix addresses -- it made an empty, unselected preview pane look like
    correct behavior. See `test_fresh_mainwindow_hides_preview_after_startup_restore`
    below for the dedicated regression test."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    requested = []
    real_setSizes = win.main_splitter.setSizes
    monkeypatch.setattr(
        win.main_splitter, "setSizes",
        lambda sizes: (requested.append(list(sizes)), real_setSizes(sizes))[-1],
    )

    apply_preset(win, "Browse")

    assert requested[-1] == LAYOUT_PRESETS["Browse"]["main_sizes"]
    assert win.video_player_pane.isVisible() is False
    assert win.history_dock.isVisible() is False
    assert win.settings_dock.isVisible() is False
    if win.analytics_dock is not None:
        assert win.analytics_dock.isVisible() is False


@pytest.mark.gui
def test_fresh_mainwindow_hides_preview_after_startup_restore(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Regression test for the Important review finding on Task 8: a fresh
    `MainWindow` construction runs `apply_preset()` unconditionally at the
    end of `__init__` to restore the saved layout (defaulting to Browse,
    `preview_visible: True`). Before the fix, that call did
    `video_player_pane.setVisible(True)` whenever the preset allowed a
    preview, showing an empty "No preview available" pane on every launch
    even with nothing selected. `video_player_pane` must stay exactly as
    `setup_ui()` left it (`.hide()`-den) until a real selection triggers
    `on_selection_changed()` -> `expand_preview_pane()`."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    assert win.config.get("layout_preset", "Browse") == "Browse"
    assert win.media_display.get_selected_element_ids() == []
    assert win.video_player_pane.isVisible() is False


@pytest.mark.gui
@pytest.mark.parametrize("name", ["Review", "Curation"])
def test_preview_visible_preset_does_not_force_show_without_selection(
    qtbot, mock_nuke, monkeypatch, tmp_path, name
):
    """Same regression, exercised explicitly for the other two
    `preview_visible: True` presets (Review, Curation) instead of relying
    only on the Browse default."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    assert win.video_player_pane.isVisible() is False

    apply_preset(win, name)

    assert LAYOUT_PRESETS[name]["preview_visible"] is True
    assert win.video_player_pane.isVisible() is False


@pytest.mark.gui
def test_preview_visible_preset_leaves_already_shown_preview_visible(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """The flip side of the regression: a `preview_visible: True` preset
    must not touch visibility at all -- neither forcing it on nor hiding
    it. If the preview is already showing (e.g. the user has a single
    element selected), applying Curation must leave it showing."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    win.video_player_pane.show()
    assert win.video_player_pane.isVisible() is True

    apply_preset(win, "Curation")

    assert win.video_player_pane.isVisible() is True


@pytest.mark.gui
def test_apply_ingest_preset_hides_preview_and_shows_history_dock(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    apply_preset(win, "Ingest")

    # `preview_visible: False` means the video_player_pane specifically is
    # hidden; the right column itself (and the sticky inspector inside it)
    # must stay reachable -- see the dedicated regression test below.
    assert win.video_player_pane.isVisible() is False
    assert win.history_dock.isVisible() is True
    assert win.settings_dock.isVisible() is False
    if win.analytics_dock is not None:
        assert win.analytics_dock.isVisible() is False


@pytest.mark.gui
def test_apply_every_preset_keeps_right_column_and_inspector_reachable(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """No preset -- including Ingest, which hides the preview -- may
    zero the right column. `apply_preset()` must reuse
    `collapse_preview_pane()`'s inspector-derived floor
    (`_right_column_collapsed_width()`) rather than a hardcoded width, so
    this stays correct even if the inspector's minimum size changes."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    for name in preset_names():
        apply_preset(win, name)
        sizes = win.main_splitter.sizes()
        assert win.main_splitter.count() == 3
        assert sizes[2] > 0, (
            "preset {!r} must not drive the right column to width 0 -- "
            "the sticky inspector lives there and must stay reachable".format(name)
        )
        if not LAYOUT_PRESETS[name]["preview_visible"]:
            floor = win._right_column_collapsed_width()
            assert sizes[2] == floor, (
                "preset {!r} hides the preview, so the right column should "
                "sit exactly at collapse_preview_pane()'s reused floor, not "
                "an independently invented width".format(name)
            )


@pytest.mark.gui
def test_apply_preset_persists_selection_under_layout_preset_config_key(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    apply_preset(win, "Curation")
    assert win.config.get("layout_preset") == "Curation"

    apply_preset(win, "Review")
    assert win.config.get("layout_preset") == "Review"


# ---------------------------------------------------------------------------
# Final fix-pass Minor: apply_preset() hides/shows stacks_panel directly
# (see the Finding-3 comment above), bypassing MainWindow.toggle_focus_mode
# entirely -- so MediaDisplayWidget.focus_mode_button (a floating FAB
# inside the media pane, not in the toolbar) kept its old checked state
# and tooltip. Under Review the nav is hidden while the FAB still read
# "Enter focus mode (hide navigation panel)", so the first click on it
# appeared to do nothing (it *was* about to hide already-hidden nav).
# Cosmetic (nothing becomes unreachable), but apply_preset() must keep the
# FAB's displayed state truthful.
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_apply_preset_syncs_focus_button_checked_state_and_tooltip(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    button = win.media_display.focus_mode_button
    assert button.isChecked() is False

    apply_preset(win, "Review")  # main_sizes[0] == 0 -> nav hidden

    assert win.stacks_panel.isVisible() is False
    assert button.isChecked() is True
    assert button.toolTip() == "Exit focus mode (show navigation panel)"

    apply_preset(win, "Browse")  # main_sizes[0] > 0 -> nav restored

    assert win.stacks_panel.isVisible() is True
    assert button.isChecked() is False
    assert button.toolTip() == "Enter focus mode (hide navigation panel)"


@pytest.mark.gui
def test_apply_preset_focus_button_sync_does_not_trigger_mainwindow_toggle(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Syncing the FAB's checked state must be signals-blocked -- it must
    not itself fire MainWindow.toggle_focus_mode (which hides the toolbar/
    docks and re-derives splitter sizes independently of apply_preset's
    own, already-applied sizing)."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(win, "toggle_focus_mode", lambda checked: calls.append(checked))

    apply_preset(win, "Review")
    apply_preset(win, "Browse")

    assert calls == []


@pytest.mark.gui
def test_apply_preset_focus_button_sync_is_noop_without_button(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Guard for shells where MediaDisplayWidget.focus_mode_button doesn't
    exist (e.g. a differently-configured Nuke embed) -- apply_preset must
    not raise."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    win.media_display.focus_mode_button = None

    apply_preset(win, "Review")  # must not raise
