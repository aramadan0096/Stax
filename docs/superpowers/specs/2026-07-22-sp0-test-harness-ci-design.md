# SP0 — Test Harness & CI Foundation — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). This is the first sub-project and a prerequisite for the rest: it establishes the safety net that makes SP1–SP8 test-driven.

---

## 1. Background & Motivation

The StaX audit (`STAX_AUDIT_REPORT.md`) found automated test coverage of the risky surface to be essentially zero, and surfaced two structural test problems:

1. **No CI exists.** `.github/` contains only issue templates. Regressions are caught by nothing.
2. **The existing `tests/conftest.py` validates a fantasy schema.** Its `FakeDB` and `_BASELINE_SCHEMA` use the *capitalized* tables (`Stacks`, `Elements`, `InsertionLog`) from the **orphaned** `db_manager_additions.py` layer — not the live `DatabaseManager`, which uses lowercase `stacks`/`elements`/`ingestion_history`. The current tests therefore exercise code that does not run in production.

Additionally, `tests/` is polluted with non-test scratch scripts (`gui_main_backup.py` ~190 KB, vendored `Ulaavi/` and `glb_converter/` trees, manual ffplay/glb/seq scripts), so `testpaths` is noisy and several "test_" files are manual `__main__` harnesses that assert nothing.

SP0 fixes the **infrastructure**, not the product bugs. It delivers a clean, real-schema, headless-capable, gated test harness so every later sub-project (SP1–SP8) can be implemented test-first.

### Program context (decisions already made)
- **Wire, don't remove:** the half-wired features (async preview worker, analytics, REST API, duplicate detection, batch-edit) will be *finished*, not deleted (drives SP1/SP2). SP0 must therefore be able to exercise those code paths.
- **Target platforms:** Windows + Linux (no macOS). CI runs on both.

---

## 2. Goals / Non-Goals

### Goals
- A cleaned `tests/` tree with a 3-tier layout (unit / gui / nuke) and archived scratch scripts.
- A rewritten `conftest.py` whose DB fixture builds the **real `DatabaseManager`** on a temp database.
- Headless Qt testing via `pytest-qt` + `QT_QPA_PLATFORM=offscreen`.
- Nuke testing via `NukeBridge(mock_mode=True)` and an injected fake `nuke` module.
- A **gating** GitHub Actions workflow on Windows + Linux (Python 3.9) that blocks merges to `main` on failure.
- A small set of smoke + characterization tests, including a `MainWindow`+API smoke test that red-flags C1.

### Non-Goals (explicitly deferred)
- Fixing any product bug (C1, C4, etc.) — those are SP1+. SP0 only *documents* known-broken paths via `xfail`.
- Exhaustive per-module test suites — each later SP adds its own feature tests TDD-style.
- Nuke real-mode (licensed) testing; macOS support.
- A hard code-coverage percentage gate (coverage is reported, not enforced, initially).

---

## 3. Approach

Chosen approach: **Minimal foundation + smoke/characterization tests.** Build the harness, CI, and cleanup; write only (a) characterization tests that lock current *correct* behavior of stable modules so SP8 refactors can't regress them, and (b) smoke tests that red-flag the known crashers as `xfail`. Later SPs write their own feature tests.

Rejected alternatives:
- *Foundation + broad baseline suite now* — slow, and risks locking in buggy behavior before SP1–SP6 fix it.
- *Fold the conftest rewrite into SP1* — strands SP0 with no way to validate anything.

---

## 4. Detailed Design

### 4.1 Test tree layout

```
tests/
  conftest.py          # rewritten: real DatabaseManager + headless Qt + mock-nuke fixtures
  unit/                # Tier 1 — pure logic, no Qt   (db, ingestion, sequence, config, file_lock, preview_cache)
  gui/                 # Tier 2 — pytest-qt + QT_QPA_PLATFORM=offscreen
  nuke/                # Tier 3 — NukeBridge(mock_mode=True) / injected fake `nuke` module
  manual/              # archived scratch scripts — NOT collected by pytest
```

**File disposition:**

| Action | Files |
|---|---|
| **Delete** (true junk / vendored / backup) | `tests/gui_main_backup.py`, `tests/Ulaavi/`, `tests/glb_converter/` |
| **Archive → `tests/manual/`** (keep, not collected) | `ffplay_test.py`, `ffpyplayer_imageSequence.py`, `seq2gif.py`, `run_detect.py`, `glb_viewer.py`, `verify_features.py`, `example_usage.py`, duplicate `ffmpeg_downloader.py` |
| **Rewrite & relocate → `unit/`** | `test_sequence_detection.py`, `test_sequence_detection_simple.py`, `test_sequence_pattern_selection.py`, `test_ffmpeg_padding.py`, `test_frame_count_display.py` |
| **Rewrite headless or archive** | `test_nuke_launcher.py` (manual GUI `sys.exit`), `test_network_sqlite.py` (no `test_` funcs), `test_ingest_library_sequences.py` (real QApplication), `test_features_2_to_6.py`, `test_feature1_preview_worker.py`, `test_gif_generation.py`, `test_gif_startframe.py` — keep the assertions that target real code; move to the correct tier; archive anything that only runs interactively. |

### 4.2 `pytest.ini`

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
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

`manual/` is excluded from `testpaths`, so archived scripts are never collected. `--strict-markers` prevents typo'd markers.

### 4.3 Fixtures (`conftest.py`, rewritten)

- **`stax_db`** — constructs the real `DatabaseManager` pointed at `tmp_path/stax_test.db`, running its actual `_create_schema` + `_apply_migrations`. Validates the *production* schema and honestly exposes C1's gaps. Yields the manager; tears down the file. Replaces the fantasy-schema `FakeDB`.
- **`qapp` / `qtbot`** — provided by `pytest-qt`; `QT_QPA_PLATFORM=offscreen` is set (in `conftest.py` at import time as a fallback, and in CI env) so widgets construct without a display.
- **`mock_nuke`** — inserts a minimal fake `nuke` module into `sys.modules` (nodes, `pluginAddPath`, `nodePaste`, etc. as no-op stubs) so nuke-facing imports succeed; pairs with `NukeBridge(mock_mode=True)`.
- **Media fixtures** — retain `tiny_png`, `tiny_png_similar`, `tiny_png_different`; add `tiny_sequence` (a handful of zero-padded numbered PNGs in a temp dir) for sequence-detection and preview tests.
- **`sys.path`** — keep the existing repo-root insertion so `src` imports resolve.

### 4.4 CI workflow (`.github/workflows/ci.yml`)

- **Triggers:** `push` and `pull_request`.
- **Matrix:** `os: [windows-latest, ubuntu-latest]` × `python-version: ["3.9"]` (matches `.python-version` / `requires-python >=3.9`).
- **Steps:**
  1. `actions/checkout` (with submodules if needed).
  2. `actions/setup-python`.
  3. Install `uv`; install project + a new **`dev` extra** (`pytest`, `pytest-qt`, `pytest-mock`, `pytest-cov`).
  4. On Linux: `apt-get install -y libegl1 libgl1` for offscreen Qt.
  5. Run `pytest -m "not manual"` with `QT_QPA_PLATFORM=offscreen` (and `pytest-cov` reporting).
- **ffmpeg:** tests marked `ffmpeg` **skip gracefully** when binaries are absent (availability check), so CI need not bundle ffmpeg.
- **Coverage:** reported (job summary/artifact), **not** hard-gated on a percentage. The gate is pass/fail.
- **Branch protection:** `main` requires this CI check to pass before merge.

### 4.5 `pyproject.toml` change

Add a dev dependency group/extra:

```toml
[project.optional-dependencies]
dev = ["pytest>=7", "pytest-qt", "pytest-mock", "pytest-cov"]
```

(Or the equivalent `[dependency-groups]` if staying on uv's grouping — implementation plan decides the exact table.)

### 4.6 Smoke & characterization tests

**Smoke (Tier 2 — catch the known crashers, marked `xfail` until the owning SP fixes them):**
- `gui/test_mainwindow_smoke.py::test_mainwindow_instantiates` — offscreen + `mock_nuke` + `stax_db`: construct `MainWindow`, assert no exception.
- `gui/test_api_smoke.py::test_all_endpoints_respond` — start `APIServer` on the temp DB, hit every endpoint, assert no 500 / `AttributeError`. **This is the C1 detector.**
- `gui/test_batch_edit_smoke.py::test_dialog_opens` — construct `BatchEditDialog`, assert its DB calls resolve.
- Known-broken assertions use `@pytest.mark.xfail(reason="C1 — fixed in SP1", strict=True)` so **CI is green today** and SP1 flips them to passing (strict xfail flags an accidental early xpass).

**Characterization (Tier 1 — lock current correct behavior; guard SP8 refactors):**
- `unit/test_sequence_detection.py` — `SequenceDetector` across the four frame patterns, padding, frame-range.
- `unit/test_preview_cache.py` — `PreviewCache` LRU insert/evict/hit-miss stats.
- `unit/test_config.py` — `Config` default merge, `STOCK_DB` env override, relative→absolute path resolution.
- `unit/test_file_lock.py` — `FileLockManager` basic acquire/release (single-process).

---

## 5. Testing Strategy for SP0 itself

SP0 *is* testing infrastructure, so "testing SP0" means: the workflow runs green on both OSes, the smoke tests correctly `xfail` (not error), the characterization tests pass, and `pytest -m "not manual"` collects only the three tiers. A deliberately-introduced schema mismatch in a scratch branch should make `stax_db`-based tests fail (proving the fixture exercises the real schema).

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Offscreen Qt flaky on Linux CI | Install `libegl1`/`libgl1`; pin `QT_QPA_PLATFORM=offscreen`; keep GUI tests to construction-smoke, not pixel assertions. |
| `stax_db` reveals so many failures it blocks CI | Known-broken paths are `xfail`, not asserted-pass; only stable modules are asserted green in SP0. |
| PySide2 wheels unavailable for 3.9 on a runner | Verify PySide2 install in the first CI run; fall back to a documented pinned version. |
| Rewriting legacy tests balloons scope | Archive-first: anything not trivially convertible goes to `manual/`; real conversions are limited to the stable-module characterization set. |

---

## 7. Deliverables Checklist
- [ ] `tests/` restructured into `unit/`, `gui/`, `nuke/`, `manual/`; junk deleted, scratch archived.
- [ ] `conftest.py` rewritten around the real `DatabaseManager`, headless Qt, and mock-nuke.
- [ ] `pytest.ini` updated (testpaths, markers, strict-markers).
- [ ] `pyproject.toml` `dev` extra added.
- [ ] `.github/workflows/ci.yml` gating on Windows + Linux.
- [ ] Smoke tests (`xfail` for C1's missing-method crashes) + characterization tests for stable modules.
- [ ] Branch protection on `main` requiring CI.

---

## 8. Follow-on
SP1 (Database consolidation & concurrency) is the natural next sub-project: it makes the C1 `xfail` smoke tests pass and builds on `stax_db`. The remaining sub-projects (SP2–SP8) each add their own feature tests on this harness.
