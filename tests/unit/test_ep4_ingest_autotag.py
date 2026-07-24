# -*- coding: utf-8 -*-
"""EP4 Task 9: auto-tag + derived-field hook wired into IngestionCore.ingest_file.

Two tests:
  1. test_ingest_merge_helper_unions_tags -- locks the `_merge_tags` merge
     contract that the ingest hook relies on (brief Step 1, verbatim).
  2. test_ingest_applies_autotag_rule_and_fields -- a real, end-to-end
     integration test against the real `stax_db` fixture that actually
     drives `IngestionCore.ingest_file` through the new hook and asserts
     the resulting element carries the derived tag and metadata field.
"""
import pytest
from metadata_rules import evaluate_autotag

from ingestion_core import IngestionCore


@pytest.mark.unit
def test_ingest_merge_helper_unions_tags(stax_db):
    # Verifies the merge contract ingest_file relies on.
    merged = stax_db._merge_tags("base", ",".join(
        evaluate_autotag("/x/explosion.exr",
                         [{"pattern": "explosion", "match_type": "contains",
                           "tags": "fx", "fields": {}}])["tags"]))
    assert "base" in merged and "fx" in merged


@pytest.mark.unit
def test_ingest_applies_autotag_rule_and_fields(stax_db, tmp_path, tiny_png):
    """Real ingest_file run: a matching autotag rule must merge its tags
    into the created element and write its derived fields as metadata,
    without the hook ever blocking a successful ingest."""
    stack_id = stax_db.create_stack("S", str(tmp_path))
    list_id = stax_db.create_list(stack_id, "L")

    stax_db.create_autotag_rule(
        pattern="*.png", match_type="glob", tags="auto",
        field_values={"cs": "ACES"}, stack_fk=stack_id)

    cfg = {
        "previews_path": str(tmp_path / "prev"),
        "generate_previews": False,   # avoid touching the real preview queue
        "dedup_enabled": False,       # avoid phash/dupe scan noise
    }
    core = IngestionCore(stax_db, cfg)

    result = core.ingest_file(tiny_png, target_list_id=list_id, copy_policy="soft")

    assert result["success"] is True, result.get("message")
    element_id = result["element_id"]

    element = stax_db.get_element_by_id(element_id)
    tags = [t.strip() for t in (element["tags"] or "").split(",") if t.strip()]
    assert "auto" in tags

    fields = stax_db.get_element_metadata(element_id)
    assert fields.get("cs") == "ACES"
