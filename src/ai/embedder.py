# -*- coding: utf-8 -*-
"""Local-only embedding abstraction for AI discovery (EP7).

No cloud/API provider is ever used. The real implementation runs a
downloaded CLIP ViT-B/32 model through onnxruntime on CPU. When the model or
runtime is unavailable, get_embedder() returns None and every AI code path
degrades gracefully.
"""

import hashlib
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

EMBED_DIM = 512


def _l2_normalize(vec):
    vec = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return (vec / norm).astype(np.float32)


def default_model_dir():
    """Where downloaded CLIP-ONNX files live (see tools/download_clip_model.py)."""
    base = os.environ.get("STAX_AI_MODEL_DIR")
    if base:
        return base
    return os.path.join(os.path.expanduser("~"), ".stax", "models", "clip-vit-b32-onnx")


class Embedder(object):
    """Abstract local embedder mapping text/images to unit vectors."""

    id = "abstract"
    dim = EMBED_DIM

    def is_available(self):
        raise NotImplementedError

    def embed_text(self, text):
        raise NotImplementedError

    def embed_image(self, image_path):
        raise NotImplementedError


class FakeEmbedder(Embedder):
    """Deterministic, dependency-free embedder for tests.

    Vectors are seeded from a hash of the input, so identical inputs always
    map to identical vectors and cosine relationships are stable across runs.
    """

    id = "fake-v1"

    def __init__(self, dim=EMBED_DIM):
        self.dim = dim

    def is_available(self):
        return True

    def _vec(self, key):
        seed = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        return _l2_normalize(rng.rand(self.dim))

    def embed_text(self, text):
        return self._vec("t:" + (text or ""))

    def embed_image(self, image_path):
        return self._vec("i:" + str(image_path))


class ClipOnnxEmbedder(Embedder):
    """Real local CLIP ViT-B/32 embedder via onnxruntime (CPU).

    Model + tokenizer are fetched once by tools/download_clip_model.py into
    model_dir. Heavy imports are deferred and guarded (mirrors
    duplicate_detection.compute_phash) so a missing runtime never breaks import.
    Real inference is exercised only by @pytest.mark.manual tests.
    """

    id = "clip-vit-b32-onnx"

    def __init__(self, model_dir=None):
        self.model_dir = model_dir or default_model_dir()
        self._image_session = None
        self._text_session = None
        self._tokenizer = None

    def _image_path(self):
        return os.path.join(self.model_dir, "clip_image.onnx")

    def _text_path(self):
        return os.path.join(self.model_dir, "clip_text.onnx")

    def is_available(self):
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return False
        return os.path.isfile(self._image_path()) and os.path.isfile(self._text_path())

    # --- real inference (deferred; covered by manual tests) -----------------
    def _ensure_loaded(self):
        if self._image_session is None:
            import onnxruntime
            from clip_tokenizer import ClipTokenizer  # vendored BPE tokenizer
            self._image_session = onnxruntime.InferenceSession(
                self._image_path(), providers=["CPUExecutionProvider"])
            self._text_session = onnxruntime.InferenceSession(
                self._text_path(), providers=["CPUExecutionProvider"])
            self._tokenizer = ClipTokenizer(self.model_dir)

    def embed_text(self, text):
        self._ensure_loaded()
        tokens = self._tokenizer.encode(text or "")            # (1, 77) int64
        inp = self._text_session.get_inputs()[0].name
        out = self._text_session.run(None, {inp: tokens})[0][0]
        return _l2_normalize(out)

    def embed_image(self, image_path):
        self._ensure_loaded()
        from PIL import Image
        img = Image.open(image_path).convert("RGB").resize((224, 224))
        arr = np.asarray(img, dtype=np.float32) / 255.0
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        arr = (arr - mean) / std
        chw = np.transpose(arr, (2, 0, 1))[None, :, :, :].astype(np.float32)
        inp = self._image_session.get_inputs()[0].name
        out = self._image_session.run(None, {inp: chw})[0][0]
        return _l2_normalize(out)


def get_embedder(config=None):
    """Return an available local Embedder, or None (AI disabled). Never raises."""
    try:
        model_dir = None
        if config is not None:
            try:
                model_dir = config.get("ai_model_dir")
            except AttributeError:
                model_dir = getattr(config, "ai_model_dir", None)
        emb = ClipOnnxEmbedder(model_dir or default_model_dir())
        if emb.is_available():
            return emb
        logger.info("AI embedder unavailable (model/runtime missing) — AI features disabled.")
        return None
    except Exception:
        logger.exception("Failed to construct embedder")
        return None
