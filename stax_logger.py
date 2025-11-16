# -*- coding: utf-8 -*-
"""
StaX Logger
Comprehensive logging system for debugging Nuke integration issues
"""

import os
import sys
import traceback
from datetime import datetime


class StaXLogger(object):
    """
    Centralized logging system for StaX.
    Writes to both console and log file.
    """
    
    def __init__(self, log_file=None):
        """
        Initialize logger.
        
        Args:
            log_file (str): Path to log file. If None, uses default location.
        """
        if log_file is None:
            # Default log location
            log_dir = os.path.join(os.path.dirname(__file__), 'logs')
            if not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir)
                except Exception as e:
                    print("[StaX Logger] Failed to create log directory: {}".format(e))
                    log_dir = os.path.dirname(__file__)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(log_dir, 'stax_{}.log'.format(timestamp))
        
        self.log_file = log_file
        self.enabled = True
        
        # Write header
        self._write_header()
    
    def _write_header(self):
        """Write log file header."""
        header = """
================================================================================
StaX Debug Log
Started: {}
Python Version: {}
Platform: {}
================================================================================
""".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            sys.version,
            sys.platform
        )
        self._write_to_file(header)
    
    def _write_to_file(self, message):
        """Write message to log file."""
        if not self.enabled:
            return
        
        try:
            with open(self.log_file, 'a') as f:
                f.write(message)
                if not message.endswith('\n'):
                    f.write('\n')
        except Exception as e:
            print("[StaX Logger] Failed to write to log file: {}".format(e))
    
    def _format_message(self, level, message):
        """Format log message with timestamp and level."""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        return "[{}] [{}] {}".format(timestamp, level, message)
    
    def debug(self, message):
        """Log debug message."""
        formatted = self._format_message("DEBUG", message)
        print(formatted)
        self._write_to_file(formatted)
    
    def info(self, message):
        """Log info message."""
        formatted = self._format_message("INFO", message)
        print(formatted)
        self._write_to_file(formatted)
    
    def warning(self, message):
        """Log warning message."""
        formatted = self._format_message("WARNING", message)
        print(formatted)
        self._write_to_file(formatted)
    
    def error(self, message):
        """Log error message."""
        formatted = self._format_message("ERROR", message)
        print(formatted)
        self._write_to_file(formatted)
    
    def critical(self, message):
        """Log critical error message."""
        formatted = self._format_message("CRITICAL", message)
        print(formatted)
        self._write_to_file(formatted)
    
    def exception(self, message):
        """Log exception with full traceback."""
        formatted = self._format_message("EXCEPTION", message)
        print(formatted)
        self._write_to_file(formatted)
        
        # Add traceback
        tb = traceback.format_exc()
        print(tb)
        self._write_to_file(tb)
    
    def separator(self):
        """Write separator line."""
        line = "-" * 80
        print(line)
        self._write_to_file(line)


# Global logger instance
_logger = None


def get_logger():
    """Get or create global logger instance."""
    global _logger
    if _logger is None:
        _logger = StaXLogger()
    return _logger


def init_logger(log_file=None):
    """Initialize logger with custom log file."""
    global _logger
    _logger = StaXLogger(log_file)
    return _logger
