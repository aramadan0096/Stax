import numpy as np
import pytest
from ai.embedder import FakeEmbedder
from ai.ai_search import AiSearchService


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("fire", "water", "city"):
            conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,?, '2D', ?)",
                         (name, name))


def _index(stax_db, emb):
    # embed each element by its NAME so text queries have a known nearest match
    for eid, name in ((1, "fire"), (2, "water"), (3, "city")):
        stax_db.store_element_embedding(eid, emb.id, emb.embed_text(name))


@pytest.mark.unit
def test_semantic_search_ranks_exact_match_first(stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    _index(stax_db, emb)
    svc = AiSearchService(stax_db, emb)
    res = svc.semantic_search("fire", top_k=3)
    assert res[0]["name"] == "fire"
    assert "score" in res[0]


@pytest.mark.unit
def test_similar_to_excludes_self(stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    _index(stax_db, emb)
    svc = AiSearchService(stax_db, emb)
    res = svc.similar_to(1, top_k=3)
    assert all(r["element_id"] != 1 for r in res)


@pytest.mark.unit
def test_all_ai_methods_empty_without_embedder(stax_db):
    _seed(stax_db)
    svc = AiSearchService(stax_db, None)
    assert svc.semantic_search("fire") == []
    assert svc.visual_search("/x.png") == []
    assert svc.similar_to(1) == []
    assert svc.suggest_tags(1) == []


@pytest.mark.unit
def test_suggest_tags_picks_matching_vocab(stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    # element 1's image embedding equals the text vector for "fire"
    stax_db.store_element_embedding(1, emb.id, emb.embed_text("fire"))
    svc = AiSearchService(stax_db, emb)
    tags = svc.suggest_tags(1, vocabulary=["fire", "water", "city"], top_k=1, min_score=-1.0)
    assert tags[0][0] == "fire"
