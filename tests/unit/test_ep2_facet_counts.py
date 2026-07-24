import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for name, typ, fmt in [("a","2D",".exr"), ("b","2D",".mov"), ("c","3D",".abc")]:
            conn.execute("INSERT INTO elements (list_fk,name,type,format) VALUES (1,?,?,?)",
                         (name, typ, fmt))


@pytest.mark.unit
def test_type_facet_counts(stax_db):
    _seed(stax_db)
    counts = stax_db.get_facet_counts({})
    assert counts["type"]["2D"] == 2
    assert counts["type"]["3D"] == 1


@pytest.mark.unit
def test_format_facet_respects_other_filters(stax_db):
    _seed(stax_db)
    counts = stax_db.get_facet_counts({"types": ["2D"]})
    assert counts["format"].get(".exr") == 1
    assert counts["format"].get(".mov") == 1
    assert ".abc" not in counts["format"]


@pytest.mark.unit
def test_type_facet_reports_sibling_when_filtered_by_itself(stax_db):
    """type facet must drop its own `types` clause: with `types=["2D"]`
    active, the facet must still report what clicking `3D` would yield,
    not drop/zero it just because 3D isn't in the currently-active set."""
    _seed(stax_db)
    counts = stax_db.get_facet_counts({"types": ["2D"]})
    assert counts["type"].get("3D") == 1


@pytest.mark.unit
def test_format_facet_reports_sibling_when_filtered_by_itself(stax_db):
    """format facet must drop its own `formats` clause: with `formats=[".exr"]`
    active, sibling formats (.mov, .abc) must still be reported."""
    _seed(stax_db)
    counts = stax_db.get_facet_counts({"formats": [".exr"]})
    assert counts["format"].get(".mov") == 1
    assert counts["format"].get(".abc") == 1


def _seed_ratings(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for name, rating in [("low", 1), ("mid", 3), ("high", 5)]:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, rating) VALUES (1,?,'2D',?)",
                (name, rating))


@pytest.mark.unit
def test_rating_facet_reports_buckets_below_active_threshold(stax_db):
    """rating facet must drop its own `rating_min` clause: with `rating_min=3`
    active (which would exclude rating=1 rows from the result set), the
    rating facet must still report the rating=1 bucket."""
    _seed_ratings(stax_db)
    counts = stax_db.get_facet_counts({"rating_min": 3})
    assert counts["rating"].get(1) == 1
    assert counts["rating"].get(3) == 1
    assert counts["rating"].get(5) == 1


def _seed_labels(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    label_a = stax_db.create_label("A", "#FF0000")
    label_b = stax_db.create_label("B", "#00FF00")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        conn.execute(
            "INSERT INTO elements (list_fk, name, type, label_fk) VALUES (1,'x','2D',?)",
            (label_a,))
        conn.execute(
            "INSERT INTO elements (list_fk, name, type, label_fk) VALUES (1,'y','2D',?)",
            (label_b,))
    return label_a, label_b


@pytest.mark.unit
def test_label_facet_reports_sibling_when_filtered_by_itself(stax_db):
    """label facet must drop its own `label_fks` clause: with a filter
    pinned to label A, label B's element must still be counted."""
    label_a, label_b = _seed_labels(stax_db)
    counts = stax_db.get_facet_counts({"label_fks": [label_a]})
    assert counts["label"].get(label_b) == 1


def _seed_status(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for name, deprecated in [("keep1", 0), ("keep2", 0), ("gone", 1)]:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, is_deprecated) VALUES (1,?,'2D',?)",
                (name, deprecated))


@pytest.mark.unit
def test_status_facet_reports_active_bucket_when_filtered_to_deprecated(stax_db):
    """Fix 1: status facet must drop its own `is_deprecated` clause. With
    `is_deprecated=True` pinned (so the active result set is all-deprecated),
    the 'active' bucket must still be present in the facet -- not missing
    from the dict entirely -- and reflect what toggling to 'active' would
    yield."""
    _seed_status(stax_db)
    counts = stax_db.get_facet_counts({"is_deprecated": True})
    assert counts["status"].get("active") == 2
    assert counts["status"].get("deprecated") == 1


def _seed_tags(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for name, tags in [("r1", "red"), ("rb", "red,blue"),
                           ("b1", "blue"), ("b2", "blue")]:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, tags) VALUES (1,?,'2D',?)",
                (name, tags))


@pytest.mark.unit
def test_tag_facet_reports_full_sibling_count_not_just_cooccurring(stax_db):
    """Fix 1: tag facet must drop tags_any/tags_all/tags_exclude before
    tallying. With `tags_any=["red"]` active (OR semantics -- the active
    result set is only rows carrying 'red'), a sibling tag ('blue') must
    report its full corpus count (3: it co-occurs with 'red' on one row and
    appears alone on two others), not just the count of rows where it
    happens to co-occur with 'red' (which would understate to 1)."""
    _seed_tags(stax_db)
    counts = stax_db.get_facet_counts({"tags_any": ["red"]})
    assert counts["tag"].get("blue") == 3
    assert counts["tag"].get("red") == 2
