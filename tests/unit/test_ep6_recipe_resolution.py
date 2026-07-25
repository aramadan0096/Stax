import pytest


@pytest.mark.unit
def test_resolve_recipe_config_resolves_profile_and_chain(stax_db):
    high = next(p for p in stax_db.get_proxy_profiles() if p["name"] == "High")  # seeded, max_size 1024
    cid = stax_db.create_action_chain("C", [{"action": "add_tag", "params": {"tag": "x"}}])
    cfg = stax_db.resolve_recipe_config(
        {"copy_policy": "hard", "proxy_profile_id": high["profile_id"], "action_chain_id": cid},
        {"preview_size": 512})
    assert cfg["copy_policy"] == "hard"
    assert cfg["preview_size"] == high["max_size"]          # profile overlay applied
    assert cfg["generate_video_previews"] is True           # kind == 'mp4'
    assert cfg["action_chain_steps"][0]["action"] == "add_tag"


@pytest.mark.unit
def test_resolve_recipe_config_plain_recipe_no_crash(stax_db):
    cfg = stax_db.resolve_recipe_config({"copy_policy": "soft", "tags": "plate"}, {"preview_size": 512})
    assert cfg["copy_policy"] == "soft" and cfg["preview_size"] == 512
    assert "action_chain_steps" not in cfg
