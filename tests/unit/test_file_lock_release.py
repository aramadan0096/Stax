import os
import pytest

from file_lock import FileLockManager


@pytest.mark.unit
def test_release_keeps_lock_file_and_allows_reacquire(tmp_path):
    lock_path = str(tmp_path / "res.lock")
    lock = FileLockManager(lock_path)
    assert lock.acquire() is True
    assert os.path.exists(lock_path)
    lock.release()
    # H1: the file must persist (no delete-on-release inode race).
    assert os.path.exists(lock_path)
    assert lock.is_locked is False
    # And a fresh manager can re-lock the same file.
    lock2 = FileLockManager(lock_path)
    assert lock2.acquire() is True
    lock2.release()
