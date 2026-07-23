# -*- coding: utf-8 -*-
"""OS-aware, per-user writable directories for StaX.

Frozen builds install under a read-only location (e.g. %ProgramFiles%\StaX),
so logs, the database, and config must live in a per-user writable dir.

    Windows :  %LOCALAPPDATA%\StaX\{logs, ...}
    Linux   :  $XDG_STATE_HOME/StaX/logs, $XDG_DATA_HOME/StaX, $XDG_CONFIG_HOME/StaX
    Fallback:  %TEMP%/StaX/<name>   (when the preferred base is unwritable)
"""

import os
import sys
import tempfile

APP_NAME = "StaX"


def _is_windows():
    return sys.platform.startswith("win")


def _user_base(kind):
    """Base dir for kind in {'state', 'data', 'config'}."""
    if _is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
        return os.path.join(base, APP_NAME)
    home = os.path.expanduser("~")
    xdg = {
        "state": os.environ.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state"),
        "data": os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"),
        "config": os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
    }[kind]
    return os.path.join(xdg, APP_NAME)


def _ensure_writable(path):
    """Create `path`; on failure or if not writable, fall back under the temp dir."""
    try:
        os.makedirs(path, exist_ok=True)
        if os.access(path, os.W_OK):
            return path
    except OSError:
        pass
    fallback = os.path.join(
        tempfile.gettempdir(), APP_NAME, os.path.basename(path.rstrip("/\\")) or APP_NAME
    )
    os.makedirs(fallback, exist_ok=True)
    return fallback


def get_log_dir():
    """Per-user writable directory for StaX logs."""
    return _ensure_writable(os.path.join(_user_base("state"), "logs"))


def get_data_dir():
    """Per-user writable directory for the StaX database and previews."""
    return _ensure_writable(_user_base("data"))


def get_config_dir():
    """Per-user writable directory for StaX configuration."""
    return _ensure_writable(_user_base("config"))
