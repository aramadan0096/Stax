import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        rows = [
            # name, file_size, is_hard_copy, is_deprecated, phash
            ("a", 1000, 1, 0, "hhhh"),
            ("b",  800, 1, 0, "hhhh"),   # dup of a (same phash)
            ("c",  600, 0, 0, "hhhh"),   # dup of a (same phash)
            ("d",  500, 0, 1, "zzzz"),   # deprecated, unique phash
            ("e",  400, 0, 0, None),     # no phash
        ]
        for name, size, hard, dep, phash in rows:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, file_size, is_hard_copy, "
                "is_deprecated, phash) VALUES (1, ?, '2D', ?, ?, ?, ?)",
                (name, size, hard, dep, phash))


@pytest.mark.unit
def test_storage_stats(stax_db):
    _seed(stax_db)
    s = stax_db.get_storage_stats()
    assert s["element_count"] == 5
    assert s["total_bytes"] == 3300
    assert s["hard_copy_count"] == 2
    assert s["soft_copy_count"] == 3
    assert s["deprecated_count"] == 1
    assert s["deprecated_bytes"] == 500


@pytest.mark.unit
def test_duplicate_stats_exact_phash_cluster(stax_db):
    _seed(stax_db)
    d = stax_db.get_duplicate_stats()
    # cluster "hhhh" has a(1000), b(800), c(600): keep largest 1000, reclaim 1400
    assert d["cluster_count"] == 1
    assert d["duplicate_count"] == 2
    assert d["reclaimable_bytes"] == 1400
