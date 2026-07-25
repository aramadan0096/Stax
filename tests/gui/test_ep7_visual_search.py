# -*- coding: utf-8 -*-
"""EP7 Task 6: ImageDropZone widget + AI visual-search result surface.

Constructed with the real MediaDisplayWidget signature
(db_manager, config, nuke_bridge) -- the plan's `MediaDisplayWidget(stax_db)`
is stale; see the task-6 report for the reconciliation.
"""
import pytest
from PIL import Image

from ai.embedder import FakeEmbedder
from ai.ai_search import AiSearchService
from nuke_bridge import NukeBridge


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'fire','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'water','2D')")


@pytest.mark.gui
def test_drop_zone_emits_path(qtbot, tmp_path):
    from ui.image_drop_zone import ImageDropZone
    p = tmp_path / "ref.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(str(p))
    zone = ImageDropZone()
    qtbot.addWidget(zone)
    with qtbot.waitSignal(zone.image_dropped, timeout=1000):
        zone.accept_path(str(p))


@pytest.mark.gui
def test_run_visual_search_renders_results(qtbot, stax_db, stax_config):
    _seed(stax_db)
    emb = FakeEmbedder()
    # index element 1 so its image-embedding is the query's nearest neighbour
    ref = "/ref/frame.png"
    stax_db.store_element_embedding(1, emb.id, emb.embed_image(ref))
    stax_db.store_element_embedding(2, emb.id, emb.embed_text("water"))
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    w.ai_service = AiSearchService(stax_db, emb)
    qtbot.addWidget(w)
    rows = w.run_visual_search(ref)
    assert rows[0]["element_id"] == 1
