# SP5 — Nuke integration & embedded-mode correctness — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). SP5 is the sixth sub-project. It depends on SP0's test harness (the `stax_db`, `stax_config`, `mock_nuke` fixtures and the 3-tier `unit`/`gui`/`nuke` layout) and is otherwise independent of SP1–SP4.

---

## 1. Background & Motivation

StaX runs in two modes: a standalone `QApplication` app and an embedded dockable panel inside Foundry Nuke. The audit (`STAX_AUDIT_REPORT.md`) found that the **embedded path is broken in ways that only manifest inside Nuke**, so the automated suite never caught them and the standalone path masked them. SP5 fixes the five issues that make StaX misbehave (or crash, or silence the host) specifically when hosted in Nuke, plus the interpreter-version debt that makes the host integration lie about what it supports.

The five issues:

- **H5 — In-Nuke menu commands call methods on the wrong object.** `menu.py` builds three commands (`Quick Ingest…`, `Register Toolset…`, `Advanced Search…`) as `panel = nuke_launcher.show_stax_panel(); panel.ingest_files()` (and `.register_toolset()`, `.show_advanced_search()`). But in Nuke mode `show_stax_panel()` returns the result of `nukescripts.panels.registerWidgetAsPanel(...).addToPane()` — a Nuke pane object, **not** a `StaXPanel`. It has no `ingest_files` / `register_toolset` / `show_advanced_search`, so each command raises `AttributeError`, and every invocation also registers and docks a **second** panel.
- **H8 — Global stdout/stderr hijack suppresses unrelated output inside Nuke.** `src/debug_manager.py` replaces `sys.stdout` and `sys.stderr` process-wide at import (triggered from both `menu.py` and `nuke_launcher.py`). When `debug_mode` is false, `_DebugStream.write` **drops every write** — not just StaX's — silencing Nuke's own console and every other tool's tracebacks for the whole session.
- **L1 — CWD-relative Nuke plugin paths.** `init.py` registers `'./tools'`, `'./src/ui'`, etc. via `nuke.pluginAddPath(subdir)`; if Nuke's working directory isn't the StaX root the imports silently fail. It also computes display paths with `subdir.lstrip('./')`, a character-set strip (not a prefix strip) that is semantically wrong.
- **L3 — Orphaned, stale `src/nuke_bridge_patch.py`.** An apply-by-hand skeleton that references `self.nuke_bridge` / `paste_toolset` methods that don't exist and documents an analytics hook never called by the real `insert_element`. Dead weight; delete.
- **L7 — Contradictory Python-2.7 claims + dead compat shims.** Many file headers claim "Python 2.7 compatible" while the app imports PySide2/Flask/numpy≥2/`secrets`/`shutil.which` (all Py3-only). Dead shims (`unicode = str`, an `isinstance(x, unicode)` branch, a `urllib2` fallback, a `TimeoutError` polyfill) remain. Under a Py2 Nuke these would `ImportError` and be silently swallowed. State a single interpreter (Python 3) and remove the shims.

### Program context (decisions already made)
- **Wire, don't remove** the half-wired features — except the *explicitly orphaned* file (L3's `src/nuke_bridge_patch.py`), which is deleted.
- **Target platforms:** Windows + Linux.
- **Testing:** hybrid 3-tier (unit / gui / nuke), headless; Nuke is always mocked (`NukeBridge(mock_mode=True)` + an injected fake `nuke` module). Never run real Nuke in CI.
- **Conventions:** flat imports (`from db_manager import ...`), `logging`/`stax_logger` over `print` in new code, TDD, frequent conventional commits.

---

## 2. Goals / Non-Goals

### Goals
- A single, module-level `StaXPanel` **singleton** in `nuke_launcher.py`, exposed via a `get_stax_panel()` accessor, so menu commands operate on the live widget and never spawn duplicate panels (H5).
- A `DebugManager` that scopes suppression to StaX's **own logger**, never swallows `stderr`, and **never replaces** `sys.stdout`/`sys.stderr` (H8).
- An `init.py` whose plugin-path assembly is a **pure, importable, absolute-path** function, unit-tested independently (L1).
- Deletion of `src/nuke_bridge_patch.py`, verified by a test asserting the file no longer exists (L3).
- A single-interpreter (Python 3) codebase: all "Python 2.7 compatible" claims and dead shims removed, enforced by a guard test that scans the tree for banned tokens (L7).

### Non-Goals (explicitly deferred)
- Fixing `NukeIntegration.insert_element`'s frame-range parsing (`split('-')`, issue L8) — that is SP6/SP8 scope, not SP5.
- Wiring an analytics insertion-logging hook into `insert_element` (the thing the orphaned `nuke_bridge_patch.py` *described*) — that belongs to SP1 (DB consolidation / analytics). SP5 deletes the stale skeleton only.
- The logging-location / rotation fix (M14) and the `print`→`logging` migration (L4) across the whole codebase — SP8. SP5 uses `logging`/`DebugManager.debug` only in the code it newly writes.
- Real-mode (licensed) Nuke testing; macOS.

---

## 3. Approach

Chosen approach: **surgical, test-first fixes to the embedded seams.** Each issue gets (a) a failing test in the appropriate tier that reproduces the embedded-mode defect against mocks, then (b) the minimal code change to make it pass. The singleton and the DebugManager keep their existing public entry points (`show_stax_panel`, `DebugManager.bootstrap_from_config` / `sync_from_config`) so callers in `menu.py`, `nuke_launcher.py`, and `main.py` don't churn — only their *behavior* is corrected.

Two small refactors are introduced purely to make the fixes testable without a running Nuke:
1. `get_stax_panel()` reads/writes a module-level singleton that `StaXPanel.__init__` populates — so whether the widget is created by our accessor or by Nuke's `registerWidgetAsPanel` machinery, the same live instance is returned.
2. `init.py`'s path logic becomes a pure `build_plugin_paths(stax_root)` function, and the module imports cleanly when `nuke` is absent (so `unit`-tier tests can import it).

Rejected alternatives:
- *Have `show_stax_panel()` return the `StaXPanel` even in Nuke mode* — impossible/fragile: in Nuke the widget is instantiated lazily by the pane machinery from the `'nuke_launcher.StaXPanel'` string, so we don't hold the handle at call time. The singleton-registered-from-`__init__` approach captures whichever instance Nuke actually built.
- *Keep DebugManager's stream proxy but only wrap `stdout`* — still risks swallowing host output on the shared `stdout` and still replaces an interpreter stream inside a host app. A logger-scoped design is cleaner and directly satisfies the audit directive.

---

## 4. Detailed Design

### 4.1 H5 — StaXPanel singleton + `get_stax_panel()` accessor

**In `nuke_launcher.py`:**

- Add a module-level `_STAX_PANEL_INSTANCE = None`.
- At the end of `StaXPanel.__init__`, register `self` as the singleton:
  ```python
  global _STAX_PANEL_INSTANCE
  _STAX_PANEL_INSTANCE = self
  ```
  This captures both construction paths: our own accessor, and Nuke's `registerWidgetAsPanel('nuke_launcher.StaXPanel', ...)` which instantiates the class by name when the pane is shown.
- Add the accessor:
  ```python
  def get_stax_panel():
      """Return the live StaXPanel singleton, creating one if none exists yet.

      Menu commands MUST call this rather than show_stax_panel(): in Nuke mode
      show_stax_panel() returns registerWidgetAsPanel(...).addToPane()'s result
      (a Nuke pane object), NOT a StaXPanel, so calling panel.ingest_files() on
      it raises AttributeError and docks a duplicate panel each time (H5).
      """
      global _STAX_PANEL_INSTANCE
      if _STAX_PANEL_INSTANCE is None:
          _STAX_PANEL_INSTANCE = StaXPanel()
      return _STAX_PANEL_INSTANCE
  ```

`show_stax_panel()` is unchanged in responsibility (it docks/shows the panel); it no longer needs to be the thing menu commands call for widget methods.

**In `menu.py`,** the three affected command strings change from
`'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.ingest_files()'`
to
`'import nuke_launcher; nuke_launcher.get_stax_panel().ingest_files()'`
(and likewise `.register_toolset()`, `.show_advanced_search()`). The `Open StaX Panel` command (which *docks* the panel) still calls `show_stax_panel()`.

**Result:** menu commands always hit a real `StaXPanel` (no `AttributeError`), and no duplicate panel is spawned.

### 4.2 H8 — Logger-scoped DebugManager (no stream hijack)

`src/debug_manager.py` is rewritten so that Debug Mode toggles the **verbosity of StaX's own logger** (`logging.getLogger("stax")`) between `DEBUG` and `WARNING`. It:
- **never** assigns to `sys.stdout` or `sys.stderr`;
- **never** swallows `stderr`;
- keeps its public surface — `initialize(enabled=True)`, `set_enabled(enabled)`, `is_enabled()`, `bootstrap_from_config(config_path=None)`, `sync_from_config(config)`, `restore_original_streams()` — so `menu.py`, `nuke_launcher.py`, and `main.py` (which call `bootstrap_from_config()` / `sync_from_config()`) are unaffected;
- adds `DebugManager.debug(message, *args)` for gated StaX output that routes through the logger instead of a hijacked stream (the correct replacement for the old gated `print`).

`_DebugStream` and the `restore_original_streams()` stream-swap are removed; `restore_original_streams()` becomes a back-compat reset that clears the initialized flag.

### 4.3 L1 — Pure, absolute plugin-path assembly in `init.py`

`init.py` gains a pure function:
```python
def build_plugin_paths(stax_root):
    root = os.path.abspath(stax_root)
    subdirs = ['tools', os.path.join('src', 'ui'), 'src', 'resources',
               os.path.join('dependencies', 'ffpyplayer')]
    paths = [root]
    for subdir in subdirs:
        paths.append(os.path.normpath(os.path.join(root, subdir)))
    return paths
```
Registration uses `nuke.pluginAddPath(path)` with those **absolute** paths (no `'./tools'`, no `lstrip('./')`). The module also imports cleanly when `nuke` is unavailable (guard: `try: import nuke as _nuke / except ImportError: _nuke = None`; run registration only when `_nuke is not None`), so the pure function can be imported and unit-tested without Nuke.

### 4.4 L3 — Delete `src/nuke_bridge_patch.py`

The file is an orphaned apply-by-hand skeleton (references nonexistent `paste_toolset`, documents an uncalled analytics hook). Delete it with `git rm`. A test asserts `os.path.exists(.../src/nuke_bridge_patch.py)` is `False`.

### 4.5 L7 — Single interpreter (Python 3); remove dead shims

Every "Python 2.7 compatible" claim and dead compat shim is removed. Enumerated targets (all `.py`; `changelog.md` is a historical record and is intentionally left, `.github/copilot-instructions.md` and `CLAUDE.md` already describe the removal):

| File | What changes |
|---|---|
| `main.py` (line 3) | Header "Python 2.7 / 3.x compatible" → "Python 3.9+". |
| `nuke_launcher.py` (line 5) | Header "Python 2.7 compatible" removed. |
| `src/config.py` (line 5) | Header claim removed. |
| `src/db_manager.py` (line 5) | Header claim removed. |
| `src/extensibility_hooks.py` (line 5) | Header claim removed. |
| `src/ingestion_core.py` (line 5) | Header claim removed. |
| `src/preview_cache.py` (line 5) | Header "Python 2.7/3+ compatible" → "Python 3.9+". |
| `src/video_player_widget.py` (line 5) | Header "Python 2.7/3+ compatible" → "Python 3.9+". |
| `src/geometry_viewer.py` (line 7) | "written to work with Python 2.7" claim removed. |
| `src/file_lock.py` (line 5; lines 230–234) | Header claim removed; **dead `TimeoutError` polyfill deleted** (the `if not hasattr(__builtins__, 'TimeoutError')` block is also buggy — `__builtins__` is a dict in `__main__`, so it can shadow the real builtin). |
| `src/nuke_bridge.py` (line 5; lines 18–19; line 516) | Header claim removed; **`unicode = str` shim deleted**; the `isinstance(name, unicode)` branch (~lines 516–522) rewritten to Py3 `str`/`bytes` handling for the `hashlib.md5` call. |
| `src/glb_converter.py` (lines 60, 137) | "for Python 2.7" comments in `_which` / `_communicate_with_timeout` corrected (functions kept — they are live helpers, only the misleading comments change). |
| `tools/stax_cli.py` (line 61; lines 68–74) | `from __future__ import ...` removed; the `except ImportError: from urllib2 import ...` Python-2 fallback deleted, keeping only the `urllib.request`/`urllib.error`/`urllib.parse` imports. |
| `src/debug_manager.py` (line 8) | Its "Python 2.7 compatible." header is gone as part of the H8 rewrite (§4.2). |

A regression-guard test (§5) walks the tree and asserts none of `"Python 2.7"`, `"unicode = str"`, `"urllib2"` survive in `.py` files (excluding vendored/`lib`/`dependencies`/`docs`/`tests`/`examples`/`bin`).

---

## 5. Testing Strategy

All tests are headless and mock-based, in the SP0 tiers. Each is written **red first** (reproducing the defect), then made green by the fix.

**`nuke` tier**
- `tests/nuke/test_panel_singleton.py` — with `mock_nuke`, monkeypatch `nuke_launcher.StaXPanel` to a lightweight counting stub and reset the module singleton, then assert `get_stax_panel()` returns the **same object** across two calls and constructs the panel exactly once. (Reproduces H5's duplicate-panel spawn; the accessor is the fix.)

**`unit` tier**
- `tests/unit/test_debug_manager.py` — assert `DebugManager.initialize(enabled=False)` does **not** replace `sys.stdout`/`sys.stderr` (identity preserved), that a manual `sys.stderr.write(...)` is still visible under `capsys` when debug is off (**stderr is never swallowed**), and that disabling sets the `"stax"` logger to `WARNING` while enabling sets `DEBUG`. (All fail against the old stream-hijack implementation.)
- `tests/unit/test_init_plugin_paths.py` — import `build_plugin_paths` from `init` (proves the module imports without Nuke) and assert every returned path is absolute (`os.path.isabs`), that `<root>/src/ui` and `<root>` are present, and that no path is CWD-relative / `./`-prefixed. (Reproduces L1.)
- `tests/unit/test_nuke_bridge_patch_removed.py` — assert `src/nuke_bridge_patch.py` no longer exists. (L3.)
- `tests/unit/test_no_py2_shims.py` — tree scan asserting no banned Python-2 tokens remain. (L7.)

**Interaction with the wider suite:** because the singleton test and any gui-tier test import `nuke_launcher` (which at import time calls `DebugManager.bootstrap_from_config()`), doing the H8 fix **before** the H5 fix guarantees that importing `nuke_launcher` in tests never installs a stream-swallowing proxy.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Importing `nuke_launcher` in the singleton test is heavy (pulls PySide2 + all `src/ui`). | Run offscreen (`QT_QPA_PLATFORM=offscreen`, set by SP0's conftest); PySide2 is a project dependency. Monkeypatch `StaXPanel` so no real panel/DB/UI is constructed — the test exercises only the accessor's caching logic. |
| `DebugManager` is global singleton state shared across tests. | The new `initialize`/`set_enabled` are idempotent and always (re)apply the enabled state; `initialize` never mutates interpreter streams, so leakage between tests is benign. Tests assert on logger level and stream identity, not on residual proxies. |
| `init.py` is `exec`'d by Nuke (not imported) at startup — the guard must not change that behavior. | The imperative block still runs unconditionally under `if _nuke is not None:` when Nuke is present; only the *import-without-Nuke* path is newly made safe. `build_plugin_paths` is pure and side-effect-free. |
| Removing the `unicode` shim breaks `register_toolset`'s md5 hashing on non-ASCII names. | The rewritten branch encodes `str` via UTF-8 and passes `bytes` through, preserving the exact hash input for ASCII and fixing it for Unicode; covered by keeping the existing toolset flow intact (no signature change). |
| The L7 guard test is over-broad and flags a legitimate future mention. | Scope is limited to `.py` files outside vendored/test/doc trees, and to three precise tokens; `changelog.md` (historical) and Markdown docs are excluded by the `.py` filter. |

---

## 7. Deliverables Checklist
- [ ] `nuke_launcher.py`: module-level `_STAX_PANEL_INSTANCE`, `StaXPanel.__init__` self-registration, `get_stax_panel()` accessor (H5).
- [ ] `menu.py`: three command strings routed through `get_stax_panel()` (H5).
- [ ] `src/debug_manager.py`: rewritten logger-scoped; no stream hijack; `stderr` never swallowed; `DebugManager.debug` added (H8).
- [ ] `init.py`: pure `build_plugin_paths(stax_root)`, absolute registration, import-safe without Nuke (L1).
- [ ] `src/nuke_bridge_patch.py`: deleted (L3).
- [ ] Python-2 claims/shims removed across the enumerated files; single-interpreter (Py3) stated (L7).
- [ ] Tests: `nuke/test_panel_singleton.py`, `unit/test_debug_manager.py`, `unit/test_init_plugin_paths.py`, `unit/test_nuke_bridge_patch_removed.py`, `unit/test_no_py2_shims.py` — all green (`pytest -m "not manual"`).

---

## 8. Follow-on
SP6 (UI correctness) is the natural next sub-project; it fixes the daily-driver UI defects (H3/M3/M4/M6/M7/H7) and the frame-range parsing (L8) that SP5 deliberately left in `NukeIntegration`. SP1 (already sequenced earlier) owns the analytics insertion-logging hook that the deleted `nuke_bridge_patch.py` merely *described*.
