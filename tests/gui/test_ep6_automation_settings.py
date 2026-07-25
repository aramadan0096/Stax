import pytest


class _Main(object):
    """Fake main window exposing the non-interactive `is_admin` flag that
    _build_ingest_automation_tab must use for state gating (enable/disable
    buttons at construction time), mirroring the pattern used by
    _build_fields_tab / _build_labels_tab / _build_search_tab. `current_user`
    is included because SettingsPanel.setup_ui reads it unconditionally when
    building the bottom button bar.
    """

    def __init__(self, a):
        self.is_admin = a
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        return self.is_admin


@pytest.mark.gui
def test_automation_tab_lists_and_gates_admin(qtbot, stax_config, stax_db):
    stax_db.create_watch_folder("/inbox", target_list_id=1)
    stax_db.create_ingest_recipe("Plates", {"copy_policy": "hard"})
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(False))
    qtbot.addWidget(panel)
    assert panel.watch_table.rowCount() == 1
    assert panel.recipes_table.rowCount() == 1
    # seeded proxy presets show up
    assert panel.profiles_table.rowCount() >= 3
    assert panel.add_watch_button.isEnabled() is False


@pytest.mark.gui
def test_admin_can_delete_watch(qtbot, stax_config, stax_db):
    stax_db.create_watch_folder("/inbox")
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(True))
    qtbot.addWidget(panel)
    panel.watch_table.selectRow(0)
    panel._on_delete_watch()
    assert stax_db.get_watch_folders() == []
