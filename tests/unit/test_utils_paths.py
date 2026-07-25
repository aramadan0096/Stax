import os

import pytest

from utils.paths import resolve_path


class _FakeConfig(object):
    def __init__(self, root):
        self.root = root

    def resolve_path(self, path):
        if not path:
            return None
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.root, path))


@pytest.mark.unit
def test_none_and_empty_return_none():
    assert resolve_path(None) is None
    assert resolve_path("") is None
    assert resolve_path("   ") is None


@pytest.mark.unit
def test_absolute_path_is_normalized():
    ap = os.path.abspath(os.path.join("x", "y", "..", "z.png"))
    assert resolve_path(ap) == os.path.normpath(ap)


@pytest.mark.unit
def test_relative_joins_project_root_and_strips():
    root = os.path.abspath("proj")
    assert resolve_path("  previews/a.png  ", project_root=root) == \
        os.path.normpath(os.path.join(root, "previews/a.png"))


@pytest.mark.unit
def test_config_consulted_first_for_relative():
    root = os.path.abspath("cfgroot")
    cfg = _FakeConfig(root)
    proj = os.path.abspath("projroot")
    # config path wins over project_root when config resolves a value
    assert resolve_path("a/b.png", project_root=proj, config=cfg) == \
        os.path.normpath(os.path.join(root, "a/b.png"))


@pytest.mark.unit
def test_falls_back_to_project_root_when_config_returns_falsy():
    class _NullConfig(object):
        def resolve_path(self, path):
            return None

    proj = os.path.abspath("projroot")
    assert resolve_path("a/b.png", project_root=proj, config=_NullConfig()) == \
        os.path.normpath(os.path.join(proj, "a/b.png"))
