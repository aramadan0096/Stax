# -*- coding: utf-8 -*-
"""Shared element metadata formatting (EP3; reduces audit L10 duplication).

Pure formatting/derivation logic for element metadata display — no Qt, no DB.
Consumed by ``InspectorPanel`` (EP3 Task 6) and ``media_info_popup.py`` (the
Alt+hover popup), so there is exactly one implementation of this formatting.
"""

from src.utils.formatting import human_size

# Re-exported for convenience/back-compat: callers can import human_size from
# either src.utils.formatting (the canonical definition, SP8) or here.
__all__ = [
    "human_size",
    "element_field_rows",
    "VIDEO_EXTS",
    "SEQUENCE_EXTS",
    "detect_playback_mode",
]

# Element type (elements.type: '2D' / '3D' / 'Toolset') is a real DB column
# and is distinct from playback mode below. Playback mode (video vs. image
# sequence) is derived from the file format extension (+ frame range for
# sequences), not from element type. See SP6 "M7" fix.
VIDEO_EXTS = ('.mov', '.mp4', '.avi', '.mxf')
SEQUENCE_EXTS = ('.exr', '.dpx', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.tga', '.bmp')


def detect_playback_mode(fmt, frame_range):
    """Determine (is_video, is_sequence) from a format extension + frame range.

    Behavior-preserving extraction of the logic that previously lived inline
    in ``MediaInfoPopup.show_element``:
      - ``fmt`` is lower-cased and given a leading dot if missing.
      - A video extension makes ``is_video`` True.
      - A sequence extension makes ``is_sequence`` True only when a truthy
        ``frame_range`` is also present (a lone still is not a sequence).

    Args:
        fmt (str): File format/extension, with or without a leading dot
            (e.g. ".exr", "exr", or falsy).
        frame_range: Frame range value (e.g. "1-10"); falsy means no range.

    Returns:
        tuple[bool, bool]: (is_video, is_sequence)
    """
    fmt = (fmt or '').lower()
    if fmt and not fmt.startswith('.'):
        fmt = '.' + fmt
    is_video = fmt in VIDEO_EXTS
    is_sequence = bool(frame_range) and fmt in SEQUENCE_EXTS
    return is_video, is_sequence


def element_field_rows(element):
    """Return the read-only display rows (label, value) for an element dict."""
    return [
        ("Name", element.get("name", "")),
        ("Type", element.get("type", "")),
        ("Format", element.get("format", "") or ""),
        ("Frames", element.get("frame_range", "") or ""),
        ("Size", human_size(element.get("file_size", 0))),
    ]
