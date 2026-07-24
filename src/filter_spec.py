# -*- coding: utf-8 -*-
"""Serializable filter model shared by the drawer, chips, saved searches,
and smart collections (EP2)."""

FILTER_VERSION = 1

_LIST_KEYS = ("types", "formats", "tags_all", "tags_any",
              "tags_exclude", "formats_exclude", "label_fks")
_FLAG_KEYS = ("is_deprecated", "is_hard_copy")
_INT_KEYS = ("rating_min", "list_fk", "stack_fk")


def _as_list(val):
    """Coerce a stored value into a list without shredding a bare string
    (or bytes) into individual characters."""
    if val is None:
        return []
    if isinstance(val, (str, bytes)):
        return [val]
    return list(val)


def _as_int(val, default):
    """Coerce a stored value into an int, degrading to ``default`` when the
    key is absent/empty or the stored value can't be coerced -- while still
    preserving an explicit falsy value (e.g. ``0``) rather than treating it
    as absent."""
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def empty_filter():
    spec = {"v": FILTER_VERSION, "text": ""}
    for k in _LIST_KEYS:
        spec[k] = []
    for k in _FLAG_KEYS:
        spec[k] = None
    for k in _INT_KEYS:
        spec[k] = 0 if k == "rating_min" else None
    return spec


def normalize(spec):
    """Return a full spec with defaults filled and types coerced."""
    out = empty_filter()
    if not spec:
        return out
    out["text"] = str(spec.get("text") or "")
    for k in _LIST_KEYS:
        out[k] = _as_list(spec.get(k))
    for k in _FLAG_KEYS:
        out[k] = spec.get(k, None)
    for k in _INT_KEYS:
        default = 0 if k == "rating_min" else None
        out[k] = _as_int(spec.get(k, None), default)
    out["v"] = FILTER_VERSION
    return out


def is_active(spec):
    s = normalize(spec)
    if s["text"]:
        return True
    if s["rating_min"]:
        return True
    for k in _LIST_KEYS:
        if s[k]:
            return True
    for k in _FLAG_KEYS:
        if s[k] is not None:
            return True
    if s["list_fk"] or s["stack_fk"]:
        return True
    return False
