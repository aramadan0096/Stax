import pytest

import ingest_automation


@pytest.mark.unit
def test_resolve_duplicate_action_used_by_policy():
    # Contract test: the resolver the ingest path calls behaves as ingest expects.
    assert ingest_automation.resolve_duplicate_action("skip", [{"element_id": 1}]) == "skip"
    assert ingest_automation.resolve_duplicate_action("allow", [{"element_id": 1}]) == "allow"


@pytest.mark.unit
def test_ingest_file_skips_on_skip_policy(stax_db, stax_config, tiny_png, monkeypatch):
    from ingestion_core import IngestionCore
    import ingestion_core
    # Force a duplicate hit regardless of DB contents.
    monkeypatch.setattr(ingestion_core, "find_duplicates",
                        lambda db, phash, threshold=8: [{"element_id": 99}], raising=False)
    cfg = stax_config.get_all()
    cfg["dedup_enabled"] = True
    cfg["duplicate_policy"] = "skip"
    core = IngestionCore(stax_db, cfg)
    stack_id = stax_db.create_stack("S", str(tiny_png))
    list_id = stax_db.create_list(stack_id, "L")
    result = core.ingest_file(tiny_png, list_id, copy_policy="soft")
    assert result["success"] is False
    assert result.get("reason") == "duplicate_skipped"


@pytest.mark.unit
def test_action_chain_runs_after_ingest(stax_db, stax_config, tiny_png):
    from ingestion_core import IngestionCore
    cfg = stax_config.get_all()
    cfg["action_chain_steps"] = [{"action": "add_tag", "params": {"tag": "auto"}}]
    core = IngestionCore(stax_db, cfg)
    stack_id = stax_db.create_stack("S", str(tiny_png))
    list_id = stax_db.create_list(stack_id, "L")
    result = core.ingest_file(tiny_png, list_id, copy_policy="soft")
    eid = result["element_id"]
    assert "auto" in (stax_db.get_element_by_id(eid).get("tags") or "")
