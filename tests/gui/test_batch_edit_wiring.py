import pytest
from PySide2 import QtWidgets

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


class _FakeMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(_FakeMainWindow, self).__init__()
        self.is_admin = True

    def check_admin_permission(self, action_name="this action"):
        return self.is_admin


def _make_widget(qtbot, stax_db, stax_config):
    mw = _FakeMainWindow()
    qtbot.addWidget(mw)
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_bulk_menu_offers_and_triggers_batch_edit(qtbot, stax_db, stax_config, monkeypatch):
    w = _make_widget(qtbot, stax_db, stax_config)

    monkeypatch.setattr(w, "get_selected_element_ids", lambda: [11, 12])

    called = []
    monkeypatch.setattr(w, "open_batch_edit", lambda element_ids: called.append(list(element_ids)), raising=False)

    class _FakeAction(object):
        def __init__(self, text):
            self.text = text

    class _FakeMenu(object):
        last = None

        def __init__(self, *args, **kwargs):
            self.actions = []
            _FakeMenu.last = self

        def addAction(self, *args):
            text = args[-1]
            action = _FakeAction(text)
            self.actions.append(action)
            return action

        def addSeparator(self):
            return None

        def exec_(self, *args, **kwargs):
            for action in self.actions:
                if action.text == "Batch Edit Metadata...":
                    return action
            return None

    monkeypatch.setattr(QtWidgets, "QMenu", _FakeMenu)

    w.show_bulk_menu()

    assert _FakeMenu.last is not None
    assert "Batch Edit Metadata..." in [a.text for a in _FakeMenu.last.actions]
    assert called == [[11, 12]]
