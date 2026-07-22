# SP5 — Nuke integration & embedded-mode correctness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make StaX's embedded-in-Nuke path correct: menu commands hit a live `StaXPanel` singleton (H5), the debug controller stops hijacking `sys.stdout`/`sys.stderr` and never swallows `stderr` (H8), Nuke plugin paths are absolute (L1), the orphaned `src/nuke_bridge_patch.py` is deleted (L3), and all Python-2.7 claims and dead shims are removed in favor of a single Python-3 interpreter (L7).

**Architecture:** Introduce a module-level `StaXPanel` singleton in `nuke_launcher.py` populated from `StaXPanel.__init__` and exposed via `get_stax_panel()`; route `menu.py`'s Quick Ingest / Register Toolset / Advanced Search commands through it. Rewrite `src/debug_manager.py` to scope Debug Mode to the `"stax"` logger's level, keeping its public API. Refactor `init.py` so plugin-path assembly is a pure, importable, absolute-path function and the module imports cleanly without Nuke. Delete the stale patch file. Sweep the tree for Py2 shims/claims and enforce their absence with a guard test.

**Tech Stack:** Python 3.9, PySide2 (offscreen), pytest / pytest-qt (from SP0's `dev` extra), the SP0 fixtures (`stax_db`, `stax_config`, `mock_nuke`), flat imports (`src/` on `sys.path`).

## Global Constraints

- **Platforms:** Windows + Linux only. Paths must be built with `os.path.join` / `os.path.normpath`, never hardcoded separators.
- **Nuke is always mocked.** Use `mock_nuke` + `NukeBridge(mock_mode=True)`; never import a real `nuke`.
- **Import convention:** flat — `from debug_manager import DebugManager`, `from init import build_plugin_paths`, `import nuke_launcher`. `src/` and the repo root are on `sys.path` (SP0 conftest).
- **Logging, not print, in new code.** New DebugManager output routes through `logging.getLogger("stax")`; do not add gated `print`s.
- **TDD:** every task writes a failing test first, then the fix. Run `pytest -m "not manual"` before each commit.
- **Do the H8 task (Task 2) before the H5 task (Task 3):** the H5 test imports `nuke_launcher`, whose import calls `DebugManager.bootstrap_from_config()`; the H8 rewrite guarantees that import never swallows test output.
- **Conventional commits:** `fix:` for H5/H8/L1, `chore:`/`refactor:` for L3/L7, `test:` for test-only additions. Frequent commits (one per task). Do **not** commit unless a step says so; the executor commits per task.
- **Do not edit `docs/superpowers/IMPLEMENTATION_PROGRESS.md`** as part of code tasks (progress tracking is handled separately).

---

## Key signatures (verified against the codebase)

- `nuke_launcher.show_stax_panel()` → in Nuke mode returns `nukescripts.panels.registerWidgetAsPanel('nuke_launcher.StaXPanel', ...).addToPane()`'s result (a Nuke pane object, **not** a `StaXPanel`); in standalone returns a `StaXPanel` (`nuke_launcher.py:867`).
- `nuke_launcher.StaXPanel(parent=None)` — `QtWidgets.QWidget` subclass; methods `ingest_files()`, `register_toolset()`, `show_advanced_search()` (`nuke_launcher.py:204,727,789,859`).
- `src/debug_manager.py` `DebugManager` classmethods: `initialize(enabled=True)`, `set_enabled(enabled)`, `is_enabled()`, `restore_original_streams()`, `bootstrap_from_config(config_path=None)`, `sync_from_config(config)` (`src/debug_manager.py:73`). Callers: `menu.py:16`, `nuke_launcher.py:17`, `nuke_launcher.py:276` (`sync_from_config`), and `main.py`.
- `init.py` currently: `nuke.pluginAddPath(subdir)` over `['./tools', './src/ui', './src', './resources', './dependencies/ffpyplayer']` and `subdir.lstrip('./')` (`init.py:38-48`).
- `NukeBridge(mock_mode=True)`; `.create_read_node(filepath, frame_range=None, node_name=None)` → dict in mock mode (`src/nuke_bridge.py:37,60`). `NukeIntegration(nuke_bridge, db_manager, config=None, ingestion_core=None, processor_manager=None)` (`src/nuke_bridge.py:359`).
- `src/nuke_bridge.py` L7 targets: header line 5; `if sys.version_info[0] >= 3: unicode = str` (lines 18–19); `if isinstance(name, unicode):` in `register_toolset` (~line 516).
- `src/file_lock.py` L7 targets: header line 5; the `if not hasattr(__builtins__, 'TimeoutError')` polyfill (lines 230–234).
- `tools/stax_cli.py` L7 targets: `from __future__ import ...` (line 61); `except ImportError: from urllib2 import ...` (lines 72–74).
- SP0 fixtures available: `stax_db`, `stax_config`, `mock_nuke`, `tiny_png*`, `tiny_sequence` (`tests/conftest.py`). Markers `unit`, `gui`, `nuke`, `ffmpeg`, `slow`, `manual` (`pytest.ini`).

---

## Task 1: Delete the orphaned `src/nuke_bridge_patch.py` (L3)

**Files:**
- Delete: `src/nuke_bridge_patch.py`
- Create: `tests/unit/test_nuke_bridge_patch_removed.py`

**Interfaces:**
- Produces: a regression test that fails if the stale patch file is ever re-added.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_nuke_bridge_patch_removed.py`:

```python
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.unit
def test_nuke_bridge_patch_is_deleted():
    """L3: the orphaned apply-by-hand skeleton must not exist. It referenced
    nonexistent NukeBridge.paste_toolset and documented an uncalled analytics
    hook."""
    stale = os.path.join(_REPO_ROOT, "src", "nuke_bridge_patch.py")
    assert not os.path.exists(stale), "src/nuke_bridge_patch.py should be deleted"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_nuke_bridge_patch_removed.py -v`
Expected: FAIL — the file still exists.

- [ ] **Step 3: Delete the file**

```bash
cd "d:/Scripts/modern-stock-browser"
git rm --force src/nuke_bridge_patch.py
```

- [ ] **Step 4: Re-run the test**

Run: `pytest tests/unit/test_nuke_bridge_patch_removed.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_nuke_bridge_patch_removed.py
git commit -m "chore: delete orphaned src/nuke_bridge_patch.py (L3)"
```

---

## Task 2: Rewrite `DebugManager` to be logger-scoped (H8)

**Files:**
- Replace: `src/debug_manager.py`
- Create: `tests/unit/test_debug_manager.py`

**Interfaces:**
- Produces: a `DebugManager` that toggles the `"stax"` logger level and never touches `sys.stdout`/`sys.stderr`. Public API unchanged (`initialize`, `set_enabled`, `is_enabled`, `restore_original_streams`, `bootstrap_from_config`, `sync_from_config`), plus new `debug(message, *args)`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_debug_manager.py`:

```python
import logging
import sys

import pytest

from debug_manager import DebugManager


@pytest.mark.unit
def test_initialize_does_not_replace_interpreter_streams():
    """H8: DebugManager must never replace sys.stdout / sys.stderr."""
    before_out, before_err = sys.stdout, sys.stderr
    DebugManager.initialize(enabled=False)
    try:
        assert sys.stdout is before_out
        assert sys.stderr is before_err
    finally:
        DebugManager.set_enabled(True)


@pytest.mark.unit
def test_stderr_is_never_swallowed_when_debug_off(capsys):
    """H8: with debug disabled, a stderr write must still reach stderr — the
    old proxy dropped ALL writes, silencing Nuke's own console."""
    DebugManager.initialize(enabled=False)
    try:
        sys.stderr.write("real-error-from-nuke\n")
        captured = capsys.readouterr()
        assert "real-error-from-nuke" in captured.err
    finally:
        DebugManager.set_enabled(True)


@pytest.mark.unit
def test_enabled_state_maps_to_stax_logger_level():
    """H8: suppression is scoped to StaX's own logger, not global streams."""
    DebugManager.set_enabled(False)
    assert logging.getLogger("stax").level == logging.WARNING
    DebugManager.set_enabled(True)
    assert logging.getLogger("stax").level == logging.DEBUG
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_debug_manager.py -v`
Expected: FAIL — the old implementation replaces the streams (identity assertion fails) and swallows stderr when disabled.

- [ ] **Step 3: Replace `src/debug_manager.py`**

Replace the entire file with:

```python
# -*- coding: utf-8 -*-
"""Centralized debug-output controller for StaX.

Debug Mode toggles the verbosity of StaX's *own* logger only. It never
replaces the interpreter's ``sys.stdout`` / ``sys.stderr`` and never swallows
``stderr`` — doing so inside a host application (Nuke) silenced the host's own
console and other tools' tracebacks for the whole session (issue H8).
"""

import json
import logging
import os
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'config', 'config.json')

# StaX's own logger namespace. Suppression is scoped to this tree; the root
# logger, sys.stdout, and sys.stderr are left untouched.
_STAX_LOGGER_NAME = 'stax'


class DebugManager(object):
    """Controller for StaX's own debug verbosity (logger-scoped)."""

    _initialized = False
    _enabled = True
    _lock = threading.RLock()

    @classmethod
    def initialize(cls, enabled=True):
        """Configure the StaX logger and set the initial enabled state.

        Does NOT touch sys.stdout / sys.stderr.
        """
        with cls._lock:
            logger = logging.getLogger(_STAX_LOGGER_NAME)
            if not cls._initialized:
                # Give StaX log records a sink without hijacking interpreter
                # streams. A NullHandler stays quiet unless the app installs
                # its own handler (see stax_logger).
                if not logger.handlers:
                    logger.addHandler(logging.NullHandler())
                cls._initialized = True
            cls.set_enabled(enabled)

    @classmethod
    def set_enabled(cls, enabled):
        """Enable or disable StaX debug output (StaX logger level only)."""
        with cls._lock:
            cls._enabled = bool(enabled)
            logger = logging.getLogger(_STAX_LOGGER_NAME)
            logger.setLevel(logging.DEBUG if cls._enabled else logging.WARNING)

    @classmethod
    def is_enabled(cls):
        with cls._lock:
            return cls._enabled

    @classmethod
    def debug(cls, message, *args):
        """Emit a StaX debug message (suppressed when Debug Mode is off).

        Use in place of gated ``print`` calls. stdout/stderr are never
        replaced, so host and other-tool output is unaffected.
        """
        logging.getLogger(_STAX_LOGGER_NAME).debug(message, *args)

    @classmethod
    def restore_original_streams(cls):
        """Back-compat reset. Streams are never replaced anymore, so this only
        clears the initialized flag (kept so existing callers don't break)."""
        with cls._lock:
            cls._initialized = False

    @classmethod
    def bootstrap_from_config(cls, config_path=None):
        """Read the debug preference from the config file and initialize."""
        debug_enabled = cls._read_debug_flag(config_path)
        cls.initialize(debug_enabled)
        return debug_enabled

    @classmethod
    def sync_from_config(cls, config):
        """Update enabled state based on a Config instance."""
        if config is None:
            return
        try:
            enabled = config.get('debug_mode', True)
        except Exception:
            enabled = True
        cls.set_enabled(enabled)

    @staticmethod
    def _read_debug_flag(config_path=None):
        path = config_path or _DEFAULT_CONFIG_PATH
        try:
            with open(path, 'r') as handle:
                data = json.load(handle)
            return bool(data.get('debug_mode', True))
        except Exception:
            return True


__all__ = ['DebugManager']
```

- [ ] **Step 4: Re-run the test**

Run: `pytest tests/unit/test_debug_manager.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Sanity-check the callers still import**

Run:
```bash
python -c "from debug_manager import DebugManager; DebugManager.bootstrap_from_config(); DebugManager.sync_from_config(None); print('debug_manager ok')"
```
Expected: prints `debug_manager ok` with no traceback (proves `bootstrap_from_config`/`sync_from_config` — the methods `menu.py`/`nuke_launcher.py` call — still work).

- [ ] **Step 6: Commit**

```bash
git add src/debug_manager.py tests/unit/test_debug_manager.py
git commit -m "fix: scope DebugManager to the stax logger; stop hijacking stdout/stderr (H8)"
```

---

## Task 3: StaXPanel singleton + `get_stax_panel()` accessor; wire `menu.py` (H5)

**Files:**
- Modify: `nuke_launcher.py`
- Modify: `menu.py`
- Create: `tests/nuke/test_panel_singleton.py`

**Interfaces:**
- Produces: `nuke_launcher.get_stax_panel()` → the live `StaXPanel` singleton; `nuke_launcher._STAX_PANEL_INSTANCE` module global set from `StaXPanel.__init__`.
- Consumes: `mock_nuke` fixture.

- [ ] **Step 1: Write the failing test**

Create `tests/nuke/test_panel_singleton.py`:

```python
import pytest


@pytest.mark.nuke
def test_get_stax_panel_returns_a_singleton(mock_nuke, monkeypatch):
    """H5: menu commands must operate on one live StaXPanel, not spawn a new
    one each call. get_stax_panel() caches a module-level singleton."""
    import nuke_launcher

    created = []

    class _FakePanel(object):
        def __init__(self):
            created.append(self)

    # Substitute a lightweight stub so no real Config/DB/UI is constructed.
    monkeypatch.setattr(nuke_launcher, "StaXPanel", _FakePanel)
    # Ensure a clean slate regardless of test ordering.
    monkeypatch.setattr(nuke_launcher, "_STAX_PANEL_INSTANCE", None, raising=False)

    first = nuke_launcher.get_stax_panel()
    second = nuke_launcher.get_stax_panel()

    assert first is second                 # same live widget
    assert len(created) == 1               # constructed exactly once (no duplicate panel)


@pytest.mark.nuke
def test_get_stax_panel_is_exposed(mock_nuke):
    """The accessor menu.py depends on must exist."""
    import nuke_launcher

    assert hasattr(nuke_launcher, "get_stax_panel")
    assert callable(nuke_launcher.get_stax_panel)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/nuke/test_panel_singleton.py -v`
Expected: FAIL — `nuke_launcher.get_stax_panel` does not exist yet. (If importing `nuke_launcher` errors instead of failing the assertion, verify PySide2 is installed and `QT_QPA_PLATFORM=offscreen` is set — both are provided by SP0's conftest/CI.)

- [ ] **Step 3: Add the singleton global and accessor to `nuke_launcher.py`**

Insert immediately **before** the `class StaXPanel(QtWidgets.QWidget):` line (after the "All imports completed successfully" block, ~line 202):

```python
# Module-level singleton: the one live StaXPanel the menu operates on. In Nuke
# mode show_stax_panel() returns a Nuke pane object, not this widget, so menu
# commands must go through get_stax_panel() instead (issue H5).
_STAX_PANEL_INSTANCE = None
```

- [ ] **Step 4: Register the instance from `StaXPanel.__init__`**

At the very end of `StaXPanel.__init__` (immediately after the final `if logger: logger.separator()` block, ~line 416), append:

```python
        # Register this instance as the module-level singleton so menu commands
        # operate on the live widget — whether it was built here or by Nuke's
        # registerWidgetAsPanel('nuke_launcher.StaXPanel', ...) machinery (H5).
        global _STAX_PANEL_INSTANCE
        _STAX_PANEL_INSTANCE = self
```

- [ ] **Step 5: Add the `get_stax_panel()` accessor**

Insert immediately **before** `def show_stax_panel():` (~line 867):

```python
def get_stax_panel():
    """Return the live StaXPanel singleton, creating one if none exists yet.

    Menu commands MUST call this rather than show_stax_panel(): in Nuke mode
    show_stax_panel() returns registerWidgetAsPanel(...).addToPane()'s result
    (a Nuke pane object), NOT a StaXPanel, so calling panel.ingest_files() on it
    raises AttributeError and docks a duplicate panel each time (H5).
    """
    global _STAX_PANEL_INSTANCE
    if _STAX_PANEL_INSTANCE is None:
        _STAX_PANEL_INSTANCE = StaXPanel()
    return _STAX_PANEL_INSTANCE
```

- [ ] **Step 6: Re-run the nuke-tier test**

Run: `pytest tests/nuke/test_panel_singleton.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Wire `menu.py` to the accessor**

In `menu.py`, change the three command strings (Commands 2, 3, 4). Replace:

```python
            'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.ingest_files()',
```
with
```python
            'import nuke_launcher; nuke_launcher.get_stax_panel().ingest_files()',
```

Replace:
```python
            'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.register_toolset()',
```
with
```python
            'import nuke_launcher; nuke_launcher.get_stax_panel().register_toolset()',
```

Replace:
```python
            'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.show_advanced_search()',
```
with
```python
            'import nuke_launcher; nuke_launcher.get_stax_panel().show_advanced_search()',
```

(The `Open StaX Panel` command at `menu.py:77` still calls `show_stax_panel()` — that one *docks* the panel and is correct.)

- [ ] **Step 8: Verify the menu command strings compile**

Run:
```bash
python -c "import ast; ast.parse(open('menu.py').read()); print('menu.py parses')"
```
Expected: prints `menu.py parses`. (Grep-verify the wiring:)
```bash
grep -n "get_stax_panel()" menu.py
```
Expected: three lines — `.ingest_files()`, `.register_toolset()`, `.show_advanced_search()`.

- [ ] **Step 9: Commit**

```bash
git add nuke_launcher.py menu.py tests/nuke/test_panel_singleton.py
git commit -m "fix: route Nuke menu commands through a StaXPanel singleton accessor (H5)"
```

---

## Task 4: Absolute, importable plugin-path assembly in `init.py` (L1)

**Files:**
- Modify (replace): `init.py`
- Create: `tests/unit/test_init_plugin_paths.py`

**Interfaces:**
- Produces: pure `init.build_plugin_paths(stax_root)` returning absolute normalized paths; `init.install_stax_plugin_paths(nuke_module)`; the module imports cleanly when `nuke` is absent.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_init_plugin_paths.py`:

```python
import os

import pytest

from init import build_plugin_paths


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
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_init_plugin_paths.py -v`
Expected: FAIL / ERROR — `build_plugin_paths` does not exist (and importing the old `init.py` raises because it hard-fails when `nuke` is absent).

- [ ] **Step 3: Replace `init.py`**

Replace the entire file with:

```python
# -*- coding: utf-8 -*-
"""
StaX Init Script for Nuke
Loads on Nuke startup to register StaX's plugin paths.
Single interpreter: Python 3 (Nuke 13+).
"""

import os
import sys


def build_plugin_paths(stax_root):
    """Return the absolute, normalized plugin directories to register with Nuke.

    Pure and importable (no Nuke dependency) so it can be unit-tested. Replaces
    the old CWD-relative './tools' entries and the buggy ``subdir.lstrip('./')``
    char-set strip (issue L1).
    """
    root = os.path.abspath(stax_root)
    subdirs = [
        'tools',
        os.path.join('src', 'ui'),
        'src',
        'resources',
        os.path.join('dependencies', 'ffpyplayer'),
    ]
    paths = [root]
    for subdir in subdirs:
        paths.append(os.path.normpath(os.path.join(root, subdir)))
    return paths


def install_stax_plugin_paths(nuke_module):
    """Register StaX's plugin directories with Nuke using absolute paths."""
    stax_root = os.path.dirname(os.path.abspath(__file__))
    if stax_root not in sys.path:
        sys.path.insert(0, stax_root)

    for path in build_plugin_paths(stax_root):
        nuke_module.pluginAddPath(path)
        if os.path.isdir(path):
            print("[StaX init.py]   [OK] Added: {} (exists)".format(path))
        else:
            print("[StaX init.py]   [WARN] Added: {} (NOT FOUND)".format(path))

    try:
        from stax_logger import init_logger
        logger = init_logger()
        logger.info("StaX init.py completed; plugin paths configured")
    except Exception as exc:
        print("[StaX init.py] [WARN] Logger init failed: {}".format(exc))


# Executed by Nuke on startup. Importable in tests: when `nuke` is unavailable
# the module imports cleanly and simply skips registration.
try:
    import nuke as _nuke
except ImportError:
    _nuke = None

if _nuke is not None:
    print("\n" + "=" * 80)
    print("[StaX init.py] Starting initialization...")
    print("=" * 80)
    try:
        install_stax_plugin_paths(_nuke)
        print("[StaX init.py] [OK] Initialization complete")
        print("=" * 80 + "\n")
    except Exception as exc:
        import traceback
        print("[StaX init.py] [ERROR] Initialization failed: {}".format(exc))
        traceback.print_exc()
        raise
```

- [ ] **Step 4: Re-run the test**

Run: `pytest tests/unit/test_init_plugin_paths.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add init.py tests/unit/test_init_plugin_paths.py
git commit -m "fix: register absolute Nuke plugin paths via a pure build_plugin_paths (L1)"
```

---

## Task 5: Remove Python-2.7 claims and dead shims — single interpreter (L7)

**Files:**
- Modify: `main.py`, `nuke_launcher.py`, `src/config.py`, `src/db_manager.py`, `src/extensibility_hooks.py`, `src/ingestion_core.py`, `src/preview_cache.py`, `src/video_player_widget.py`, `src/geometry_viewer.py`, `src/file_lock.py`, `src/nuke_bridge.py`, `src/glb_converter.py`, `tools/stax_cli.py`
- Create: `tests/unit/test_no_py2_shims.py`

**Interfaces:**
- Produces: a tree-scan guard test that fails if any banned Python-2 token reappears.
- Note: `src/debug_manager.py`'s Py2 header was already removed by Task 2's rewrite. `changelog.md` (historical) and Markdown docs are intentionally untouched.

- [ ] **Step 1: Write the failing guard test**

Create `tests/unit/test_no_py2_shims.py`:

```python
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Banned in first-party .py files. The app is Python-3 only.
_BANNED = ("Python 2.7", "unicode = str", "urllib2")

# Vendored / generated / doc / test trees are not first-party source.
_SKIP_DIRS = {".git", "lib", "dependencies", "docs", "tests", "examples", "bin",
              "__pycache__", ".venv", "venv"}


def _iter_source_files():
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


@pytest.mark.unit
def test_no_python2_claims_or_shims_remain():
    """L7: no 'Python 2.7' claims and no dead Py2 shims in first-party source."""
    offenders = []
    for path in _iter_source_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        for token in _BANNED:
            if token in text:
                offenders.append("{}: {!r}".format(os.path.relpath(path, _REPO_ROOT), token))
    assert not offenders, "Python-2 shims/claims remain:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_no_py2_shims.py -v`
Expected: FAIL — the assertion lists the offending files (`main.py`, `nuke_launcher.py`, `src/config.py`, `src/db_manager.py`, `src/extensibility_hooks.py`, `src/ingestion_core.py`, `src/preview_cache.py`, `src/video_player_widget.py`, `src/geometry_viewer.py`, `src/file_lock.py`, `src/nuke_bridge.py`, `src/glb_converter.py`, `tools/stax_cli.py`).

- [ ] **Step 3: Fix the header-only files**

Edit each header docstring line:

- `main.py` line 3: `Main GUI for StaX — Python 2.7 / 3.x compatible` → `Main GUI for StaX — Python 3.9+`
- `nuke_launcher.py` line 5: delete the line `Python 2.7 compatible`
- `src/config.py` line 5: delete the line `Python 2.7 compatible`
- `src/db_manager.py` line 5: delete the line `Python 2.7 compatible`
- `src/extensibility_hooks.py` line 5: delete the line `Python 2.7 compatible`
- `src/ingestion_core.py` line 5: delete the line `Python 2.7 compatible`
- `src/preview_cache.py` line 5: `Python 2.7/3+ compatible` → `Python 3.9+`
- `src/video_player_widget.py` line 5: `Python 2.7/3+ compatible` → `Python 3.9+`
- `src/geometry_viewer.py` line 7: change `reference implementation from tests/glb_converter but is written to work with Python 2.7, which StaX targets for Nuke compatibility.` → `reference implementation from tests/glb_converter.` (drop the Py2 clause).

- [ ] **Step 4: Remove the dead `TimeoutError` polyfill in `src/file_lock.py`**

Delete the header claim on line 5 (`Python 2.7 compatible`), and delete the entire trailing block (lines ~230–234):

```python
# Python 2.7 compatibility: Define TimeoutError if not available
if not hasattr(__builtins__, 'TimeoutError'):
    class TimeoutError(OSError):
        """Timeout error for Python 2.7 compatibility."""
        pass
```

(Under Python 3 `TimeoutError` is always a builtin; the guard is also buggy because `__builtins__` is a dict in `__main__`.)

- [ ] **Step 5: Remove the `unicode` shim and fix the branch in `src/nuke_bridge.py`**

Delete the header claim on line 5. Delete lines 18–19:

```python
if sys.version_info[0] >= 3:  # Python 3 fallback for compatibility
    unicode = str
```

In `register_toolset` (~lines 516–522), replace:

```python
        if isinstance(name, unicode):
            name_bytes = name.encode('utf-8')
        elif isinstance(name, str):
            name_bytes = name
        else:
            name_bytes = str(name)
        name_hash = hashlib.md5(name_bytes).hexdigest()[:8]
```

with:

```python
        if isinstance(name, str):
            name_bytes = name.encode('utf-8')
        elif isinstance(name, bytes):
            name_bytes = name
        else:
            name_bytes = str(name).encode('utf-8')
        name_hash = hashlib.md5(name_bytes).hexdigest()[:8]
```

(`hashlib.md5` requires `bytes` in Python 3; this encodes `str` and passes `bytes` through.)

- [ ] **Step 6: Fix the misleading comments in `src/glb_converter.py`**

- Line ~60: `"""Portable find executable for Python 2.7."""` → `"""Portable executable lookup (shutil.which with a PATH fallback)."""`
- Line ~137: `"""Communicate with timeout support for Python 2.7."""` → `"""Communicate with a subprocess, enforcing a timeout."""`

(The functions themselves are live helpers and are kept unchanged.)

- [ ] **Step 7: Remove the `urllib2` fallback in `tools/stax_cli.py`**

Delete line 61 (`from __future__ import absolute_import, print_function, unicode_literals`). Replace the try/except import block (lines ~68–74):

```python
try:
    from urllib.request import urlopen, Request
    from urllib.error   import HTTPError, URLError
    from urllib.parse   import urlencode, quote
except ImportError:
    from urllib2 import urlopen, Request, HTTPError, URLError  # Python 2
    from urllib  import urlencode, quote
```

with the plain Python-3 imports:

```python
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
```

- [ ] **Step 8: Re-run the guard test**

Run: `pytest tests/unit/test_no_py2_shims.py -v`
Expected: PASS (1 passed). If it still lists an offender, edit that file — do not weaken `_BANNED`.

- [ ] **Step 9: Verify the touched modules still import**

Run:
```bash
python -c "import ast; [ast.parse(open(f).read()) for f in ['main.py','nuke_launcher.py','tools/stax_cli.py','src/file_lock.py','src/nuke_bridge.py','src/glb_converter.py','src/config.py','src/preview_cache.py','src/video_player_widget.py','src/geometry_viewer.py','src/db_manager.py','src/extensibility_hooks.py','src/ingestion_core.py']]; print('all parse')"
```
Expected: prints `all parse`. Then confirm the pure-logic modules import:
```bash
python -c "from file_lock import FileLockManager, TimeoutError; from preview_cache import PreviewCache; print('imports ok')"
```
Expected: prints `imports ok` (the builtin `TimeoutError` is importable from `file_lock`'s namespace via re-export only if used — if this errors on the name `TimeoutError`, drop it from the import; the point is that `file_lock` imports cleanly).

- [ ] **Step 10: Run the full SP5 suite**

Run: `pytest -m "not manual"`
Expected: all SP0 + SP5 `unit`/`gui`/`nuke` tests pass or xfail; **0 failed, 0 errored**.

- [ ] **Step 11: Commit**

```bash
git add main.py nuke_launcher.py src/config.py src/db_manager.py src/extensibility_hooks.py src/ingestion_core.py src/preview_cache.py src/video_player_widget.py src/geometry_viewer.py src/file_lock.py src/nuke_bridge.py src/glb_converter.py tools/stax_cli.py tests/unit/test_no_py2_shims.py
git commit -m "refactor: drop Python 2.7 claims and dead compat shims; single Py3 interpreter (L7)"
```

---

## Self-Review

**1. Spec coverage:**
- H5 singleton + accessor + menu wiring → Task 3 ✓
- H8 logger-scoped DebugManager, no stream hijack, stderr never swallowed → Task 2 ✓
- L1 absolute + pure + importable plugin paths → Task 4 ✓
- L3 delete `src/nuke_bridge_patch.py` + absence test → Task 1 ✓
- L7 remove claims/shims across all enumerated files + guard test → Task 5 ✓
- Tests use `mock_nuke` (Task 3) and unit tier (Tasks 1, 2, 4, 5); `NukeBridge(mock_mode=True)` signature referenced in Key signatures ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every code step shows complete, real code (full `debug_manager.py`, full `init.py`, exact before/after snippets for each L7 edit, exact `menu.py` command strings). Fallbacks (e.g. relax a `TimeoutError` import, PySide2/offscreen note) specify the exact alternative.

**3. Type / signature consistency:** `DebugManager` public methods (`initialize`, `set_enabled`, `is_enabled`, `restore_original_streams`, `bootstrap_from_config`, `sync_from_config`) match the callers in `menu.py:16`, `nuke_launcher.py:17,276`, and `main.py`. `get_stax_panel()` is defined in `nuke_launcher.py` (Task 3) and consumed by `menu.py`'s command strings with matching method names (`ingest_files`, `register_toolset`, `show_advanced_search`) verified against `nuke_launcher.py:727,789,859`. `build_plugin_paths(stax_root)` is defined and consumed with the same name (Task 4). `_STAX_PANEL_INSTANCE` is written in `StaXPanel.__init__` and in `get_stax_panel()`, and reset in the test — one consistent module global.

**4. Ordering:** Task 2 (H8) precedes Task 3 (H5) so that importing `nuke_launcher` in the singleton test never triggers a stream-swallowing proxy. Task 1 (L3, self-contained) runs first as a warm-up; Task 5 (L7) runs last and its guard test only passes once every earlier-touched file (`nuke_launcher.py` header, `debug_manager.py`) is already clean.

---

## Notes for the executor
- **Never weaken a test to make it pass.** If the L7 guard still flags a file, fix the file. If the singleton import is too heavy on a runner, confirm PySide2 + `QT_QPA_PLATFORM=offscreen`; do not stub out `nuke_launcher` itself.
- Run `pytest -m "not manual"` before every commit.
- Do **not** wire an analytics insertion hook into `NukeIntegration.insert_element` — the orphaned patch merely *described* that; the real hook is SP1's job. SP5 only deletes the stale skeleton.
- Do not touch `docs/superpowers/IMPLEMENTATION_PROGRESS.md` from these code tasks.
