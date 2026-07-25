"""EP8 wiring: the granular check_permission gate must actually guard the
ingest / delete / metadata-edit actions (Task 3's 'switch the call sites' step,
which was never executed). Denial must block the action; success on delete/edit
must attribute the actor in the activity log.
"""

import pytest
from PySide2 import QtWidgets

from ui.media_display_widget import MediaDisplayWidget
import ui.media_display_widget as mdw_mod
from nuke_bridge import NukeBridge


class _FakeMW(QtWidgets.QMainWindow):
    """Records which gate a widget consults and answers allow/deny."""

    def __init__(self, allow):
        super(_FakeMW, self).__init__()
        self._allow = allow
        self.is_admin = False
        self.current_user = {"username": "rev", "role": "reviewer", "user_id": 2}
        self.perm_calls = []
        self.admin_calls = []

    def check_permission(self, permission, action_name="this action"):
        self.perm_calls.append(permission)
        return self._allow

    def check_admin_permission(self, action_name="this action"):
        self.admin_calls.append(action_name)
        return False


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    eid = stax_db.create_element(lid, "e1", "2D", format="exr")
    return lid, eid


def _widget(qtbot, stax_db, stax_config, mw):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_delete_element_gated_on_can_delete_not_admin(qtbot, stax_db, stax_config, mock_nuke):
    lid, eid = _seed(stax_db)
    mw = _FakeMW(allow=False)
    qtbot.addWidget(mw)
    w = _widget(qtbot, stax_db, stax_config, mw)

    w.delete_element(eid)

    assert "can_delete" in mw.perm_calls      # granular gate consulted...
    assert mw.admin_calls == []               # ...not the old binary admin gate
    assert stax_db.get_element_by_id(eid) is not None   # denied -> element survives


@pytest.mark.gui
def test_delete_element_allowed_logs_actor(qtbot, stax_db, stax_config, mock_nuke, monkeypatch):
    lid, eid = _seed(stax_db)
    mw = _FakeMW(allow=True)
    qtbot.addWidget(mw)
    w = _widget(qtbot, stax_db, stax_config, mw)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    w.delete_element(eid)

    assert stax_db.get_element_by_id(eid) is None
    with stax_db.get_connection(write=False) as conn:
        rows = conn.execute(
            "SELECT actor, action FROM activity_log WHERE action = 'delete'").fetchall()
    assert any(r["actor"] == "rev" for r in rows)   # attributed to the acting user


@pytest.mark.gui
def test_edit_element_gated_on_can_edit_metadata(qtbot, stax_db, stax_config, mock_nuke, monkeypatch):
    lid, eid = _seed(stax_db)
    mw = _FakeMW(allow=False)
    qtbot.addWidget(mw)
    w = _widget(qtbot, stax_db, stax_config, mw)
    constructed = []

    class _FakeDialog(object):
        def __init__(self, *a, **k):
            constructed.append(1)

        def exec_(self):
            return QtWidgets.QDialog.Rejected

    monkeypatch.setattr(mdw_mod, "EditElementDialog", _FakeDialog)

    w.edit_element(eid)

    assert "can_edit_metadata" in mw.perm_calls
    assert constructed == []   # denied -> the edit dialog is never built


# The ingest gates live on MainWindow. Constructing a full MainWindow headless
# spawns real QThreads + a QWebEngineView and is teardown-crash-prone, so these
# call the gate methods unbound with a minimal fake `self` — the denied path
# returns at the gate and never reaches the file dialog / library dialog.


@pytest.mark.gui
def test_ingest_files_gated_on_can_ingest(monkeypatch):
    import types as _types
    from main import MainWindow

    calls = []
    opened = []
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (opened.append(1), ([], ""))[1]))
    fake = _types.SimpleNamespace(
        check_permission=lambda perm, action_name="x": (calls.append(perm), False)[1])

    MainWindow.ingest_files(fake)

    assert calls == ["can_ingest"]   # gated on the right permission...
    assert opened == []              # ...and denied before the file picker opens


@pytest.mark.gui
def test_ingest_library_gated_on_can_ingest(monkeypatch):
    import types as _types
    import main as mainmod

    calls = []
    built = []
    monkeypatch.setattr(mainmod, "IngestLibraryDialog", lambda *a, **k: built.append(1))
    fake = _types.SimpleNamespace(
        check_permission=lambda perm, action_name="x": (calls.append(perm), False)[1])

    mainmod.MainWindow.ingest_library(fake)

    assert calls == ["can_ingest"]
    assert built == []               # denied before the library dialog is built
