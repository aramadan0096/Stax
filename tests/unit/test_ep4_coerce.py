import pytest
from metadata_rules import validate_field_type, coerce_to_text, parse_from_text


@pytest.mark.unit
def test_validate_type_and_choices():
    validate_field_type("choice", ["a", "b"])       # ok
    with pytest.raises(ValueError):
        validate_field_type("bogus", None)
    with pytest.raises(ValueError):
        validate_field_type("choice", None)          # choice needs choices


@pytest.mark.unit
def test_coerce_and_parse_roundtrip():
    assert coerce_to_text("number", 3) == "3"
    assert parse_from_text("number", "3") == 3.0
    assert coerce_to_text("bool", True) == "1"
    assert parse_from_text("bool", "1") is True
    assert parse_from_text("text", None) == ""
