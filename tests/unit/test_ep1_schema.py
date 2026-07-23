import pytest


@pytest.mark.unit
def test_elements_has_rating_and_label_columns(stax_db):
    with stax_db.get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)").fetchall()}
    assert "rating" in cols
    assert "label_fk" in cols


@pytest.mark.unit
def test_labels_table_seeded_with_default_palette(stax_db):
    with stax_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT name, color_hex FROM labels ORDER BY sort_order"
        ).fetchall()
    names = [r[0] for r in rows]
    assert names[:3] == ["Reject", "Review", "Approved"]
    assert len(rows) == 7
    for _, color in rows:
        assert color.startswith("#") and len(color) == 7
