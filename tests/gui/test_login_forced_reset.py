import pytest
from PySide2 import QtWidgets

from ui.dialogs import LoginDialog


@pytest.mark.gui
def test_login_blocks_when_forced_password_change_cancelled(qtbot, stax_db, monkeypatch):
    user_id = stax_db.create_user("forced_user", "secret123", role="user")
    with stax_db.get_connection() as conn:
        conn.execute(
            "UPDATE users SET must_change_password = 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()

    dlg = LoginDialog(stax_db)
    qtbot.addWidget(dlg)
    dlg.username_edit.setText("forced_user")
    dlg.password_edit.setText("secret123")

    calls = []
    monkeypatch.setattr(
        dlg,
        "_force_password_change",
        lambda user: calls.append(user["user_id"]) or False,
        raising=False,
    )

    dlg.attempt_login()

    assert calls == [user_id]
    assert dlg.authenticated_user is None
    assert dlg.result() != QtWidgets.QDialog.Accepted


@pytest.mark.gui
def test_login_continues_after_forced_password_change(qtbot, stax_db, monkeypatch):
    user_id = stax_db.create_user("forced_user_ok", "secret123", role="user")
    with stax_db.get_connection() as conn:
        conn.execute(
            "UPDATE users SET must_change_password = 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()

    dlg = LoginDialog(stax_db)
    qtbot.addWidget(dlg)
    dlg.username_edit.setText("forced_user_ok")
    dlg.password_edit.setText("secret123")

    calls = []
    monkeypatch.setattr(
        dlg,
        "_force_password_change",
        lambda user: calls.append(user["user_id"]) or True,
        raising=False,
    )

    dlg.attempt_login()

    assert calls == [user_id]
    assert dlg.authenticated_user is not None
    assert dlg.authenticated_user["user_id"] == user_id
    assert dlg.result() == QtWidgets.QDialog.Accepted
