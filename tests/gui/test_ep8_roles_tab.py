import pytest


class _Main:
    def __init__(self, admin, user="admin"):
        self._a = admin
        self.current_user = {"username": user, "role": "admin" if admin else "user"}
        self.is_admin = admin
    def check_admin_permission(self, *a, **k):
        return self._a


@pytest.mark.gui
def test_roles_tab_lists_roles_and_gates_admin(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(admin=False))
    qtbot.addWidget(panel)
    assert panel.roles_table.rowCount() >= 5      # built-in roles
    assert panel.add_role_button.isEnabled() is False


@pytest.mark.gui
def test_admin_toggles_permission_persists(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    panel._toggle_role_permission("reviewer", "can_delete", True)
    assert "can_delete" in stax_db.get_role_permissions("reviewer")
