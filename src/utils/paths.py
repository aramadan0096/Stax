# -*- coding: utf-8 -*-
"""Shared path helpers (consolidates the former per-widget _resolve_path copies)."""

import os


def resolve_path(path, project_root=None, config=None):
    """Resolve a stored (possibly relative) asset path to an absolute filesystem path.

    Args:
        path (str | None): Stored path. Empty / whitespace-only returns None.
        project_root (str | None): Root to join relative paths against.
        config (Config | None): If given and the path is relative, ``config.resolve_path``
            is consulted first (used by the drag/storage call site).

    Returns:
        str | None: A normalized absolute path, or None for falsy input.
    """
    if not path:
        return None
    path = path.strip()
    if not path:
        return None
    if os.path.isabs(path):
        return os.path.normpath(path)
    if config is not None:
        resolved = config.resolve_path(path)
        if resolved:
            return os.path.normpath(resolved)
    if project_root:
        return os.path.normpath(os.path.join(project_root, path))
    return os.path.normpath(path)
