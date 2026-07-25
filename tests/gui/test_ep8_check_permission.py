import pytest


@pytest.mark.gui
def test_check_permission_uses_role_matrix(qtbot, stax_db, stax_config, monkeypatch):
    stax_db.create_user("rev", "pw", role="reviewer")
    from main import MainWindow
    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)
    win.db = stax_db            # use the seeded roles DB instead of the one MainWindow built
    win.current_user = {"username": "rev", "role": "reviewer", "user_id": 2}
    win.is_admin = False
    monkeypatch.setattr("PySide2.QtWidgets.QMessageBox.warning", lambda *a, **k: None)
    assert win.check_permission("can_edit_metadata") is True
    assert win.check_permission("can_delete") is False
