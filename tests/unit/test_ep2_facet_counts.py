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
