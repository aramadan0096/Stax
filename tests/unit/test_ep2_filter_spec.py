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


# --- Fix (a): a bare string/bytes for a list key must be wrapped in a
# single-element list, not shredded into characters. ---------------------

@pytest.mark.unit
def test_bare_string_for_list_key_is_wrapped_not_shredded():
    spec = normalize({"types": "2D", "tags_all": "beach"})
    assert spec["types"] == ["2D"]
    assert spec["tags_all"] == ["beach"]


# --- Fix (b): a non-coercible int value must degrade to the key's
# default instead of raising ValueError. ----------------------------------

@pytest.mark.unit
def test_noncoercible_rating_min_falls_back_to_default():
    spec = normalize({"rating_min": "N/A"})
    assert spec["rating_min"] == 0


# --- Fix (c): an explicit 0 for list_fk/stack_fk must survive
# normalization instead of collapsing to None. ----------------------------

@pytest.mark.unit
def test_explicit_zero_fk_survives_normalization():
    spec = normalize({"list_fk": 0, "stack_fk": 0})
    assert spec["list_fk"] == 0
    assert spec["stack_fk"] == 0


# --- Falsy-vs-absent contract: rating_min=0 stays inactive (no rating
# filter), is_deprecated=False stays active (explicit filter clause). ----

@pytest.mark.unit
def test_falsy_vs_absent_contract_holds():
    assert is_active(normalize({"rating_min": 0})) is False
    assert is_active(normalize({"is_deprecated": False})) is True


# --- normalize(None) and normalize({}) must still return a full
# default spec (no crash, no partial spec). -------------------------------

@pytest.mark.unit
def test_normalize_none_and_empty_dict_return_full_default_spec():
    default = empty_filter()
    assert normalize(None) == default
    assert normalize({}) == default
