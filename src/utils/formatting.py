# -*- coding: utf-8 -*-
"""Shared human-readable formatting helpers."""


def human_size(num_bytes):
    """Format a byte count as a human-readable string (B / KB / MB / GB / TB)."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    if size < 0:
        size = 0.0
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            if unit == "B":
                return "{:.0f} {}".format(size, unit)
            return "{:.1f} {}".format(size, unit)
        size /= 1024.0
    return "{:.1f} TB".format(size)
