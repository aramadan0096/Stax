# -*- coding: utf-8 -*-
"""Real local CLIP inference (EP7) over the bundled weights.

Exercises the whole offline pipeline end to end: clip_tokenizer.ClipTokenizer ->
clip_text.onnx and the image preprocessing -> clip_image.onnx, via
ai.embedder.get_embedder(). Skips automatically when the weights or onnxruntime
are absent (so environments without the model still pass), and runs for real
when weights/clip-vit-b32-onnx is present.
"""

import os

import numpy as np
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def embedder():
    from ai.embedder import get_embedder
    emb = get_embedder()
    if emb is None or not emb.is_available():
        pytest.skip("CLIP weights/onnxruntime not available")
    return emb


def test_clip_tokenizer_shapes_and_specials():
    from ai.embedder import default_model_dir
    from clip_tokenizer import ClipTokenizer
    model_dir = default_model_dir()
    if not os.path.isfile(os.path.join(model_dir, "bpe_simple_vocab_16e6.txt.gz")):
        pytest.skip("BPE vocab not available")
    tok = ClipTokenizer(model_dir, context_length=77)
    arr = tok.encode("a photo of a dog")
    assert arr.shape == (1, 77)
    assert arr.dtype == np.int32
    assert arr[0, 0] == tok.sot            # starts with start-of-text
    assert tok.eot in arr[0].tolist()      # end-of-text present


def test_embed_text_is_unit_512(embedder):
    v = embedder.embed_text("a photo of a dog")
    assert v.shape == (512,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-3


def test_embed_image_is_unit_512(embedder):
    img = os.path.join(_REPO, "resources", "logo.png")
    v = embedder.embed_image(img)
    assert v.shape == (512,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-3


def test_text_semantics_rank_sensibly(embedder):
    dog = embedder.embed_text("a photo of a dog")
    puppy = embedder.embed_text("a photo of a puppy")
    airplane = embedder.embed_text("a photo of an airplane")
    assert float(np.dot(dog, puppy)) > float(np.dot(dog, airplane))
