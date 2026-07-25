# -*- coding: utf-8 -*-
"""EP7 wiring: the Settings 'Reindex library' button no-ops because main.py
never gives the Settings panel a handle to the running AiIndexWorker. main.py
builds the worker (self.ai_index_worker) before the panel but never assigns
self.settings_panel.ai_index_worker, so _on_reindex_library() always sees None.
"""

import types
import pytest


@pytest.mark.gui
def test_attach_ai_worker_gives_settings_panel_the_worker():
    from main import MainWindow
    panel = types.SimpleNamespace()
    worker = object()
    fake = types.SimpleNamespace(settings_panel=panel, ai_index_worker=worker)

    MainWindow._attach_ai_worker_to_settings(fake)

    assert panel.ai_index_worker is worker


@pytest.mark.gui
def test_attach_ai_worker_tolerates_no_worker():
    from main import MainWindow
    panel = types.SimpleNamespace()
    fake = types.SimpleNamespace(settings_panel=panel)   # ai_index_worker absent

    MainWindow._attach_ai_worker_to_settings(fake)

    assert getattr(panel, "ai_index_worker", "unset") is None


@pytest.mark.gui
def test_reindex_enqueues_missing_when_worker_wired(qtbot, stax_db, stax_config, tmp_path, monkeypatch):
    """Downstream check: once the panel HAS a worker, Reindex enqueues the
    missing-embedding ids onto it. (Green pre-fix — proves wiring the worker is
    sufficient, so the helper above closes the whole loop.)"""
    from ui.settings_panel import SettingsPanel
    import ai.embedder as embmod

    stax_config.set("ai_model_dir", str(tmp_path))

    class _Main(object):
        is_admin = True
        current_user = None

        def check_admin_permission(self, action_name="this action"):
            return True

    panel = SettingsPanel(config=stax_config, db_manager=stax_db, main_window=_Main())
    qtbot.addWidget(panel)

    monkeypatch.setattr(embmod, "get_embedder",
                        lambda cfg=None: types.SimpleNamespace(id="fake-model"))
    monkeypatch.setattr(stax_db, "get_elements_missing_embedding", lambda model_id: [1, 2])
    enqueued = []
    panel.ai_index_worker = types.SimpleNamespace(enqueue_many=lambda ids: enqueued.extend(ids))

    panel._on_reindex_library()

    assert enqueued == [1, 2]
