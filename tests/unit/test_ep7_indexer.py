import numpy as np
import pytest
from PIL import Image
from ai.embedder import FakeEmbedder
from ai.indexer import index_element


def _seed_with_preview(stax_db, tmp_path):
    p = tmp_path / "prev.png"
    Image.new("RGB", (16, 16), (255, 0, 0)).save(str(p))
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,preview_path) VALUES (1,'a','2D',?)",
                     (str(p),))


@pytest.mark.unit
def test_index_writes_color_without_embedder(stax_db, tmp_path):
    _seed_with_preview(stax_db, tmp_path)
    res = index_element(stax_db, 1, embedder=None)
    assert res["colored"] is True
    assert res["embedded"] is False
    ids, matrix = stax_db.get_all_colors()
    assert ids == [1]


@pytest.mark.unit
def test_index_writes_both_with_embedder(stax_db, tmp_path):
    _seed_with_preview(stax_db, tmp_path)
    res = index_element(stax_db, 1, embedder=FakeEmbedder())
    assert res["colored"] is True and res["embedded"] is True
    assert stax_db.get_element_embedding(1) is not None


@pytest.mark.unit
def test_index_never_raises_on_bad_element(stax_db):
    res = index_element(stax_db, 9999, embedder=FakeEmbedder())
    assert res["embedded"] is False and res["colored"] is False
