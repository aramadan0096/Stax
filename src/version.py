# -*- coding: utf-8 -*-
"""Single source of truth for the StaX version.

Consumed by pyproject.toml (hatchling dynamic version), setup_freeze.py,
tools/build.ps1, tools/build_win_installer.ps1, and the running app.
"""

__version__ = "0.1.0"


def get_version():
    """Return the canonical StaX version string."""
    return __version__
