# -*- coding: utf-8 -*-
"""
File Lock Manager for Network-aware SQLite Access
Provides robust file locking for concurrent database access across network shares
Python 2.7 compatible
"""

import os
import time
import errno
import sys
from contextlib import contextmanager

# Platform-specific imports
if sys.platform == 'win32':
    import msvcrt
    PLATFORM_WINDOWS = True
else:
    import fcntl
    PLATFORM_WINDOWS = False


class FileLockManager(object):
    """
    Cross-platform file locking manager for SQLite database on network shares.
    
    Implements advisory file locking with:
    - Exponential backoff retry logic
    - Timeout handling
    - Automatic lock release
    - Platform-specific locking (Windows vs POSIX)
    """
    
    def __init__(self, lock_file_path, timeout=30.0, retry_delay=0.1, max_retries=100):
        """
        Initialize file lock manager.
        
        Args:
            lock_file_path (str): Path to lock file (.lock extension recommended)
            timeout (float): Maximum time to wait for lock acquisition (seconds)
            retry_delay (float): Initial delay between lock attempts (seconds)
            max_retries (int): Maximum number of lock acquisition attempts
        """
        self.lock_file_path = lock_file_path
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.lock_file = None
        self.is_locked = False
        
        # Ensure lock file directory exists
        lock_dir = os.path.dirname(lock_file_path)
        if lock_dir and not os.path.exists(lock_dir):
            os.makedirs(lock_dir)
    
    def acquire(self):
        """
        Acquire file lock with exponential backoff retry logic.
        
        Returns:
            bool: True if lock acquired successfully, False otherwise
            
        Raises:
            IOError: If unable to create/access lock file
            TimeoutError: If lock acquisition times out
        """
        start_time = time.time()
        attempt = 0
        current_delay = self.retry_delay
        
        while attempt < self.max_retries:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= self.timeout:
                raise TimeoutError(
                    "Failed to acquire lock after {:.2f} seconds ({} attempts)".format(
                        elapsed, attempt
                    )
                )
            
            try:
                # Open/create lock file
                if self.lock_file is None:
                    self.lock_file = open(self.lock_file_path, 'a+')
                
                # Platform-specific locking
                if PLATFORM_WINDOWS:
                    self._lock_windows()
                else:
                    self._lock_posix()
                
                # Successfully acquired lock
                self.is_locked = True
                
                # Write lock info
                self.lock_file.seek(0)
                self.lock_file.truncate()
                self.lock_file.write("Locked at: {}\n".format(time.time()))
                self.lock_file.write("PID: {}\n".format(os.getpid()))
                self.lock_file.flush()
                
                return True
            
            except (IOError, OSError) as e:
                # Lock is held by another process
                if e.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                    attempt += 1
                    
                    # Exponential backoff with jitter
                    import random
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(current_delay * jitter, 2.0)  # Cap at 2 seconds
                    
                    time.sleep(sleep_time)
                    current_delay *= 1.5  # Exponential backoff factor
                    continue
                else:
                    # Unexpected error
                    raise
        
        # Max retries exceeded
        raise TimeoutError(
            "Failed to acquire lock after {} attempts (timeout: {}s)".format(
                attempt, self.timeout
            )
        )
    
    def release(self):
        """
        Release file lock.
        
        Returns:
            bool: True if lock released successfully
        """
        if not self.is_locked:
            return False
        
        try:
            # Platform-specific unlocking
            if PLATFORM_WINDOWS:
                self._unlock_windows()
            else:
                self._unlock_posix()
            
            # Close and clean up lock file
            if self.lock_file:
                self.lock_file.close()
                self.lock_file = None
            
            # Remove lock file
            try:
                if os.path.exists(self.lock_file_path):
                    os.remove(self.lock_file_path)
            except OSError:
                pass  # Lock file may be in use by another process
            
            self.is_locked = False
            return True
        
        except Exception as e:
            print("Warning: Failed to release lock: {}".format(str(e)))
            return False
    
    def _lock_windows(self):
        """Acquire file lock on Windows using msvcrt."""
        try:
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except IOError as e:
            # Convert to OSError with appropriate errno for retry logic
            raise OSError(errno.EAGAIN, "Lock held by another process")
    
    def _unlock_windows(self):
        """Release file lock on Windows using msvcrt."""
        if self.lock_file:
            try:
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except IOError:
                pass
    
    def _lock_posix(self):
        """Acquire file lock on POSIX systems using fcntl."""
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    
    def _unlock_posix(self):
        """Release file lock on POSIX systems using fcntl."""
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
    
    def __enter__(self):
        """Context manager entry - acquire lock."""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release lock."""
        self.release()
        return False  # Don't suppress exceptions
    
    def __del__(self):
        """Destructor - ensure lock is released."""
        if self.is_locked:
            self.release()


@contextmanager
def file_lock(lock_file_path, timeout=30.0):
    """
    Convenience context manager for file locking.
    
    Usage:
        with file_lock('/path/to/database.db.lock'):
            # Perform locked operations
            pass
    
    Args:
        lock_file_path (str): Path to lock file
        timeout (float): Maximum time to wait for lock (seconds)
    
    Yields:
        FileLockManager: Lock manager instance
    """
    lock = FileLockManager(lock_file_path, timeout=timeout)
    try:
        lock.acquire()
        yield lock
    finally:
        lock.release()


# Python 2.7 compatibility: Define TimeoutError if not available
if not hasattr(__builtins__, 'TimeoutError'):
    class TimeoutError(OSError):
        """Timeout error for Python 2.7 compatibility."""
        pass
