import numpy as np
import pytest
from ai.embedder import FakeEmbedder, get_embedder, EMBED_DIM


@pytest.mark.unit
def test_fake_embedder_is_deterministic_and_normalized():
    emb = FakeEmbedder()
    v1 = emb.embed_text("fire explosion")
    v2 = emb.embed_text("fire explosion")
    assert v1.dtype == np.float32
    assert v1.shape == (EMBED_DIM,)
    assert np.allclose(v1, v2)                       # deterministic
    assert abs(float(np.linalg.norm(v1)) - 1.0) < 1e-5   # L2-normalized


@pytest.mark.unit
def test_fake_text_and_image_differ_and_image_is_pathkeyed():
    emb = FakeEmbedder()
    assert not np.allclose(emb.embed_text("x"), emb.embed_image("x"))
    assert np.allclose(emb.embed_image("/a/b.png"), emb.embed_image("/a/b.png"))


@pytest.mark.unit
def test_get_embedder_returns_none_when_unavailable(tmp_path):
    # empty model dir -> ClipOnnxEmbedder.is_available() is False -> None
    assert get_embedder({"ai_model_dir": str(tmp_path)}) is None
