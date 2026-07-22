# SP0 — Test Harness & CI Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a clean, real-schema, headless-capable, gated test harness (3-tier: unit/gui/nuke) with GitHub Actions CI on Windows + Linux, so the remaining StaX audit sub-projects (SP1–SP8) can be implemented test-first.

**Architecture:** Restructure `tests/` into `unit/`, `gui/`, `nuke/`, and a non-collected `manual/`. Rewrite `conftest.py` so its DB fixture builds the **real** `DatabaseManager` on a temp database (retiring the fantasy-schema `FakeDB`). Qt widgets are tested headlessly via `pytest-qt` + `QT_QPA_PLATFORM=offscreen`; Nuke via `NukeBridge(mock_mode=True)` and an injected fake `nuke` module. A gating GitHub Actions workflow runs the suite on both OSes.

**Tech Stack:** Python 3.9, pytest, pytest-qt, pytest-mock, pytest-cov, Flask (for API tests), PySide2 (offscreen), GitHub Actions, uv.

## Global Constraints

- **Platforms:** Windows + Linux only (no macOS). CI matrix = `windows-latest`, `ubuntu-latest`.
- **Python:** 3.9 (matches `.python-version` / `requires-python >=3.9`).
- **No product-bug fixes in SP0.** Known-broken paths (C1) are documented via `@pytest.mark.xfail(strict=True)`, never fixed here.
- **The DB fixture must exercise the real `DatabaseManager`**, whose live schema uses lowercase tables (`stacks`, `lists`, `elements`, `ingestion_history`) — NOT the capitalized `Stacks`/`Elements`/`InsertionLog` of the orphaned `db_manager_additions.py`.
- **CI gate = pass/fail.** Coverage is reported, not percentage-gated.
- **Import convention:** `src/` is added to `sys.path`, so modules are imported flat (`from db_manager import ...`), matching how StaX's own modules import their siblings.

---

## Key signatures (verified against the codebase)

- `DatabaseManager(db_path, enable_logging=False, use_file_lock=True)` — auto-creates schema when the DB file does not exist (`src/db_manager.py:22`).
- `Config(config_path='./config/config.json')`; `.get(key, default=None)`, `.get_all()`; honors `STOCK_DB` env (`src/config.py:87`).
- `SequenceDetector.detect_sequence(filepath, pattern_key=None, auto_detect=True)` classmethod → dict with keys `base_name, frame_pattern, ffmpeg_pattern, files, frame_range, first_frame, last_frame, start_frame, padding, extension, separator, pattern_key, frame_count`, or `None` if ≤1 file (`src/ingestion_core.py:52`). `SequenceDetector.get_sequence_path(sequence_info)` → path string.
- `PreviewCache(max_size=200, max_memory_mb=100)`; `.get(fp)`, `.put(fp, pixmap)`, `.clear()`; `.cache_stats` = `{hits, misses, evictions, total_requests}` (`src/preview_cache.py:12`). `put/get` store arbitrary objects — no Qt needed.
- `FileLockManager(lock_file_path, timeout=30.0, retry_delay=0.1, max_retries=100)`; `.acquire()` → `True`/raises `TimeoutError`; `.release()`; `.is_locked` bool (`src/file_lock.py:34`).
- `NukeBridge(mock_mode=True)`; `.create_read_node(filepath, frame_range=None, node_name=None)` → dict in mock mode (`src/nuke_bridge.py:31`).
- `_build_flask_app(db, config)` → Flask app with routes under `/api/v1/*` (`src/api_server.py:76`).
- `MainWindow(config=None)` (`main.py:83`); `BatchEditDialog(element_ids, db, parent=None)` (`src/ui/batch_edit_dialog.py:96`).

---

## Task 1: Restructure the `tests/` tree

**Files:**
- Create dirs: `tests/unit/`, `tests/gui/`, `tests/nuke/`, `tests/manual/`
- Delete: `tests/gui_main_backup.py`, `tests/Ulaavi/`, `tests/glb_converter/`
- Move → `tests/manual/`: `ffplay_test.py`, `ffpyplayer_imageSequence.py`, `seq2gif.py`, `run_detect.py`, `glb_viewer.py`, `verify_features.py`, `example_usage.py`, `ffmpeg_downloader.py`

**Interfaces:**
- Produces: the tier directory layout every later task writes into.

- [ ] **Step 1: Create tier directories with package markers**

```bash
cd "d:/Scripts/modern-stock-browser"
mkdir -p tests/unit tests/gui tests/nuke tests/manual
touch tests/unit/__init__.py tests/gui/__init__.py tests/nuke/__init__.py
```

- [ ] **Step 2: Delete junk (backup + vendored trees)**

```bash
git rm -r --force tests/gui_main_backup.py tests/Ulaavi tests/glb_converter
```

- [ ] **Step 3: Archive scratch scripts into `tests/manual/`**

```bash
git mv tests/ffplay_test.py tests/manual/
git mv tests/ffpyplayer_imageSequence.py tests/manual/
git mv tests/seq2gif.py tests/manual/
git mv tests/run_detect.py tests/manual/
git mv tests/glb_viewer.py tests/manual/
git mv tests/verify_features.py tests/manual/
git mv tests/example_usage.py tests/manual/
git mv tests/ffmpeg_downloader.py tests/manual/
```

- [ ] **Step 4: Archive the legacy `test_*` scripts that only run interactively**

These are `__main__` GUI/DB scripts or fantasy-schema tests; move them to `manual/` so pytest stops collecting them. (Real replacements are written in Tasks 5–8.)

```bash
git mv tests/test_nuke_launcher.py tests/manual/
git mv tests/test_network_sqlite.py tests/manual/
git mv tests/test_ingest_library_sequences.py tests/manual/
git mv tests/test_features_2_to_6.py tests/manual/
git mv tests/test_feature1_preview_worker.py tests/manual/
git mv tests/test_gif_generation.py tests/manual/
git mv tests/test_gif_startframe.py tests/manual/
git mv tests/test_frame_count_display.py tests/manual/
git mv tests/test_ffmpeg_padding.py tests/manual/
git mv tests/test_sequence_detection.py tests/manual/
git mv tests/test_sequence_detection_simple.py tests/manual/
git mv tests/test_sequence_pattern_selection.py tests/manual/
```

- [ ] **Step 5: Verify the tree**

Run:
```bash
ls tests && echo "---manual---" && ls tests/manual
```
Expected: `tests/` shows `conftest.py`, `unit/`, `gui/`, `nuke/`, `manual/` and no stray `test_*.py` or `.py` scratch scripts at the top level; `tests/manual/` holds the archived files.

- [ ] **Step 6: Commit**

```bash
git add -A tests/
git commit -m "test: restructure tests/ into unit/gui/nuke tiers, archive scratch scripts"
```

---

## Task 2: Add dev dependencies

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `pytest`, `pytest-qt`, `pytest-mock`, `pytest-cov`, `flask` importable for all later tasks.

- [ ] **Step 1: Add a `dev` optional-dependencies group**

Add to `pyproject.toml` (under `[project]`, create the table if absent):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7",
    "pytest-qt",
    "pytest-mock",
    "pytest-cov",
    "flask",
]
```

- [ ] **Step 2: Install the dev group into the venv**

Run:
```bash
uv pip install -e ".[dev]"
```
Expected: installs pytest-qt, pytest-mock, pytest-cov, flask without error.

- [ ] **Step 3: Verify pytest-qt is available**

Run:
```bash
python -c "import pytestqt, flask; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add dev test dependencies (pytest-qt/mock/cov, flask)"
```

---

## Task 3: Rewrite `conftest.py` around the real DatabaseManager

**Files:**
- Modify (replace): `tests/conftest.py`
- Test: `tests/unit/test_conftest_fixtures.py` (new)

**Interfaces:**
- Produces fixtures used by all later tasks:
  - `stax_db` → a real `DatabaseManager` on a temp DB (`use_file_lock=False`).
  - `stax_config` → a real `Config` pointed at a temp `config.json`.
  - `mock_nuke` → injects a fake `nuke` module into `sys.modules`; yields it.
  - `tiny_png`, `tiny_png_similar`, `tiny_png_different` (retained), `tiny_sequence` (new: list of numbered PNG paths).
  - Qt is headless (`QT_QPA_PLATFORM=offscreen`); `qtbot`/`qapp` come from `pytest-qt`.

- [ ] **Step 1: Write the failing fixture test**

Create `tests/unit/test_conftest_fixtures.py`:

```python
import os


def test_stax_db_uses_real_lowercase_schema(stax_db):
    """The DB fixture must build the LIVE DatabaseManager schema (lowercase tables),
    not the orphaned capitalized 'Elements'/'InsertionLog' schema."""
    with stax_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert "elements" in names
    assert "stacks" in names
    assert "lists" in names
    # The fantasy schema's capitalized tables must NOT be present
    assert "Elements" not in names
    assert "InsertionLog" not in names


def test_tiny_sequence_returns_multiple_frames(tiny_sequence):
    assert len(tiny_sequence) >= 3
    for p in tiny_sequence:
        assert os.path.isfile(p)


def test_mock_nuke_is_importable(mock_nuke):
    import sys
    assert "nuke" in sys.modules
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_conftest_fixtures.py -v`
Expected: FAIL / ERROR — fixtures `stax_db`, `tiny_sequence`, `mock_nuke` do not exist yet.

- [ ] **Step 3: Replace `tests/conftest.py`**

Replace the entire file with:

```python
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
```

- [ ] **Step 4: Run the fixture test to verify it passes**

Run: `pytest tests/unit/test_conftest_fixtures.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/unit/test_conftest_fixtures.py
git commit -m "test: rewrite conftest around real DatabaseManager, add headless Qt + mock-nuke fixtures"
```

---

## Task 4: Update `pytest.ini`

**Files:**
- Modify: `pytest.ini`

**Interfaces:**
- Produces: `testpaths` scoped to the three tiers; registered markers `unit/gui/nuke/ffmpeg/slow/manual`; `--strict-markers`.

- [ ] **Step 1: Replace `pytest.ini`**

```ini
[pytest]
testpaths        = tests/unit tests/gui tests/nuke
python_files     = test_*.py
python_classes   = Test*
python_functions = test_*
addopts          = -v --tb=short --strict-markers
markers =
    unit: pure-logic tests, no Qt or Nuke
    gui: requires headless Qt (QT_QPA_PLATFORM=offscreen)
    nuke: uses mocked nuke module / NukeBridge(mock_mode=True)
    ffmpeg: requires ffmpeg binaries (skipped if absent)
    slow: long-running
    manual: never run in CI (archived scripts)
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

- [ ] **Step 2: Verify markers are registered and collection is clean**

Run: `pytest --collect-only`
Expected: collects only `tests/unit/test_conftest_fixtures.py` so far; no errors; `tests/manual/` not collected.

- [ ] **Step 3: Commit**

```bash
git add pytest.ini
git commit -m "test: scope pytest testpaths to tiers and register strict markers"
```

---

## Task 5: Characterization tests — SequenceDetector & Config (unit tier)

**Files:**
- Create: `tests/unit/test_sequence_detector.py`, `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `tiny_sequence`, `stax_config` fixtures; `SequenceDetector` (`from ingestion_core import SequenceDetector`); `Config`.

- [ ] **Step 1: Write the SequenceDetector characterization test**

Create `tests/unit/test_sequence_detector.py`:

```python
import os
import pytest

from ingestion_core import SequenceDetector


@pytest.mark.unit
def test_detects_dot_padded_sequence(tiny_sequence):
    info = SequenceDetector.detect_sequence(tiny_sequence[0])
    assert info is not None
    assert info["frame_count"] == 4
    assert info["first_frame"] == 1
    assert info["last_frame"] == 4
    assert info["frame_range"] == "1-4"
    assert info["padding"] == 4
    assert info["ffmpeg_pattern"] == "shot.%04d.png"


@pytest.mark.unit
def test_single_file_is_not_a_sequence(tmp_path):
    from PIL import Image
    lone = str(tmp_path / "single.0001.png")
    Image.new("RGB", (8, 8), (0, 0, 0)).save(lone)
    assert SequenceDetector.detect_sequence(lone) is None


@pytest.mark.unit
def test_get_sequence_path_builds_printf_pattern(tiny_sequence):
    info = SequenceDetector.detect_sequence(tiny_sequence[0])
    seq_path = SequenceDetector.get_sequence_path(info)
    assert seq_path.endswith("shot.%04d.png")
    assert os.path.dirname(seq_path) == os.path.dirname(tiny_sequence[0])
```

- [ ] **Step 2: Run it**

Run: `pytest tests/unit/test_sequence_detector.py -v`
Expected: PASS (3 passed). If a key assertion fails, it means the detector's current behavior differs from the design's description — STOP and report; do not "fix" the detector (that is not SP0's job).

- [ ] **Step 3: Write the Config characterization test**

Create `tests/unit/test_config.py`:

```python
import pytest

from config import Config


@pytest.mark.unit
def test_defaults_present_and_get_all_is_a_copy(stax_config):
    all_cfg = stax_config.get_all()
    assert isinstance(all_cfg, dict)
    # mutating the returned dict must not affect the Config
    all_cfg["__scratch__"] = 1
    assert stax_config.get("__scratch__") is None


@pytest.mark.unit
def test_stock_db_env_override(tmp_path, monkeypatch):
    db = str(tmp_path / "shared.db")
    monkeypatch.setenv("STOCK_DB", db)
    cfg = Config(config_path=str(tmp_path / "config.json"))
    assert cfg.get("database_path") == db
```

- [ ] **Step 4: Run it**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_sequence_detector.py tests/unit/test_config.py
git commit -m "test: characterization tests for SequenceDetector and Config"
```

---

## Task 6: Characterization tests — PreviewCache & FileLockManager (unit tier)

**Files:**
- Create: `tests/unit/test_preview_cache.py`, `tests/unit/test_file_lock.py`

**Interfaces:**
- Consumes: `PreviewCache` (`from preview_cache import PreviewCache`), `FileLockManager` (`from file_lock import FileLockManager`).

- [ ] **Step 1: Write the PreviewCache characterization test**

Create `tests/unit/test_preview_cache.py`:

```python
import pytest

from preview_cache import PreviewCache


@pytest.mark.unit
def test_lru_hit_miss_and_eviction():
    cache = PreviewCache(max_size=2)
    # put/get store arbitrary objects; use sentinels (no Qt needed)
    cache.put("a", object())
    cache.put("b", object())
    assert cache.get("a") is not None          # hit, marks 'a' most-recent
    assert cache.get("missing") is None        # miss
    cache.put("c", object())                    # exceeds max_size -> evict LRU ('b')
    assert cache.get("b") is None               # 'b' evicted
    assert cache.get("a") is not None           # 'a' survived
    assert cache.cache_stats["evictions"] == 1
    assert cache.cache_stats["hits"] >= 2
    assert cache.cache_stats["misses"] >= 2


@pytest.mark.unit
def test_clear_resets_stats():
    cache = PreviewCache(max_size=4)
    cache.put("a", object())
    cache.get("a")
    cache.clear()
    assert cache.get("a") is None
    assert cache.cache_stats["evictions"] == 0
```

- [ ] **Step 2: Run it**

Run: `pytest tests/unit/test_preview_cache.py -v`
Expected: PASS (2 passed).

- [ ] **Step 3: Write the FileLockManager characterization test**

Create `tests/unit/test_file_lock.py`:

```python
import pytest

from file_lock import FileLockManager


@pytest.mark.unit
def test_acquire_and_release_toggles_state(tmp_path):
    lock = FileLockManager(str(tmp_path / "res.lock"))
    assert lock.is_locked is False
    assert lock.acquire() is True
    assert lock.is_locked is True
    lock.release()
    assert lock.is_locked is False
```

- [ ] **Step 4: Run it**

Run: `pytest tests/unit/test_file_lock.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_preview_cache.py tests/unit/test_file_lock.py
git commit -m "test: characterization tests for PreviewCache and FileLockManager"
```

---

## Task 7: Nuke-tier smoke — NukeBridge mock mode

**Files:**
- Create: `tests/nuke/test_nuke_bridge_mock.py`

**Interfaces:**
- Consumes: `NukeBridge` (`from nuke_bridge import NukeBridge`).

- [ ] **Step 1: Write the mock-mode test**

Create `tests/nuke/test_nuke_bridge_mock.py`:

```python
import pytest

from nuke_bridge import NukeBridge


@pytest.mark.nuke
def test_mock_bridge_defaults_to_mock_mode():
    bridge = NukeBridge(mock_mode=True)
    assert bridge.mock_mode is True


@pytest.mark.nuke
def test_mock_create_read_node_returns_dict():
    bridge = NukeBridge(mock_mode=True)
    result = bridge.create_read_node("/tmp/plate.%04d.exr", frame_range="1-10")
    assert isinstance(result, dict)
```

- [ ] **Step 2: Run it**

Run: `pytest tests/nuke/test_nuke_bridge_mock.py -v`
Expected: PASS (2 passed). If `create_read_node`'s mock branch returns a non-dict, relax the assertion to `assert result is not None` and note it in the commit — do not change `nuke_bridge.py`.

- [ ] **Step 3: Commit**

```bash
git add tests/nuke/test_nuke_bridge_mock.py
git commit -m "test: nuke-tier smoke test for NukeBridge mock mode"
```

---

## Task 8: GUI-tier smoke tests (xfail for C1)

**Files:**
- Create: `tests/gui/test_api_smoke.py`, `tests/gui/test_mainwindow_smoke.py`, `tests/gui/test_batch_edit_smoke.py`

**Interfaces:**
- Consumes: `stax_db`, `stax_config`, `mock_nuke`, `qtbot`; `_build_flask_app` (`from api_server import _build_flask_app`); `MainWindow` (`from main import MainWindow`); `BatchEditDialog` (`from ui.batch_edit_dialog import BatchEditDialog`).

- [ ] **Step 1: Write the API smoke test (the C1 detector)**

Create `tests/gui/test_api_smoke.py`:

```python
import pytest

from api_server import _build_flask_app


def _client(stax_db, stax_config):
    stax_config.set("api_token", "test-token")
    app = _build_flask_app(stax_db, stax_config)
    app.testing = True
    return app.test_client()


@pytest.mark.gui
def test_health_endpoint_ok(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.gui
@pytest.mark.xfail(reason="C1: analytics endpoint calls DB methods missing until SP1",
                   strict=True)
def test_analytics_top_endpoint_no_server_error(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/analytics/top?n=5",
                      headers={"X-StaX-Token": "test-token"})
    assert resp.status_code != 500
```

Rationale: `/api/v1/analytics/top` calls `get_top_inserted_elements`, which does not exist on the live `DatabaseManager` (issue C1), so it 500s today. `strict=True` means SP1 flips it to a real pass and any accidental early pass fails loudly.

- [ ] **Step 2: Run it**

Run: `pytest tests/gui/test_api_smoke.py -v`
Expected: `test_health_endpoint_ok` PASS; `test_analytics_top_endpoint_no_server_error` XFAIL. (If Flask is missing, install per Task 2.)

- [ ] **Step 3: Write the MainWindow smoke test**

Create `tests/gui/test_mainwindow_smoke.py`:

```python
import pytest


@pytest.mark.gui
def test_mainwindow_constructs(qtbot, stax_config, mock_nuke, monkeypatch, tmp_path):
    # Point the app's DB at the temp location via STOCK_DB so no shared file is touched.
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from main import MainWindow

    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)
    assert win is not None
```

- [ ] **Step 4: Run it**

Run: `pytest tests/gui/test_mainwindow_smoke.py -v`
Expected: PASS. If `MainWindow.__init__` raises due to an unfixed defect (e.g. it eagerly calls a missing DB method), convert this test to `@pytest.mark.xfail(reason="<issue id>", strict=True)` and record which issue in the commit message — do not fix the defect here.

- [ ] **Step 5: Write the BatchEditDialog smoke test**

Create `tests/gui/test_batch_edit_smoke.py`:

```python
import pytest

from ui.batch_edit_dialog import BatchEditDialog


@pytest.mark.gui
@pytest.mark.xfail(reason="C1: batch edit calls update_element_metadata, missing until SP1",
                   strict=True)
def test_batch_edit_apply_resolves_db_method(qtbot, stax_db):
    # Seed one stack/list/element via the real DB, then attempt an apply.
    stack_id = stax_db.create_stack("S", "/tmp/S") if hasattr(stax_db, "create_stack") else None
    dlg = BatchEditDialog([1], stax_db)
    qtbot.addWidget(dlg)
    # The dialog constructs fine; the C1 failure is that its apply path calls
    # db.update_element_metadata which does not exist on the live DatabaseManager.
    assert hasattr(stax_db, "update_element_metadata")
```

- [ ] **Step 6: Run it**

Run: `pytest tests/gui/test_batch_edit_smoke.py -v`
Expected: XFAIL (the live `DatabaseManager` lacks `update_element_metadata`). SP1 adds the method and flips this to pass.

- [ ] **Step 7: Run the full suite**

Run: `pytest -m "not manual"`
Expected: all `unit`/`nuke`/`gui` tests pass or xfail; **0 failed, 0 errored**. Note the xfail count.

- [ ] **Step 8: Commit**

```bash
git add tests/gui/
git commit -m "test: gui-tier smoke tests (MainWindow, API, BatchEdit) with strict xfail for C1"
```

---

## Task 9: GitHub Actions CI + branch protection

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: a gating `CI` check on `windows-latest` + `ubuntu-latest`.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    name: test (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    env:
      QT_QPA_PLATFORM: offscreen
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"

      - name: Install uv
        run: pip install uv

      - name: Install Linux Qt runtime libs
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libegl1 libgl1

      - name: Install project (dev extras)
        run: uv pip install --system -e ".[dev]"

      - name: Run tests
        run: pytest -m "not manual" --cov=src --cov-report=term-missing
```

- [ ] **Step 2: Validate the YAML locally**

Run:
```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"
```
Expected: prints `yaml ok`. (If PyYAML isn't installed, `uv pip install pyyaml` first, or skip — GitHub will validate on push.)

- [ ] **Step 3: Commit and push to trigger the first run**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add gating pytest workflow on Windows + Linux"
git push
```

- [ ] **Step 4: Confirm the workflow passes**

Run:
```bash
gh run list --limit 1
```
Then watch the latest run:
```bash
gh run watch
```
Expected: both matrix jobs conclude `success`. If a job fails, read the log (`gh run view --log-failed`) and fix the workflow (missing system lib, PySide2 wheel, etc.) — do not disable tests to make it pass.

- [ ] **Step 5: Enable branch protection (requires repo admin)**

This is a one-time GitHub settings change, not code. Run (admin token required):
```bash
gh api -X PUT repos/aramadan0096/Stax/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[checks][][context]=test (ubuntu-latest)" \
  -f "required_status_checks[checks][][context]=test (windows-latest)" \
  -F "enforce_admins=false" \
  -F "required_pull_request_reviews=null" \
  -F "restrictions=null"
```
Expected: returns the protection JSON. If you lack admin rights or a token, record this as a manual follow-up: *"Settings → Branches → add rule for `main` requiring the `test (ubuntu-latest)` and `test (windows-latest)` checks."*

---

## Self-Review

**1. Spec coverage:**
- Cleaned 3-tier tree + archival → Task 1 ✓
- Rewritten conftest on real DatabaseManager → Task 3 ✓
- Headless Qt + mock-nuke fixtures → Task 3 ✓
- `pytest.ini` testpaths + markers → Task 4 ✓
- Gating CI on Win+Linux (Py3.9) → Task 9 ✓
- `pyproject.toml` dev extra → Task 2 ✓
- Smoke tests with strict xfail for C1 → Task 8 ✓
- Characterization tests (SequenceDetector, PreviewCache, Config, FileLockManager) → Tasks 5–6 ✓
- ffmpeg tests skip when absent → no ffmpeg test is written in SP0 (marker registered in Task 4 for later SPs); no gap.
- Branch protection → Task 9 Step 5 ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every code step shows complete code. Fallback instructions (e.g. relax an assertion) specify the exact alternative and forbid fixing product code.

**3. Type consistency:** Fixture names (`stax_db`, `stax_config`, `mock_nuke`, `tiny_sequence`) are defined in Task 3 and consumed with the same names in Tasks 5–8. Signatures (`DatabaseManager(db_path, ...)`, `_build_flask_app(db, config)`, `BatchEditDialog(element_ids, db, parent=None)`, `NukeBridge(mock_mode=True)`, `SequenceDetector.detect_sequence(...)`) match the verified codebase signatures section. `cache_stats` keys (`hits/misses/evictions/total_requests`) match `src/preview_cache.py`.

---

## Notes for the executor
- **Never fix a product bug to make a test pass.** SP0's job is the harness. If a smoke test reveals an unfixed defect, mark it `xfail(strict=True)` with the issue id and move on — the owning sub-project (SP1+) will flip it green.
- Run `pytest -m "not manual"` before every commit that touches tests.
- If a legacy assertion in Tasks 5–7 disagrees with the codebase's *current* behavior, the codebase wins — adjust the characterization test to describe reality (that is its purpose), and note the surprise.
