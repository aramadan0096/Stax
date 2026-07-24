import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        rows = [
            ("plate_a", "2D", ".exr", "fire,city", 5, 0),
            ("plate_b", "2D", ".mov", "water", 2, 0),
            ("geo_c",   "3D", ".abc", "fire", 0, 1),
        ]
        for name, typ, fmt, tags, rating, deprecated in rows:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, format, tags, rating, is_deprecated) "
                "VALUES (1,?,?,?,?,?,?)",
                (name, typ, fmt, tags, rating, deprecated),
            )


@pytest.mark.unit
def test_filter_by_type_and_rating(stax_db):
    _seed(stax_db)
    res = stax_db.search_elements_advanced({"types": ["2D"], "rating_min": 3})
    assert [r["name"] for r in res] == ["plate_a"]


@pytest.mark.unit
def test_tag_include_and_exclude(stax_db):
    _seed(stax_db)
    res = stax_db.search_elements_advanced({"tags_any": ["fire"], "tags_exclude": ["city"]})
    assert [r["name"] for r in res] == ["geo_c"]


@pytest.mark.unit
def test_text_matches_name_or_tags(stax_db):
    _seed(stax_db)
    res = stax_db.search_elements_advanced({"text": "plate"})
    assert {r["name"] for r in res} == {"plate_a", "plate_b"}


@pytest.mark.unit
def test_count_matches_result_length(stax_db):
    _seed(stax_db)
    spec = {"types": ["2D"]}
    assert stax_db.count_elements_advanced(spec) == len(stax_db.search_elements_advanced(spec))


def _seed_underscore(stax_db):
    """Rows whose tags contain a literal underscore/percent, to exercise
    LIKE-metacharacter escaping in tag matching."""
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        rows = [
            ("plate_underscore", "2D", ".exr", "green_screen", 0, 0),
            ("plate_x",          "2D", ".exr", "greenXscreen", 0, 0),
            ("plate_fire",       "2D", ".exr", "fire", 0, 0),
            ("plate_campfire",   "2D", ".exr", "campfire", 0, 0),
            ("plate_percent",    "2D", ".exr", "50%off", 0, 0),
            ("plate_percentx",   "2D", ".exr", "50Xoff", 0, 0),
            ("plate_null_tags",  "2D", ".exr", None, 0, 0),
        ]
        for name, typ, fmt, tags, rating, deprecated in rows:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, format, tags, rating, is_deprecated) "
                "VALUES (1,?,?,?,?,?,?)",
                (name, typ, fmt, tags, rating, deprecated),
            )


@pytest.mark.unit
def test_tag_with_underscore_matches_only_literal(stax_db):
    """A literal '_' in a tag must not act as a SQL LIKE single-char wildcard,
    so `green_screen` should not also match a stored `greenXscreen`."""
    _seed_underscore(stax_db)
    res = stax_db.search_elements_advanced({"tags_any": ["green_screen"]})
    assert [r["name"] for r in res] == ["plate_underscore"]


@pytest.mark.unit
def test_tag_exclude_with_underscore_keeps_non_matching_row(stax_db):
    """Excluding `green_screen` must not also exclude `greenXscreen` via the
    unescaped '_' wildcard."""
    _seed_underscore(stax_db)
    res = stax_db.search_elements_advanced({"tags_exclude": ["green_screen"]})
    names = {r["name"] for r in res}
    assert "plate_x" in names
    assert "plate_underscore" not in names


@pytest.mark.unit
def test_tag_with_percent_matches_literally(stax_db):
    """A literal '%' in a tag must not act as a SQL LIKE any-sequence
    wildcard, so `50%off` should not also match a stored `50Xoff`."""
    _seed_underscore(stax_db)
    res = stax_db.search_elements_advanced({"tags_any": ["50%off"]})
    assert [r["name"] for r in res] == ["plate_percent"]


@pytest.mark.unit
def test_tag_boundary_still_excludes_substring_match(stax_db):
    """Regression guard for the boundary case _TAG_MATCH exists to prevent:
    a plain 'fire' tag filter must not match a 'campfire'-tagged row. This
    already holds against the current code (asserted here, not previously
    covered by a test)."""
    _seed_underscore(stax_db)
    res = stax_db.search_elements_advanced({"tags_any": ["fire"]})
    assert [r["name"] for r in res] == ["plate_fire"]


@pytest.mark.unit
def test_tag_exclude_count_agrees_and_keeps_null_tags_row(stax_db):
    """Regression guard: count/search agreement on an exclude clause, and a
    NULL-tags row is retained (NULL never matches the exclude pattern, so
    NOT ... is true and the row is kept). This already holds against the
    current code (asserted here, not previously covered by a test)."""
    _seed_underscore(stax_db)
    spec = {"tags_exclude": ["fire"]}
    res = stax_db.search_elements_advanced(spec)
    assert stax_db.count_elements_advanced(spec) == len(res)
    assert "plate_null_tags" in {r["name"] for r in res}
