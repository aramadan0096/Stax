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
