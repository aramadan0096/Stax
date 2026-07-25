# -*- coding: utf-8 -*-
"""Pure, Qt-free ingest-automation helpers (EP6).

Kept free of Qt/DB imports so watch-folder diffing, recipe overlays, duplicate
policy resolution, preflight validation, proxy-profile mapping, and action-chain
dispatch are unit-testable in isolation (mirrors EP4's metadata_rules.py).
"""

import os
import logging

log = logging.getLogger(__name__)

MEDIA_EXTS = frozenset({
    ".exr", ".dpx", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".tga",
    ".mov", ".mp4", ".mxf", ".avi", ".mkv", ".abc", ".obj", ".fbx", ".glb",
})

DUP_POLICIES = ("allow", "skip", "version", "ask")


def scan_folder(path, seen, exts=None):
    """Non-recursive poll of `path`. Return (new_paths, updated_seen).

    A file is 'new' if its extension is in `exts` (default MEDIA_EXTS) and its
    absolute path is not already in `seen`. `seen` is not mutated; a fresh set
    is returned so callers persist it between polls.
    """
    exts = set(e.lower() for e in (exts or MEDIA_EXTS))
    updated = set(seen)
    new_paths = []
    try:
        entries = list(os.scandir(path))
    except (OSError, ValueError) as exc:
        log.debug("scan_folder: cannot scan %r: %s", path, exc)
        return [], updated
    for entry in sorted(entries, key=lambda e: e.name):
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in exts:
            continue
        full = os.path.abspath(entry.path)
        if full in updated:
            continue
        updated.add(full)
        new_paths.append(full)
    return new_paths, updated


def apply_recipe_to_config(recipe_values, base_config):
    """Return a NEW dict = base_config overlaid with the recipe's values."""
    merged = dict(base_config or {})
    for k, v in (recipe_values or {}).items():
        merged[k] = v
    return merged


def resolve_duplicate_action(policy, duplicates):
    """Return 'allow'|'skip'|'version'|'ask'. No duplicates => 'allow';
    unknown policy => 'allow'."""
    if not duplicates:
        return "allow"
    if policy not in DUP_POLICIES:
        return "allow"
    return policy


def run_preflight(paths, known_exts=None, duplicate_paths=None):
    """Validate `paths` before ingest. Return a list of issue dicts:
    {level: 'error'|'warning', code, path, message}."""
    known_exts = set(e.lower() for e in (known_exts or MEDIA_EXTS))
    duplicate_paths = set(duplicate_paths or ())
    issues = []
    for p in paths:
        if not os.path.exists(p):
            issues.append({"level": "error", "code": "missing", "path": p,
                           "message": "File does not exist"})
            continue
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        if size == 0:
            issues.append({"level": "error", "code": "empty", "path": p,
                           "message": "File is empty (0 bytes)"})
        if os.path.splitext(p)[1].lower() not in known_exts:
            issues.append({"level": "warning", "code": "unknown_ext", "path": p,
                           "message": "Unrecognized media extension"})
        if p in duplicate_paths:
            issues.append({"level": "warning", "code": "duplicate", "path": p,
                           "message": "Possible duplicate of an existing asset"})
    return issues
