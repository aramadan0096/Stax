import pytest


@pytest.mark.unit
def test_expand_terms_includes_group_siblings(stax_db):
    stax_db.add_synonym("fire", "g1")
    stax_db.add_synonym("flame", "g1")
    stax_db.add_synonym("blaze", "g1")
    expanded = set(stax_db.expand_terms("fire"))
    assert {"fire", "flame", "blaze"}.issubset(expanded)


@pytest.mark.unit
def test_expand_terms_passthrough_when_no_group(stax_db):
    assert stax_db.expand_terms("waterfall") == ["waterfall"]
