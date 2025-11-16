# -*- coding: utf-8 -*-
"""Centralized dependency bootstrap for StaX.

Adds project directories, bundled dependencies, and FFmpeg binaries to both
``sys.path`` and the process ``PATH`` so modules like ``ffpyplayer`` can load
inside standalone and Nuke-hosted environments.
"""

from __future__ import absolute_import

import os
import sys

_BOOTSTRAP_FLAG = "STAX_BOOTSTRAP_DONE"


def _normalize(path):
    return os.path.normpath(path) if path else path


def _add_sys_path(path):
    if not path or not os.path.isdir(path):
        return
    norm = _normalize(path)
    if norm not in sys.path:
        sys.path.insert(0, norm)


def _add_env_path(path):
    if not path or not os.path.isdir(path):
        return
    norm = _normalize(path)
    current = os.environ.get("PATH", "")
    entries = current.split(os.pathsep) if current else []
    if norm not in entries:
        os.environ["PATH"] = norm + (os.pathsep + current if current else "")


def _ffpyplayer_available():
    """Return True if ffpyplayer can be imported from current environment."""
    try:
        import ffpyplayer  # pylint: disable=unused-import,import-error
        return True
    except Exception:
        return False


def bootstrap(base_dir=None):
    """Ensure StaX dependencies are available on sys.path and PATH.

    Args:
        base_dir (str, optional): Project root. Defaults to the directory
            containing this bootstrap module.
    """
    if os.environ.get(_BOOTSTRAP_FLAG):
        return

    project_root = _normalize(base_dir or os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(project_root, "src")
    repository_dir = os.path.join(project_root, "repository")
    dependencies_root = os.path.join(project_root, "dependencies")
    ffpyplayer_dir = os.path.join(dependencies_root, "ffpyplayer")
    ffpyplayer_player_dir = os.path.join(ffpyplayer_dir, "player")
    ffmpeg_bin_dir = os.path.join(project_root, "bin", "ffmpeg", "bin")

    for path in [project_root, src_dir, repository_dir]:
        _add_sys_path(path)

    needs_bundled_ffpy = bool(os.environ.get("STAX_FORCE_BUNDLED_FFPYPLAYER"))
    if not needs_bundled_ffpy:
        needs_bundled_ffpy = not _ffpyplayer_available()

    if needs_bundled_ffpy:
        for path in [dependencies_root, ffpyplayer_dir, ffpyplayer_player_dir]:
            _add_sys_path(path)
        for path in [ffpyplayer_dir, ffpyplayer_player_dir]:
            _add_env_path(path)

    _add_env_path(ffmpeg_bin_dir)

    os.environ[_BOOTSTRAP_FLAG] = "1"


__all__ = ["bootstrap"]
