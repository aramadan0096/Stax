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
def test_admin_flag_reads_from_main_window_not_parent(qtbot, stax_db, stax_config):
    w, mw = _make_widget(qtbot, stax_db, stax_config)
    # Reparent onto a QSplitter to reproduce the real widget tree (main.py:233).
    splitter = QtWidgets.QSplitter()
    qtbot.addWidget(splitter)
    splitter.addWidget(w)
    assert w.parent() is splitter          # the Qt parent has no is_admin

    mw.is_admin = False
    assert w._is_admin_user() is False
    mw.is_admin = True
    assert w._is_admin_user() is True      # resolves via main_window, not parent()
