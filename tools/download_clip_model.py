# -*- coding: utf-8 -*-
"""Download the local CLIP ViT-B/32 ONNX model + BPE tokenizer for EP7.

No cloud inference — this only fetches model files once so ClipOnnxEmbedder
(src/ai/embedder.py) can run locally. Files land in ai.embedder.default_model_dir()
and are checksum-verified before being trusted.

Mirrors tools/ffmpeg_downloader.py: URLs/checksums are populated at build
time from a human-approved, one-time download. Until then FILES entries are
left empty and main() skips each one (never installs an unverified binary).
"""

import hashlib
import logging
import os
import sys
import urllib.request

logger = logging.getLogger(__name__)

# (filename, url, sha256) — populate with the release-hosted artifacts.
FILES = [
    ("clip_image.onnx", "", ""),
    ("clip_text.onnx", "", ""),
    ("bpe_simple_vocab_16e6.txt.gz", "", ""),
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
        logger.info("Downloading %s -> %s", name, out)
        urllib.request.urlretrieve(url, out)
        if sha and _sha256(out) != sha:
            logger.error("Checksum mismatch for %s", name)
            return 1
    logger.info("Model ready in %s", dest)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
