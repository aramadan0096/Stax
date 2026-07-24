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
