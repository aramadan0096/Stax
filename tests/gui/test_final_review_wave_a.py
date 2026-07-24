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

    panel = nuke_launcher.StaXPanel()
    qtbot.addWidget(panel)

    assert "#000000" in panel.styleSheet()
    assert app.styleSheet() == original_app_qss
