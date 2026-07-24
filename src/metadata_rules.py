# -*- coding: utf-8 -*-
"""Pure (Qt/DB-free) metadata rule logic: coercion, auto-tag, quality, naming (EP4)."""

import fnmatch
import re as _re
import logging as _logging

_log = _logging.getLogger(__name__)

FIELD_TYPES = {"text", "number", "choice", "date", "bool"}


def validate_field_type(field_type, choices):
    if field_type not in FIELD_TYPES:
        raise ValueError("unknown field_type: {!r}".format(field_type))
    if field_type == "choice" and not choices:
        raise ValueError("choice field requires a non-empty choices list")


def coerce_to_text(field_type, value):
    if value is None:
        return ""
    if field_type == "bool":
        return "1" if value in (True, 1, "1", "true", "True") else "0"
    if field_type == "number":
        return str(value)
    return str(value)


def parse_from_text(field_type, text):
    if text is None or text == "":
        if field_type == "bool":
            return False
        return "" if field_type in ("text", "choice", "date") else None
    if field_type == "bool":
        return text in (True, 1, "1", "true", "True")
    if field_type == "number":
        try:
            return float(text)
        except (TypeError, ValueError):
            return None
    return text


def check_element_quality(element, effective_meta, fields, rules):
    """Evaluate quality rules against an element; pure, Qt/DB-free.

    Args:
        element: dict with at least "name".
        effective_meta: dict of field_key -> effective value (inherited/overridden).
        fields: list of metadata field dicts ({"key", "label", ...}).
        rules: list of quality rule dicts ({"rule_id", "kind", "config"}).

    Returns:
        list of {"rule_id", "kind", "message"} dicts, one per violated rule.
    """
    issues = []
    label_by_key = {f["key"]: f.get("label", f["key"]) for f in (fields or [])}
    for rule in rules or []:
        kind = rule.get("kind")
        cfg = rule.get("config") or {}
        if kind == "required_field":
            key = cfg.get("field_key")
            if not (effective_meta or {}).get(key):
                issues.append({"rule_id": rule.get("rule_id"), "kind": kind,
                               "message": "Missing required field: {}".format(label_by_key.get(key, key))})
        elif kind == "naming_regex":
            pat = cfg.get("pattern") or ""
            try:
                if _re.match(pat, element.get("name", "")) is None:
                    issues.append({"rule_id": rule.get("rule_id"), "kind": kind,
                                   "message": "Name doesn't match convention"})
            except _re.error:
                _log.warning("bad naming regex skipped: %r", pat)
    return issues


def evaluate_autotag(source_path, rules):
    """Match rules against a path; union tags and merge fields (by rule order)."""
    path = source_path or ""
    tags, fields = [], {}
    for rule in rules or []:
        mt = rule.get("match_type")
        pat = rule.get("pattern") or ""
        matched = False
        try:
            if mt == "contains":
                matched = pat in path
            elif mt == "glob":
                matched = fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path.split("/")[-1], pat)
            elif mt == "regex":
                matched = _re.search(pat, path) is not None
        except _re.error:
            _log.warning("bad autotag regex skipped: %r", pat)
            matched = False
        if not matched:
            continue
        for t in [x.strip() for x in (rule.get("tags") or "").split(",") if x.strip()]:
            if t not in tags:
                tags.append(t)
        for k, v in (rule.get("fields") or {}).items():
            fields[k] = v
    return {"tags": tags, "fields": fields}
