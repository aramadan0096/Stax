import os


def test_stax_db_uses_real_lowercase_schema(stax_db):
    """The DB fixture must build the LIVE DatabaseManager schema (lowercase tables),
    not the orphaned capitalized 'Elements'/'InsertionLog' schema."""
    with stax_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert "elements" in names
    assert "stacks" in names
    assert "lists" in names
    # The fantasy schema's capitalized tables must NOT be present
    assert "Elements" not in names
    assert "InsertionLog" not in names


def test_tiny_sequence_returns_multiple_frames(tiny_sequence):
    assert len(tiny_sequence) >= 3
    for p in tiny_sequence:
        assert os.path.isfile(p)


def test_mock_nuke_is_importable(mock_nuke):
    import sys
    assert "nuke" in sys.modules
