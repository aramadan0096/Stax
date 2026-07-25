# -*- coding: utf-8 -*-
"""
StaX Logger
===========
Centralized logging for StaX, built on stdlib ``logging``.

- Writes to a per-user writable directory (paths.get_log_dir()), not next to
    the module, so frozen installs under Program Files still log (M14).
- Uses RotatingFileHandler (fixed filename + rollover), so each process start
    does not create a brand-new timestamped file.
- Initializes once: repeated init calls from multiple entry points do not add
    duplicate handlers.
- Preserves the historical public API used across the codebase.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

try:
    from utils.appdirs import get_log_dir      # flat (src/ on sys.path)
except ImportError:                            # imported as a package
    from src.utils.appdirs import get_log_dir

_LOGGER_NAME = "stax"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


class _SafeStreamHandler(logging.StreamHandler):
    """Stream handler that tolerates invalid stderr handles in test hosts."""

    def emit(self, record):
        try:
            super(_SafeStreamHandler, self).emit(record)
        except OSError:
            pass

    def flush(self):
        try:
            super(_SafeStreamHandler, self).flush()
        except OSError:
            pass


class StaXLogger(object):
    """Thin adapter over logging.Logger preserving StaX's historical API."""

    def __init__(self, log_file=None):
        self._log = logging.getLogger(_LOGGER_NAME)
        self._log.setLevel(logging.DEBUG)
        self._log.propagate = False
        self.log_file = log_file or os.path.join(get_log_dir(), "stax.log")
        self.enabled = True

        self._configure()

    def _configure(self):
        """Attach handlers once; safe to call repeatedly."""
        have_file = any(isinstance(h, RotatingFileHandler) for h in self._log.handlers)
        have_stream = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
            for h in self._log.handlers
        )
        fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")

        if not have_file:
            try:
                file_handler = RotatingFileHandler(
                    self.log_file,
                    maxBytes=_MAX_BYTES,
                    backupCount=_BACKUP_COUNT,
                    encoding="utf-8",
                )
                file_handler.setFormatter(fmt)
                self._log.addHandler(file_handler)
            except OSError as exc:
                sys.__stderr__.write("[StaX Logger] file handler failed: {}\n".format(exc))

        if not have_stream:
            stream_handler = _SafeStreamHandler(sys.__stderr__)
            stream_handler.setFormatter(fmt)
            self._log.addHandler(stream_handler)

    def debug(self, message, *args):
        self._log.debug(message, *args)

    def info(self, message, *args):
        self._log.info(message, *args)

    def warning(self, message, *args):
        self._log.warning(message, *args)

    def error(self, message, *args):
        self._log.error(message, *args)

    def critical(self, message, *args):
        self._log.critical(message, *args)

    def exception(self, message, *args):
        self._log.error(message, *args, exc_info=True)

    def separator(self):
        self._log.info("-" * 80)


# Global logger instance
_logger = None


def get_logger():
    """Get or create the global StaX logger."""
    global _logger
    if _logger is None:
        _logger = StaXLogger()
    return _logger


def init_logger(log_file=None):
    """Initialize or reconfigure the global logger singleton."""
    global _logger
    if _logger is None:
        _logger = StaXLogger(log_file)
    elif log_file is not None:
        _logger.log_file = log_file
        _logger._configure()
    return _logger
