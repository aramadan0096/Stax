# -*- coding: utf-8 -*-
"""Centralized debug-output controller for StaX.

This module wraps ``sys.stdout`` and ``sys.stderr`` with lightweight proxies so
that any ``print`` statements (or direct ``write`` calls) are suppressed when
Debug Mode is disabled via application settings.

Python 2.7 compatible.
"""

import json
import os
import sys
import threading


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'config', 'config.json')


class _DebugStream(object):
    """Proxy stream that conditionally forwards writes to the real stream."""

    def __init__(self, original_stream):
        self._original = original_stream
        self._enabled = True
        self._lock = threading.RLock()

    def set_enabled(self, enabled):
        with self._lock:
            self._enabled = bool(enabled)

    def is_enabled(self):
        with self._lock:
            return self._enabled

    def write(self, data):
        if not data:
            return
        with self._lock:
            if self._enabled:
                self._original.write(data)

    def writelines(self, lines):
        if not lines:
            return
        with self._lock:
            if self._enabled:
                self._original.writelines(lines)

    def flush(self):
        with self._lock:
            if hasattr(self._original, 'flush'):
                self._original.flush()

    def fileno(self):
        fileno_attr = getattr(self._original, 'fileno', None)
        if fileno_attr is None:
            raise AttributeError('fileno')
        return fileno_attr()

    def __iter__(self):
        return iter(self._original)

    def __getattr__(self, name):
        return getattr(self._original, name)

    @property
    def original(self):
        return self._original


class DebugManager(object):
    """Singleton-style controller for application-wide debug output."""

    _initialized = False
    _enabled = True
    _stdout_proxy = None
    _stderr_proxy = None
    _lock = threading.RLock()

    @classmethod
    def initialize(cls, enabled=True):
        """Wrap standard streams and set initial enabled state."""
        with cls._lock:
            if not cls._initialized:
                cls._stdout_proxy = _DebugStream(sys.stdout)
                cls._stderr_proxy = _DebugStream(sys.stderr)
                sys.stdout = cls._stdout_proxy
                sys.stderr = cls._stderr_proxy
                cls._initialized = True
            cls.set_enabled(enabled)

    @classmethod
    def set_enabled(cls, enabled):
        """Enable or disable debug output globally."""
        with cls._lock:
            cls._enabled = bool(enabled)
            if cls._stdout_proxy is not None:
                cls._stdout_proxy.set_enabled(cls._enabled)
            if cls._stderr_proxy is not None:
                cls._stderr_proxy.set_enabled(cls._enabled)

    @classmethod
    def is_enabled(cls):
        with cls._lock:
            return cls._enabled

    @classmethod
    def restore_original_streams(cls):
        """Restore the original stdout/stderr streams."""
        with cls._lock:
            if not cls._initialized:
                return
            sys.stdout = cls._stdout_proxy.original
            sys.stderr = cls._stderr_proxy.original
            cls._stdout_proxy = None
            cls._stderr_proxy = None
            cls._initialized = False

    @classmethod
    def bootstrap_from_config(cls, config_path=None):
        """Read debug preference from config file and initialize streams."""
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
