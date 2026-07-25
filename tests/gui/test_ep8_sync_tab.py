import pytest


class _Main:
    def __init__(self, admin):
        self._a = admin
        self.current_user = {"username": "admin", "role": "admin"}
        self.is_admin = admin
    def check_admin_permission(self, *a, **k):
        return self._a


def _seed_list(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'a', '2D')")
        conn.commit()
    return 1


@pytest.mark.gui
def test_sync_tab_lists_connectors(qtbot, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    labels = [panel.connectors_table.item(r, 0).text()
              for r in range(panel.connectors_table.rowCount())]
    assert any("Local Bundle" in t for t in labels)


@pytest.mark.gui
def test_export_helper_writes_bundle_and_audits(qtbot, stax_config, stax_db, tmp_path):
    lid = _seed_list(stax_db)
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    out = str(tmp_path / "x.staxbundle")
    panel._do_export(lid, out)
    import os
    assert os.path.exists(out)
    assert stax_db.get_activity(action="export")
