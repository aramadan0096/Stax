import pytest


class _FakeMain(object):
    def __init__(self, admin):
        self._admin = admin
        self.is_admin = admin
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        return self._admin


@pytest.mark.gui
def test_labels_tab_lists_palette_and_gates_admin(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=False))
    qtbot.addWidget(panel)
    assert panel.labels_table.rowCount() == 7
    assert panel.add_label_button.isEnabled() is False


@pytest.mark.gui
def test_admin_can_add_label(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=True))
    qtbot.addWidget(panel)
    panel._create_label_row("Teal", "#12A594", "custom")
    assert any(l["name"] == "Teal" for l in stax_db.get_labels())


class _PromptingFakeMain(object):
    """Fake main window whose check_admin_permission would prompt (login/denied
    dialogs) if called — as the real MainWindow's does. Used to pin the
    regression where _build_labels_tab called check_admin_permission() during
    construction and could hang on a modal dialog."""

    def __init__(self, admin):
        self.is_admin = admin
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        raise AssertionError(
            "check_admin_permission() must not be called during tab construction "
            "(it prompts interactively); use the is_admin flag for state queries"
        )


@pytest.mark.gui
def test_building_labels_tab_does_not_call_check_admin_permission(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_PromptingFakeMain(admin=False))
    qtbot.addWidget(panel)
    assert panel.labels_table.rowCount() == 7
    assert panel.add_label_button.isEnabled() is False
