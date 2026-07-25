import pytest
from metadata_rules import suggest_name


@pytest.mark.unit
def test_naming_pattern_prefers_stack_scoped_rule_over_global(stax_db):
    """I4: when both a stack-scoped and a global naming_regex rule exist,
    naming_pattern_for_stack must deterministically pick the stack-scoped
    one, regardless of insertion order or SQLite row ordering."""
    stack_id = stax_db.create_stack("S", "/tmp/S")
    stax_db.create_quality_rule("naming_regex", {"pattern": r"^GLOBAL_\d+$"}, stack_fk=None)
    stax_db.create_quality_rule("naming_regex", {"pattern": r"^stack_\d+$"}, stack_fk=stack_id)

    assert stax_db.naming_pattern_for_stack(stack_id) == r"^stack_\d+$"


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
