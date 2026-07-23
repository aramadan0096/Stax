# -*- coding: utf-8 -*-
"""Centralized debug-output controller for StaX.

Debug Mode toggles the verbosity of StaX's *own* logger only. It never
replaces the interpreter's ``sys.stdout`` / ``sys.stderr`` and never swallows
``stderr`` — doing so inside a host application (Nuke) silenced the host's own
console and other tools' tracebacks for the whole session (issue H8).
"""

import json
import logging
import os
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'config', 'config.json')

# StaX's own logger namespace. Suppression is scoped to this tree; the root
# logger, sys.stdout, and sys.stderr are left untouched.
_STAX_LOGGER_NAME = 'stax'


class DebugManager(object):
    """Controller for StaX's own debug verbosity (logger-scoped)."""

    _initialized = False
    _enabled = True
    _lock = threading.RLock()

    @classmethod
    def initialize(cls, enabled=True):
        """Configure the StaX logger and set the initial enabled state.

        Does NOT touch sys.stdout / sys.stderr.
        """
        with cls._lock:
            logger = logging.getLogger(_STAX_LOGGER_NAME)
            if not cls._initialized:
                # Give StaX log records a sink without hijacking interpreter
                # streams. A NullHandler stays quiet unless the app installs
                # its own handler (see stax_logger).
                if not logger.handlers:
                    logger.addHandler(logging.NullHandler())
                cls._initialized = True
            cls.set_enabled(enabled)

    @classmethod
    def set_enabled(cls, enabled):
        """Enable or disable StaX debug output (StaX logger level only)."""
        with cls._lock:
            cls._enabled = bool(enabled)
            logger = logging.getLogger(_STAX_LOGGER_NAME)
            logger.setLevel(logging.DEBUG if cls._enabled else logging.WARNING)

    @classmethod
    def is_enabled(cls):
        with cls._lock:
            return cls._enabled

    @classmethod
    def debug(cls, message, *args):
        """Emit a StaX debug message (suppressed when Debug Mode is off).

        Use in place of gated ``print`` calls. stdout/stderr are never
        replaced, so host and other-tool output is unaffected.
        """
        logging.getLogger(_STAX_LOGGER_NAME).debug(message, *args)

    @classmethod
    def restore_original_streams(cls):
        """Back-compat reset. Streams are never replaced anymore, so this only
        clears the initialized flag (kept so existing callers don't break)."""
        with cls._lock:
            cls._initialized = False

    @classmethod
    def bootstrap_from_config(cls, config_path=None):
        """Read the debug preference from the config file and initialize."""
        debug_enabled = cls._read_debug_flag(config_path)
        cls.initialize(debug_enabled)
        return debug_enabled

    @classmethod
    def sync_from_config(cls, config):
        """Update enabled state based on a Config instance."""
        if config is None:
            return
        try:
            enabled = config.get('debug_mode', True)
        except Exception:
            enabled = True
        cls.set_enabled(enabled)

    @staticmethod
    def _read_debug_flag(config_path=None):
        path = config_path or _DEFAULT_CONFIG_PATH
        try:
            with open(path, 'r') as handle:
                data = json.load(handle)
            return bool(data.get('debug_mode', True))
        except Exception:
            return True


__all__ = ['DebugManager']
