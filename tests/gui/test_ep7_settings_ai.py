# -*- coding: utf-8 -*-
"""EP7 Task 10 — Settings AI tab (status/download/reindex)."""

import pytest


class _Main(object):
    """Fake main window matching the interface SettingsPanel.setup_ui
    unconditionally touches while building other tabs (is_admin for
    security-tab gating, current_user for the bottom button bar), same
    pattern as tests/gui/test_ep6_automation_settings.py's _Main.
    """

    def __init__(self):
        self.is_admin = True
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        return True


@pytest.mark.gui
def test_ai_tab_reports_unavailable_when_no_model(qtbot, stax_db, stax_config, tmp_path):
    from ui.settings_panel import SettingsPanel

    # stax_config is a real Config (has DEFAULT_CONFIG for every other tab's
    # self.config.get(key) calls with no fallback) -- a bare
    # {"ai_model_dir": ...} dict, as sketched in the task brief, blows up
    # setup_ingestion_tab()'s self.config.get('auto_detect_sequences') (no
    # default -> None -> QCheckBox.setChecked(None) TypeError) before the AI
    # tab is even reached. get_embedder() accepts either a dict or a
    # Config-like object (config.get(...) / getattr fallback), so routing the
    # AI model dir through Config.set keeps that contract intact while
    # letting the rest of SettingsPanel construct normally.
    stax_config.set("ai_model_dir", str(tmp_path))
    panel = SettingsPanel(config=stax_config, db_manager=stax_db,
                           main_window=_Main())
    qtbot.addWidget(panel)
    assert "not installed" in panel.ai_status_label.text().lower()
    # reindex is safe to click even with no model (color-only) but should not raise
    panel._on_reindex_library()
