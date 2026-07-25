# -*- coding: utf-8 -*-
"""Dominant-color signatures for color-palette search (EP7, F004).

Dependency-light: Pillow + numpy only. No AI model involved, so color search
works even when the embedder is unavailable.
"""

import colorsys
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

HIST_BINS = 12


def _rgb_pixels_to_hist(arr):
    """arr: float32 [N,3] in 0..1 -> saturation*value weighted 12-bin hue hist."""
    hist = np.zeros(HIST_BINS, dtype=np.float32)
    for r, g, b in arr:
        h, s, v = colorsys.rgb_to_hsv(float(r), float(g), float(b))
        bin_idx = min(HIST_BINS - 1, int(h * HIST_BINS))
        hist[bin_idx] += s * v
    total = float(hist.sum())
    if total > 0:
        hist /= total
    return hist.astype(np.float32)


def rgb_to_histogram(rgb):
    """A single RGB (0..255) as a normalized hue histogram (for queries)."""
    arr = np.asarray([rgb], dtype=np.float32) / 255.0
    return _rgb_pixels_to_hist(arr)


def _dominant_colors(arr, k=5):
    """Coarse dominant colors: bucket to a 4x4x4 RGB grid, return top-k by weight."""
    buckets = {}
    for r, g, b in arr:
        key = (int(r * 3.999), int(g * 3.999), int(b * 3.999))
        buckets[key] = buckets.get(key, 0) + 1
    total = float(len(arr)) or 1.0
    top = sorted(buckets.items(), key=lambda kv: -kv[1])[:k]
    out = []
    for (br, bg, bb), count in top:
        out.append([int((br + 0.5) / 4 * 255), int((bg + 0.5) / 4 * 255),
                    int((bb + 0.5) / 4 * 255), round(count / total, 4)])
    return out


def compute_color_signature(image_path, sample=64):
    if not image_path or not os.path.isfile(image_path):
        return None
    try:
        from PIL import Image
        img = Image.open(image_path).convert("RGB").resize((sample, sample))
        arr = (np.asarray(img, dtype=np.float32) / 255.0).reshape(-1, 3)
    except Exception as exc:
        logger.debug("color signature failed for %s: %s", image_path, exc)
        return None
    return {"histogram": _rgb_pixels_to_hist(arr), "dominant": _dominant_colors(arr)}


def color_search(db, rgb, top_k=50):
    """Rank stored elements by L1 hue-histogram distance to the query color."""
    query = rgb_to_histogram(rgb)
    ids, matrix = db.get_all_colors()
    if not ids:
        return []
    dists = np.abs(matrix - query).sum(axis=1)
    order = np.argsort(dists)[:top_k]
    return [(ids[int(i)], float(1.0 - dists[int(i)] / 2.0)) for i in order]
