# -*- coding: utf-8 -*-
"""Pure (Qt/DB-free) metadata rule logic: coercion, auto-tag, quality, naming (EP4)."""

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
