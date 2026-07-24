import pytest
from metadata_rules import evaluate_autotag


@pytest.mark.unit
def test_evaluate_contains_glob_regex():
    rules = [
        {"pattern": "explosion", "match_type": "contains", "tags": "fx,fire", "fields": {}},
        {"pattern": "*.exr", "match_type": "glob", "tags": "exr", "fields": {"cs": "ACES"}},
        {"pattern": r"sh(\d+)", "match_type": "regex", "tags": "shot", "fields": {}},
    ]
    out = evaluate_autotag("/mov/explosion/sh010.exr", rules)
    assert set(out["tags"]) == {"fx", "fire", "exr", "shot"}
    assert out["fields"]["cs"] == "ACES"


@pytest.mark.unit
def test_bad_regex_skipped():
    rules = [{"pattern": "([", "match_type": "regex", "tags": "x", "fields": {}}]
    assert evaluate_autotag("/a/b", rules) == {"tags": [], "fields": {}}
