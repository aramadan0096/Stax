import pytest


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    return lid, stax_db.create_element(lid, "keep", "2D", format="exr")


@pytest.mark.unit
def test_search_elements_bad_property_is_coerced_not_injected(stax_db):
    lid, eid = _seed(stax_db)
    # A hostile property name must not drop the table or raise a SQL error.
    results = stax_db.search_elements(
        "keep", property_name="name = 'x' OR 1=1; DROP TABLE elements; --"
    )
    # coerced to 'name': the loose search for 'keep' still matches the seeded row
    assert any(r["element_id"] == eid for r in results)
    # table survived
    assert stax_db.get_element_by_id(eid) is not None


@pytest.mark.unit
def test_update_element_ignores_non_whitelisted_keys(stax_db):
    lid, eid = _seed(stax_db)
    # A hostile "column" key must be filtered out, leaving a no-op (False).
    changed = stax_db.update_element(
        eid, **{"name = name || (SELECT 'x')": "boom"}
    )
    assert changed is False
    assert stax_db.get_element_by_id(eid)["name"] == "keep"
