import pytest
from filter_spec import empty_filter, is_active, normalize, FILTER_VERSION


@pytest.mark.unit
def test_empty_filter_is_inactive():
    spec = empty_filter()
    assert spec["v"] == FILTER_VERSION
    assert is_active(spec) is False


@pytest.mark.unit
def test_active_when_any_clause_set():
    assert is_active(normalize({"text": "fire"})) is True
    assert is_active(normalize({"types": ["2D"]})) is True
    assert is_active(normalize({"rating_min": 3})) is True


@pytest.mark.unit
def test_normalize_fills_defaults_and_coerces():
    spec = normalize({"rating_min": "4", "types": None})
    assert spec["rating_min"] == 4
    assert spec["types"] == []
    assert spec["text"] == ""
