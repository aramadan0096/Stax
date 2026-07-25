import pytest


@pytest.mark.gui
def test_ingest_hook_enqueues_new_element(qtbot, stax_db, stax_config, tiny_png):
    # A minimal stand-in for the wiring contract: setting ai_index_hook on the
    # ingestion core (as main.py's startup wiring does) causes ingest_file to
    # enqueue the new element id after create_element (Task 5's hook point).
    from ingestion_core import IngestionCore

    core = IngestionCore(stax_db, stax_config.get_all())
    enqueued = []
    core.ai_index_hook = lambda eid: enqueued.append(eid)

    stack_id = stax_db.create_stack("S", str(tiny_png))
    list_id = stax_db.create_list(stack_id, "L")

    result = core.ingest_file(tiny_png, list_id, copy_policy="soft")

    assert result["success"] is True
    assert enqueued == [result["element_id"]]
