import pytest


@pytest.mark.unit
def test_get_recent_elements_newest_first(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("a", "b", "c"):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')", (name,))
    recent = stax_db.get_recent_elements(limit=2)
    assert len(recent) == 2
    assert recent[0]["name"] == "c"   # newest first


@pytest.mark.unit
def test_get_recent_elements_respects_limit_and_tiebreak(stax_db):
    """All three rows share a `created_at` (inserted in one transaction, same
    second), so the ordering must fall back to `element_id DESC` -- confirms
    the tiebreaker in the ORDER BY, not just that *a* limit is applied."""
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("a", "b", "c", "d", "e"):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')", (name,))

    recent = stax_db.get_recent_elements(limit=3)
    assert [r["name"] for r in recent] == ["e", "d", "c"]

    all_recent = stax_db.get_recent_elements(limit=100)
    assert [r["name"] for r in all_recent] == ["e", "d", "c", "b", "a"]


@pytest.mark.unit
def test_get_recent_elements_excludes_deprecated(stax_db):
    """Final whole-branch review 'also fix': get_recent_elements() omitted
    the is_deprecated=0 filter that get_elements_by_list()/
    get_elements_count() apply, so a deprecated element could appear in
    the start page's Recent section and be double-clicked straight into
    Nuke."""
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
        cur = conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'b','2D')")
        deprecated_id = cur.lastrowid
        conn.execute(
            "UPDATE elements SET is_deprecated = 1 WHERE element_id = ?",
            (deprecated_id,),
        )

    recent = stax_db.get_recent_elements(limit=10)
    assert [r["name"] for r in recent] == ["a"]
