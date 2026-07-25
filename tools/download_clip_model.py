# -*- coding: utf-8 -*-
"""Download the local CLIP ViT-B/32 ONNX model + BPE tokenizer for EP7.

No cloud inference — this only fetches the model files once so ClipOnnxEmbedder
(src/ai/embedder.py) can run locally on CPU. Files land in
ai.embedder.default_model_dir() (the repo-local weights/clip-vit-b32-onnx cache
by default) and are SHA-256 verified before being trusted.

Models: ONNX exports of OpenAI CLIP ViT-B/32 from josephrocca/openai-clip-js
(uint8-quantized: image ~84 MB, text ~61 MB). Text encoder input is (1,77) int32
token ids; image encoder input is (1,3,224,224) float32 — matching
ClipOnnxEmbedder / clip_tokenizer.ClipTokenizer. The BPE vocab is OpenAI CLIP's
bpe_simple_vocab_16e6.txt.gz.

Re-run any time; files already present with a matching checksum are skipped.
"""

import hashlib
import logging
import os
import sys
import urllib.request

# Make src/ importable when run as `python -m tools.download_clip_model` or
# `python tools/download_clip_model.py` (src is on sys.path inside the app via
# init.py / conftest, but not for this standalone tool).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)

_HF = "https://huggingface.co/rocca/openai-clip-js/resolve/main"
_OPENAI = "https://github.com/openai/CLIP/raw/main/clip"

# (filename, url, sha256) — saved under default_model_dir() with these names.
FILES = [
    ("clip_image.onnx",
     _HF + "/clip-image-vit-32-uint8.onnx",
     "7ae4fbd0b82e9f91adb1bfd57a3580f39ffe38cb4e1956e04fd2e23b0f60502c"),
    ("clip_text.onnx",
     _HF + "/clip-text-vit-32-uint8.onnx",
     "c73b51372d637e78b023dc1ecc9f34850e523628206ab3102e7b5a9ea1196eb8"),
    ("bpe_simple_vocab_16e6.txt.gz",
     _OPENAI + "/bpe_simple_vocab_16e6.txt.gz",
     "924691ac288e54409236115652ad4aa250f48203de50a9e4722a6ecd48d6804a"),
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    from ai.embedder import default_model_dir

    dest = default_model_dir()
    os.makedirs(dest, exist_ok=True)
    for name, url, sha in FILES:
        if not url:
            logger.info("No URL configured for %s — skipping.", name)
            continue
        out = os.path.join(dest, name)
        if os.path.isfile(out) and (not sha or _sha256(out) == sha):
            logger.info("%s already present (checksum ok) — skipping.", name)
            continue
        logger.info("Downloading %s -> %s", name, out)
        urllib.request.urlretrieve(url, out)
        if sha and _sha256(out) != sha:
            logger.error("Checksum mismatch for %s (got %s, expected %s)",
                         name, _sha256(out), sha)
            return 1
    logger.info("Model ready in %s", dest)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
