# -*- coding: utf-8 -*-
"""EP1 Task 9: action tray + context-aware empty states wired into
MediaDisplayWidget."""

import pytest
from PySide2 import QtWidgets

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


class _FakeMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(_FakeMainWindow, self).__init__()
        self.is_admin = False

    def check_admin_permission(self, action_name="this action"):
        return self.is_admin


def _make_widget(qtbot, stax_db, stax_config):
    mw = _FakeMainWindow()
    qtbot.addWidget(mw)
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w, mw


@pytest.mark.gui
def test_tray_shows_on_multiselect(qtbot, stax_db, stax_config):
    w, mw = _make_widget(qtbot, stax_db, stax_config)
    w.action_tray.set_selection([1, 2])
    assert w.action_tray.isHidden() is False


@pytest.mark.gui
def test_empty_state_library_has_ingest_action(qtbot, stax_db, stax_config):
    w, mw = _make_widget(qtbot, stax_db, stax_config)
    w._show_empty_state("library")
    assert w.current_empty_state.primary_button.text().lower().startswith("ingest")


@pytest.mark.gui
def test_tag_zero_match_resets_stale_empty_page(qtbot, stax_db, stax_config):
    """Fix 1 regression: a zero-match tag filter must reset the nested
    empty-page stack to the legacy page, not leave a previously-installed
    EP1 page (e.g. from an earlier search) stuck on screen.

    Asserting on content_stack.currentIndex() alone would pass vacuously
    (it's 0 in both the buggy and fixed behaviour); the real bug is which
    widget is current on the *nested* _empty_page_stack.
    """
    w, mw = _make_widget(qtbot, stax_db, stax_config)

    # Install an EP1 empty page (as a prior search-with-no-matches would).
    w._show_empty_state("search", query="zzz")
    assert w._empty_page_stack.currentWidget() is w.current_empty_state

    # Drive the zero-match load_elements_by_tags path.
    w.load_elements_by_tags(["nonexistent_tag_zzz"])

    assert w.content_stack.currentIndex() == 0
    assert w._empty_page_stack.currentWidget() is w.empty_state_widget
