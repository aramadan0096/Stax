import importlib.util
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_root_init():
    path = os.path.join(_REPO_ROOT, "init.py")
    spec = importlib.util.spec_from_file_location("stax_root_init", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_plugin_paths = _load_root_init().build_plugin_paths


@pytest.mark.unit
def test_all_plugin_paths_are_absolute_and_rooted(tmp_path):
    """L1: plugin paths must be absolute (not CWD-relative './tools')."""
    root = str(tmp_path)
    paths = build_plugin_paths(root)

    for p in paths:
        assert os.path.isabs(p), "not absolute: {}".format(p)

    normalized = {os.path.normpath(p) for p in paths}
    assert os.path.normpath(root) in normalized
    assert os.path.normpath(os.path.join(root, "src", "ui")) in normalized
    assert os.path.normpath(os.path.join(root, "dependencies", "ffpyplayer")) in normalized


@pytest.mark.unit
def test_no_dotslash_relative_segments(tmp_path):
    """L1: no './' prefixes and no lstrip('./') char-strip artifacts."""
    for p in build_plugin_paths(str(tmp_path)):
        assert not p.startswith("./")
        assert not p.startswith(".\\")
