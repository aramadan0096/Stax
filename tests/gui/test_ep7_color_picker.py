# -*- coding: utf-8 -*-
"""EP7 Task 8: color-palette picker + search (F004, non-AI).

Constructed with the real MediaDisplayWidget signature
(db_manager, config, nuke_bridge) -- the plan's `MediaDisplayWidget(stax_db)`
is stale; see the task-6/task-7 reports for the reconciliation. Color search
is pure PIL/numpy (ai/color_index.py) and must work with ai_service = None.
"""
import pytest
from ai.color_index import rgb_to_histogram
from nuke_bridge import NukeBridge


def _seed_colored(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'red','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'blue','2D')")
    stax_db.store_element_color(1, rgb_to_histogram((255, 0, 0)), None)
    stax_db.store_element_color(2, rgb_to_histogram((0, 0, 255)), None)


@pytest.mark.gui
def test_color_search_works_without_embedder(qtbot, stax_db, stax_config):
    _seed_colored(stax_db)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    w.ai_service = None   # color search must not need AI
    qtbot.addWidget(w)
    rows = w.run_color_search((250, 10, 10))
    assert rows[0]["element_id"] == 1
