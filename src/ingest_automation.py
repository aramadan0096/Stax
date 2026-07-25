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


def profile_to_config_overlay(profile):
    """Map a proxy/transcode profile row to the SP2 PreviewWorker config keys.

    Only keys PreviewWorker._process already reads are produced — no new
    ffmpeg knobs are invented. `kind == 'mp4'` enables video previews.
    """
    overlay = {}
    max_size = profile.get("max_size")
    if max_size:
        overlay["preview_size"] = int(max_size)
        overlay["gif_size"] = int(max_size)
    fps = profile.get("fps")
    if fps:
        overlay["sequence_preview_fps"] = int(fps)
        overlay["gif_fps"] = int(fps)
    if profile.get("duration") is not None:
        overlay["gif_duration"] = profile["duration"]
    overlay["generate_video_previews"] = (profile.get("kind") == "mp4")
    return overlay


# ---------------------------------------------------------------------------
# Whitelisted action-chain executor (F040). NEVER exec()/eval() — see C2.
# ---------------------------------------------------------------------------

def _action_add_tag(context, params):
    db, eid = context.get("db"), context.get("element_id")
    tag = params.get("tag")
    if db and eid and tag and hasattr(db, "add_tag_to_element"):
        db.add_tag_to_element(eid, tag)
    return "added tag {!r}".format(tag)


def _action_set_field(context, params):
    # EP4 seam: writes a custom metadata field when EP4's API is present.
    db, eid = context.get("db"), context.get("element_id")
    key, value = params.get("field_key"), params.get("value")
    if db and eid and key and hasattr(db, "set_element_metadata"):
        db.set_element_metadata(eid, key, value)
        return "set {}={!r}".format(key, value)
    return "set_field skipped (EP4 not available)"


def _action_move_to_list(context, params):
    db, eid = context.get("db"), context.get("element_id")
    list_id = params.get("list_id")
    if db and eid and list_id and hasattr(db, "move_element"):
        db.move_element(eid, list_id)
    return "moved to list {}".format(list_id)


def _action_generate_proxy(context, params):
    # Records intent; actual transcode runs via the PreviewWorker overlay.
    return "queued proxy profile {}".format(params.get("profile_id"))


def _action_notify(context, params):
    db = context.get("db")
    if db and hasattr(db, "add_notification"):
        db.add_notification(params.get("title", "Action chain"),
                            params.get("body"), level=params.get("level", "info"))
    return "notified"


BUILTIN_ACTIONS = {
    "add_tag": _action_add_tag,
    "set_field": _action_set_field,
    "move_to_list": _action_move_to_list,
    "generate_proxy": _action_generate_proxy,
    "notify": _action_notify,
}


def run_action_chain(steps, context, handlers=None):
    """Run an ordered list of {action, params} steps against a whitelist.

    Only actions present in `handlers` (default BUILTIN_ACTIONS) execute;
    unknown actions are reported as failed and NEVER evaluated. Returns a list
    of {action, ok, message}.
    """
    handlers = BUILTIN_ACTIONS if handlers is None else handlers
    results = []
    for step in (steps or []):
        action = step.get("action")
        params = step.get("params") or {}
        fn = handlers.get(action)
        if fn is None:
            results.append({"action": action, "ok": False, "message": "unknown action"})
            continue
        try:
            msg = fn(context, params)
            results.append({"action": action, "ok": True, "message": msg or ""})
        except Exception as exc:              # noqa: BLE001
            log.exception("action %r failed", action)
            results.append({"action": action, "ok": False, "message": str(exc)})
    return results
