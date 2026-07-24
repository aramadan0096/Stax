import pytest
from metadata_rules import suggest_name


@pytest.mark.unit
def test_valid_name_ok():
    ok, suggestion = suggest_name("plate_010", r"^plate_\d+$")
    assert ok is True and suggestion is None


@pytest.mark.unit
def test_invalid_name_suggests_cleaned():
    ok, suggestion = suggest_name("Plate 010!", r"^[a-z0-9_]+$")
    assert ok is False
    assert suggestion == "plate_010"


@pytest.mark.unit
def test_no_pattern_is_ok():
    assert suggest_name("anything", None) == (True, None)
