import pytest
from ingest_automation import profile_to_config_overlay


@pytest.mark.unit
def test_seeded_presets_exist(stax_db):
    names = {p["name"] for p in stax_db.get_proxy_profiles()}
    assert {"Low", "Medium", "High"}.issubset(names)
    med = next(p for p in stax_db.get_proxy_profiles() if p["name"] == "Medium")
    assert med["max_size"] == 512 and med["is_default"] == 1


@pytest.mark.unit
def test_create_and_delete(stax_db):
    pid = stax_db.create_proxy_profile("Ultra", kind="mp4", max_size=2048, fps=30)
    assert any(p["name"] == "Ultra" for p in stax_db.get_proxy_profiles())
    stax_db.delete_proxy_profile(pid)
    assert not any(p["name"] == "Ultra" for p in stax_db.get_proxy_profiles())


@pytest.mark.unit
def test_profile_to_config_overlay_maps_sp2_keys():
    overlay = profile_to_config_overlay(
        {"kind": "mp4", "max_size": 1024, "fps": 30, "duration": 5})
    assert overlay["preview_size"] == 1024
    assert overlay["gif_size"] == 1024
    assert overlay["sequence_preview_fps"] == 30
    assert overlay["gif_fps"] == 30
    assert overlay["gif_duration"] == 5
    assert overlay["generate_video_previews"] is True
    # a thumbnail-only profile disables video
    assert profile_to_config_overlay(
        {"kind": "thumbnail", "max_size": 256, "fps": 24})["generate_video_previews"] is False
