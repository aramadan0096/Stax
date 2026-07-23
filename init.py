# -*- coding: utf-8 -*-
"""
StaX Init Script for Nuke
Loads on Nuke startup to register StaX's plugin paths.
Single interpreter: Python 3 (Nuke 13+).
"""

import os
import sys


def build_plugin_paths(stax_root):
    """Return the absolute, normalized plugin directories to register with Nuke.

    Pure and importable (no Nuke dependency) so it can be unit-tested. Replaces
    the old CWD-relative './tools' entries and the buggy ``subdir.lstrip('./')``
    char-set strip (issue L1).
    """
    root = os.path.abspath(stax_root)
    subdirs = [
        'tools',
        os.path.join('src', 'ui'),
        'src',
        'resources',
        os.path.join('dependencies', 'ffpyplayer'),
    ]
    paths = [root]
    for subdir in subdirs:
        paths.append(os.path.normpath(os.path.join(root, subdir)))
    return paths


def install_stax_plugin_paths(nuke_module):
    """Register StaX's plugin directories with Nuke using absolute paths."""
    stax_root = os.path.dirname(os.path.abspath(__file__))
    if stax_root not in sys.path:
        sys.path.insert(0, stax_root)

    for path in build_plugin_paths(stax_root):
        nuke_module.pluginAddPath(path)
        if os.path.isdir(path):
            print("[StaX init.py]   [OK] Added: {} (exists)".format(path))
        else:
            print("[StaX init.py]   [WARN] Added: {} (NOT FOUND)".format(path))

    try:
        from stax_logger import init_logger
        logger = init_logger()
        logger.info("StaX init.py completed; plugin paths configured")
    except Exception as exc:
        print("[StaX init.py] [WARN] Logger init failed: {}".format(exc))


# Executed by Nuke on startup. Importable in tests: when `nuke` is unavailable
# the module imports cleanly and simply skips registration.
try:
    import nuke as _nuke
except ImportError:
    _nuke = None

# Only register when a REAL Nuke module is present. In test/CI runs `import nuke`
# can resolve to the tests/nuke package (no pluginAddPath); skip cleanly then (L1).
if _nuke is not None and hasattr(_nuke, "pluginAddPath"):
    print("\n" + "=" * 80)
    print("[StaX init.py] Starting initialization...")
    print("=" * 80)
    try:
        install_stax_plugin_paths(_nuke)
        print("[StaX init.py] [OK] Initialization complete")
        print("=" * 80 + "\n")
    except Exception as exc:
        import traceback
        print("[StaX init.py] [ERROR] Initialization failed: {}".format(exc))
        traceback.print_exc()
        raise
