import pytest


class _FakeMain(object):
    def __init__(self, admin):
        self._admin = admin
        self.is_admin = admin
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        return self._admin


@pytest.mark.gui
def test_search_tab_lists_synonyms_and_gates_admin(qtbot, stax_config, stax_db):
    stax_db.add_synonym("fire", "g1")
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=False))
    qtbot.addWidget(panel)
    assert panel.synonyms_table.rowCount() == 1
    assert panel.add_synonym_button.isEnabled() is False
    assert panel.delete_synonym_button.isEnabled() is False
    assert panel.delete_collection_button.isEnabled() is False


@pytest.mark.gui
def test_admin_add_synonym(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=True))
    qtbot.addWidget(panel)
    panel._add_synonym_row("flame", "g1")
    assert any(s["term"] == "flame" for s in stax_db.get_synonyms())
    assert panel.synonyms_table.rowCount() == 1


@pytest.mark.gui
def test_search_tab_lists_smart_collections(qtbot, stax_config, stax_db):
    stax_db.create_smart_collection("Recent Fire", {"tags_any": ["fire"]})
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=False))
    qtbot.addWidget(panel)
    assert panel.collections_table.rowCount() == 1


@pytest.mark.gui
def test_admin_delete_synonym(qtbot, stax_config, stax_db):
    stax_db.add_synonym("fire", "g1")
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=True))
    qtbot.addWidget(panel)
    panel.synonyms_table.selectRow(0)
    panel._on_delete_synonym()
    assert stax_db.get_synonyms() == []
    assert panel.synonyms_table.rowCount() == 0


@pytest.mark.gui
def test_admin_delete_collection(qtbot, stax_config, stax_db):
    stax_db.create_smart_collection("Recent Fire", {"tags_any": ["fire"]})
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain(admin=True))
    qtbot.addWidget(panel)
    panel.collections_table.selectRow(0)
    panel._on_delete_collection()
    assert stax_db.get_smart_collections() == []
    assert panel.collections_table.rowCount() == 0


class _PromptingFakeMain(object):
    """Fake main window whose check_admin_permission would prompt (login/denied
    dialogs) if called — as the real MainWindow's does. Regression guard for the
    bug where a tab builder called check_admin_permission() during construction
    and could hang the suite on a modal dialog."""

    def __init__(self, admin):
        self.is_admin = admin
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        raise AssertionError(
            "check_admin_permission() must not be called during tab construction "
            "(it prompts interactively); use the is_admin flag for state queries"
        )


@pytest.mark.gui
def test_building_search_tab_does_not_call_check_admin_permission(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_PromptingFakeMain(admin=False))
    qtbot.addWidget(panel)
    assert panel.synonyms_table.rowCount() == 0
    assert panel.add_synonym_button.isEnabled() is False
