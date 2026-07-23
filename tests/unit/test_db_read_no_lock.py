import pytest

from db_manager import DatabaseManager


@pytest.mark.unit
def test_reads_do_not_acquire_file_lock(tmp_path, mocker):
    # Use a real lock-enabled manager so the write path DOES acquire.
    db_path = str(tmp_path / "lock_test.db")
    db = DatabaseManager(db_path, enable_logging=False, use_file_lock=True)

    import file_lock
    spy = mocker.spy(file_lock.FileLockManager, "acquire")

    # Read path: must NOT acquire the external lock.
    db.get_all_stacks()
    assert spy.call_count == 0

    # Write path: must acquire it.
    db.create_stack("S", "/tmp/S")
    assert spy.call_count >= 1
