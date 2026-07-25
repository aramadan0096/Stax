# -*- coding: utf-8 -*-
"""Permission contract shared by EP8 granular roles and SP4 auth hardening.
Qt-free and DB-free so it is unit-testable in isolation."""

PERMISSIONS = (
    "can_ingest",
    "can_delete",
    "can_edit_metadata",
    "can_manage_users",
    "can_manage_schema",
)

# built-in role name -> granted permission set
BUILTIN_ROLES = {
    "admin":    set(PERMISSIONS),                     # admin implies all
    "user":     {"can_ingest", "can_edit_metadata"},
    "reviewer": {"can_edit_metadata"},
    "ingestor": {"can_ingest"},
    "viewer":   set(),
}


def is_valid_permission(permission):
    return permission in PERMISSIONS


def default_permissions_for(role_name):
    """Built-in default permission set for a role name (empty for unknown)."""
    return set(BUILTIN_ROLES.get(role_name, set()))
