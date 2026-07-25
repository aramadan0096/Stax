import pytest
from ingest_automation import run_action_chain, BUILTIN_ACTIONS


@pytest.mark.unit
def test_chain_crud(stax_db):
    cid = stax_db.create_action_chain(
        "Review prep", [{"action": "add_tag", "params": {"tag": "review"}}])
    chains = stax_db.get_action_chains()
    assert chains[0]["name"] == "Review prep"
    assert chains[0]["steps"][0]["action"] == "add_tag"
    stax_db.delete_action_chain(cid)
    assert stax_db.get_action_chains() == []


@pytest.mark.unit
def test_run_action_chain_runs_known_in_order():
    calls = []
    handlers = {
        "one": lambda ctx, p: calls.append(("one", p.get("v"))) or "ok1",
        "two": lambda ctx, p: calls.append(("two", p.get("v"))) or "ok2",
    }
    steps = [{"action": "one", "params": {"v": 1}},
             {"action": "two", "params": {"v": 2}}]
    results = run_action_chain(steps, context={"element_id": 5}, handlers=handlers)
    assert calls == [("one", 1), ("two", 2)]
    assert [r["ok"] for r in results] == [True, True]


@pytest.mark.unit
def test_unknown_action_is_reported_not_executed():
    results = run_action_chain(
        [{"action": "danger_exec", "params": {}}], context={}, handlers={})
    assert results[0]["ok"] is False
    assert "unknown" in results[0]["message"].lower()


@pytest.mark.unit
def test_builtin_actions_are_registered():
    assert {"add_tag", "set_field", "move_to_list", "generate_proxy", "notify"} \
        <= set(BUILTIN_ACTIONS)
