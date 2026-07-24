# -*- coding: utf-8 -*-
"""Serializable filter model shared by the drawer, chips, saved searches,
and smart collections (EP2)."""

FILTER_VERSION = 1

_LIST_KEYS = ("types", "formats", "tags_all", "tags_any",
              "tags_exclude", "formats_exclude", "label_fks")
_FLAG_KEYS = ("is_deprecated", "is_hard_copy")
_INT_KEYS = ("rating_min", "list_fk", "stack_fk")


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
        val = spec.get(k) or []
        out[k] = list(val)
    for k in _FLAG_KEYS:
        out[k] = spec.get(k, None)
    for k in _INT_KEYS:
        v = spec.get(k, None)
        if k == "rating_min":
            out[k] = int(v) if v else 0
        else:
            out[k] = int(v) if v else None
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
