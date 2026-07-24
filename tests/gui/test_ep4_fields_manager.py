import pytest


class _Main(object):
    """Fake main window exposing the non-interactive `is_admin` flag that
    _build_fields_tab must use for state gating (enable/disable buttons at
    construction time), mirroring the pattern already used by
    _build_labels_tab / _build_search_tab. `current_user` is included because
    SettingsPanel.setup_ui reads it unconditionally when building the bottom
    button bar.
    """

    def __init__(self, a):
        self.is_admin = a
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        return self.is_admin


@pytest.mark.gui
def test_fields_manager_lists_and_gates(qtbot, stax_config, stax_db):
    stax_db.create_stack("Plates", "/tmp/P")
    stax_db.create_metadata_field(1, "shot", "Shot", "text")
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(False))
    qtbot.addWidget(panel)
    panel.select_fields_stack(1)
    assert panel.fields_table.rowCount() == 1
    assert panel.add_field_button.isEnabled() is False
