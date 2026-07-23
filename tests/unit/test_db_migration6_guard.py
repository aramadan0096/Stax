import sqlite3
import pytest

from db_manager import DatabaseManager


def _seed_valid_db(tmp_path, n_elements):
    """Build a normal DB, return (path, list_id, [element_ids...], playlist_id)."""
    path = str(tmp_path / "mig6.db")
    db = DatabaseManager(path, enable_logging=False, use_file_lock=False)
    sid = db.create_stack("S", "/tmp/S")
    lid = db.create_list(sid, "L")
    eids = [db.create_element(lid, "e{}".format(i), "2D") for i in range(n_elements)]
    pid = db.create_playlist("P")
    return path, lid, eids, pid


def _install_legacy_playlist_items(path, rows):
    """Drop playlist_items and recreate it in the OLD (no item_id) shape with *rows*."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DROP TABLE playlist_items")
    conn.execute(
        "CREATE TABLE playlist_items ("
        " playlist_fk INTEGER NOT NULL,"
        " element_fk INTEGER NOT NULL,"
        " order_index INTEGER DEFAULT 0,"
        " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.executemany(
        "INSERT INTO playlist_items (playlist_fk, element_fk, order_index) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


@pytest.mark.unit
def test_migration6_preserves_distinct_rows(tmp_path):
    path, lid, eids, pid = _seed_valid_db(tmp_path, 3)
    _install_legacy_playlist_items(
        path, [(pid, eids[0], 0), (pid, eids[1], 1), (pid, eids[2], 2)]
    )
    # Re-open: _apply_migrations runs Migration 6.
    db2 = DatabaseManager(path, enable_logging=False, use_file_lock=False)
    with db2.get_connection(write=False) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(playlist_items)")}
        count = conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0]
    assert "item_id" in cols       # migrated to new shape
    assert count == 3              # no data loss


@pytest.mark.unit
def test_migration6_raises_on_row_count_mismatch(tmp_path):
    path, lid, eids, pid = _seed_valid_db(tmp_path, 1)
    # Two identical (playlist_fk, element_fk) rows collapse under the new
    # UNIQUE(playlist_fk, element_fk) constraint -> copied count < source count.
    _install_legacy_playlist_items(path, [(pid, eids[0], 0), (pid, eids[0], 1)])
    with pytest.raises(RuntimeError):
        DatabaseManager(path, enable_logging=False, use_file_lock=False)
    # Original legacy table must be intact (rolled back, not swapped/dropped).
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    src = conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0]
    conn.close()
    assert "playlist_items_old" not in tables
    assert src == 2
