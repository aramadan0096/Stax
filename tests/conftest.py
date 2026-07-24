# -*- coding: utf-8 -*-
"""tests/conftest.py — shared fixtures for the StaX test suite.

Run:  pytest -m "not manual"
"""

import os
import sys
import types

import pytest

# Headless Qt BEFORE any Qt import happens anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make both the repo root and src/ importable (StaX modules import siblings flat).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")
for _p in (_REPO_ROOT, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Real DatabaseManager on a temp DB
# ---------------------------------------------------------------------------

@pytest.fixture
def stax_db(tmp_path):
    """A real DatabaseManager backed by a throwaway SQLite file.

    File locking is disabled so tests don't touch a shared lock file.
    """
    from db_manager import DatabaseManager

    db_path = str(tmp_path / "stax_test.db")
    db = DatabaseManager(db_path, enable_logging=False, use_file_lock=False)
    yield db


# ---------------------------------------------------------------------------
# Real Config on a temp config.json
# ---------------------------------------------------------------------------

@pytest.fixture
def stax_config(tmp_path, monkeypatch):
    """A real Config with a temp config path and no STOCK_DB override."""
    from config import Config

    monkeypatch.delenv("STOCK_DB", raising=False)
    cfg_path = str(tmp_path / "config.json")
    return Config(config_path=cfg_path)


# ---------------------------------------------------------------------------
# Fake `nuke` module for the nuke tier
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nuke():
    """Inject a minimal fake `nuke` module so nuke-facing imports succeed."""
    fake = types.ModuleType("nuke")

    class _Node(dict):
        def __getitem__(self, k):
            return self.setdefault(k, _Knob())

    class _Knob(object):
        def __init__(self):
            self._v = None
        def setValue(self, v):
            self._v = v
        def value(self):
            return self._v

    fake.nodes = types.SimpleNamespace(
        Read=lambda **kw: _Node(kw),
        ReadGeo=lambda **kw: _Node(kw),
        ReadGeo2=lambda **kw: _Node(kw),
    )
    fake.pluginAddPath = lambda *a, **k: None
    fake.nodePaste = lambda *a, **k: None
    fake.selectedNodes = lambda *a, **k: []
    fake.createNode = lambda *a, **k: _Node()

    sys.modules["nuke"] = fake
    yield fake
    sys.modules.pop("nuke", None)


# ---------------------------------------------------------------------------
# Media fixtures
# ---------------------------------------------------------------------------

def _make_png(path, color):
    from PIL import Image
    Image.new("RGB", (64, 64), color=color).save(path)
    return path


@pytest.fixture
def tiny_png(tmp_path):
    try:
        return _make_png(str(tmp_path / "frame.png"), (128, 64, 32))
    except ImportError:
        pytest.skip("Pillow not installed")


@pytest.fixture
def tiny_png_similar(tmp_path):
    try:
        return _make_png(str(tmp_path / "frame_similar.png"), (130, 66, 34))
    except ImportError:
        pytest.skip("Pillow not installed")


@pytest.fixture
def tiny_png_different(tmp_path):
    try:
        return _make_png(str(tmp_path / "frame_different.png"), (0, 200, 255))
    except ImportError:
        pytest.skip("Pillow not installed")


def _make_gif(path, colors):
    from PIL import Image
    frames = [Image.new("RGB", (64, 64), color=c) for c in colors]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return path


@pytest.fixture
def tiny_gif(tmp_path):
    """A real 2-frame animated GIF, for QMovie-rendering tests (EP3 quicklook)."""
    try:
        return _make_gif(str(tmp_path / "preview.gif"), [(200, 10, 10), (10, 200, 10)])
    except ImportError:
        pytest.skip("Pillow not installed")


@pytest.fixture
def tiny_sequence(tmp_path):
    """Create shot.0001.png .. shot.0004.png and return their paths, sorted."""
    try:
        paths = []
        for n in range(1, 5):
            p = str(tmp_path / "shot.{:04d}.png".format(n))
            _make_png(p, (10 * n, 20, 30))
            paths.append(p)
        return sorted(paths)
    except ImportError:
        pytest.skip("Pillow not installed")
