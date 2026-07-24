import pytest
from metadata_rules import check_element_quality


@pytest.mark.unit
def test_required_field_and_naming():
    fields = [{"key": "shot", "label": "Shot", "required": 1}]
    rules = [
        {"rule_id": 1, "kind": "required_field", "config": {"field_key": "shot"}},
        {"rule_id": 2, "kind": "naming_regex", "config": {"pattern": r"^plate_\d+$"}},
    ]
    issues = check_element_quality({"name": "bad name"}, {"shot": None}, fields, rules)
    kinds = {i["kind"] for i in issues}
    assert "required_field" in kinds and "naming_regex" in kinds

    ok = check_element_quality({"name": "plate_010"}, {"shot": "010"}, fields, rules)
    assert ok == []
