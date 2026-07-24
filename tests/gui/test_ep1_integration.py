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
