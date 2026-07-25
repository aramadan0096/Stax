import os
import pytest

from ingest_automation import (
    scan_folder, apply_recipe_to_config, resolve_duplicate_action, run_preflight,
)


@pytest.mark.unit
def test_scan_folder_detects_new_and_ignores_seen(tmp_path):
    (tmp_path / "a.exr").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")   # wrong ext, ignored
    new, seen = scan_folder(str(tmp_path), set(), exts={".exr"})
    assert [os.path.basename(p) for p in new] == ["a.exr"]
    # second pass: nothing new
    new2, seen2 = scan_folder(str(tmp_path), seen, exts={".exr"})
    assert new2 == []
    # add a file -> detected
    (tmp_path / "c.exr").write_bytes(b"x")
    new3, seen3 = scan_folder(str(tmp_path), seen2, exts={".exr"})
    assert [os.path.basename(p) for p in new3] == ["c.exr"]


@pytest.mark.unit
def test_apply_recipe_overlays_and_preserves_base():
    base = {"copy_policy": "soft", "preview_size": 512, "unrelated": 1}
    merged = apply_recipe_to_config({"copy_policy": "hard", "tags": "review"}, base)
    assert merged["copy_policy"] == "hard"
    assert merged["unrelated"] == 1
    assert merged["tags"] == "review"
    assert base["copy_policy"] == "soft"   # base not mutated


@pytest.mark.unit
def test_resolve_duplicate_action():
    assert resolve_duplicate_action("skip", []) == "allow"       # no dupes
    assert resolve_duplicate_action("skip", [{"element_id": 1}]) == "skip"
    assert resolve_duplicate_action("version", [{"element_id": 1}]) == "version"
    assert resolve_duplicate_action("bogus", [{"element_id": 1}]) == "allow"


@pytest.mark.unit
def test_run_preflight_flags_missing_empty_unknown(tmp_path):
    good = tmp_path / "g.exr"; good.write_bytes(b"data")
    empty = tmp_path / "e.exr"; empty.write_bytes(b"")
    weird = tmp_path / "w.xyz"; weird.write_bytes(b"data")
    issues = run_preflight(
        [str(good), str(empty), str(weird), str(tmp_path / "missing.exr")],
        known_exts={".exr"})
    codes = {i["code"] for i in issues}
    assert codes == {"empty", "unknown_ext", "missing"}
    assert all("path" in i and "level" in i for i in issues)
    # good file produced no issue
    assert run_preflight([str(good)], known_exts={".exr"}) == []
