# -*- coding: utf-8 -*-
"""EP7 Task 7: semantic-search toggle + "Find similar" action.

Constructed with the real MediaDisplayWidget signature
(db_manager, config, nuke_bridge) -- the plan's `MediaDisplayWidget(stax_db)`
is stale; see the task-6 report for the reconciliation (also followed here
per the task-7 brief).
"""
import pytest

from ai.embedder import FakeEmbedder
from ai.ai_search import AiSearchService
from nuke_bridge import NukeBridge


def _seed_indexed(stax_db, emb):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("fire", "water", "city"):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')", (name,))
    for eid, name in ((1, "fire"), (2, "water"), (3, "city")):
        stax_db.store_element_embedding(eid, emb.id, emb.embed_text(name))


@pytest.mark.gui
def test_semantic_search_returns_best_match_first(qtbot, stax_db, stax_config):
    emb = FakeEmbedder()
    _seed_indexed(stax_db, emb)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    w.ai_service = AiSearchService(stax_db, emb)
    qtbot.addWidget(w)
    rows = w.run_semantic_search("fire")
    assert rows[0]["name"] == "fire"


@pytest.mark.gui
def test_ai_disabled_when_no_embedder(qtbot, stax_db, stax_config):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    w.ai_service = AiSearchService(stax_db, None)
    qtbot.addWidget(w)
    assert w.ai_enabled() is False
    assert w.run_semantic_search("fire") == []
    assert w.run_similar_search(1) == []
