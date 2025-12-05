# -*- coding: utf-8 -*-
"""Centralized dependency bootstrap for StaX.

Adds project directories, bundled dependencies, and FFmpeg binaries to both
``sys.path`` and the process ``PATH`` so modules like ``ffpyplayer`` and
PySide2 can load inside standalone and DCC-hosted environments.

Env toggles:
- ``STAX_USE_SYSTEM_QT=1`` → skip bundled Qt/PySide2 even if present.
- ``STAX_FORCE_BUNDLED_QT=1`` → force using bundled Qt/PySide2 when available.
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


def _prepend_env_list(var_name, path):
    """Prepend a directory to an env list variable if it exists on disk."""
    if not path or not os.path.isdir(path):
        return
    norm = _normalize(path)
    current = os.environ.get(var_name, "")
    entries = current.split(os.pathsep) if current else []
    if norm not in entries:
        os.environ[var_name] = norm + (os.pathsep + current if current else "")


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

    # Bundled Qt/PySide2 inside lib/ (installed via pip --target . in lib)
    lib_root = os.path.join(project_root, "lib")
    lib_pyside2 = os.path.join(lib_root, "PySide2")
    lib_shiboken2 = os.path.join(lib_root, "shiboken2")
    lib_bin = os.path.join(lib_root, "bin")  # Qt DLLs on Windows
    lib_plugins = os.path.join(lib_root, "plugins")
    lib_pyside_plugins = os.path.join(lib_pyside2, "plugins")

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

    # Prefer bundled Qt unless the user explicitly opts out.
    use_system_qt = os.environ.get("STAX_USE_SYSTEM_QT", "0") == "1"
    force_bundled_qt = os.environ.get("STAX_FORCE_BUNDLED_QT", "0") == "1"
    bundled_qt_exists = os.path.isdir(lib_pyside2)

    qt_source = "system"
    if bundled_qt_exists and (force_bundled_qt or not use_system_qt):
        for path in [lib_root, lib_pyside2, lib_shiboken2]:
            _add_sys_path(path)
        for path in [lib_bin]:
            _add_env_path(path)
        # Ensure Qt plugin path is discoverable (platform plugins, etc.).
        for plugin_path in [lib_plugins, lib_pyside_plugins]:
            _prepend_env_list("QT_PLUGIN_PATH", plugin_path)
        qt_source = "bundled"

    if os.environ.get("STAX_LOG_QT_SOURCE", "1") == "1":
        try:
            print("[bootstrap] Qt source: {}".format(qt_source))
        except Exception:
            pass

    _add_env_path(ffmpeg_bin_dir)

    os.environ[_BOOTSTRAP_FLAG] = "1"


__all__ = ["bootstrap"]
