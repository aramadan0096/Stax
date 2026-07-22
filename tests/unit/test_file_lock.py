import pytest

from file_lock import FileLockManager


@pytest.mark.unit
def test_acquire_and_release_toggles_state(tmp_path):
    lock = FileLockManager(str(tmp_path / "res.lock"))
    assert lock.is_locked is False
    assert lock.acquire() is True
    assert lock.is_locked is True
    lock.release()
    assert lock.is_locked is False
