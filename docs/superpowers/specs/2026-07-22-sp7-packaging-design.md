# SP7 — Build, Packaging & Deployment — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). SP7 converges the packaging/deployment layer and fixes the per-user runtime paths (logs/config). It builds on SP0's test harness and is orthogonal to the DB/async/security work (SP1–SP6).

---

## 1. Background & Motivation

The StaX audit (`STAX_AUDIT_REPORT.md`) surfaced two packaging/deployment defects:

**M11 — Three divergent, individually-broken build definitions.** The repo ships *three* mutually inconsistent ways to freeze the app, none of which is self-consistent:

1. **`StaX.spec`** (committed PyInstaller spec) hardcodes absolute machine paths — `['D:/Scripts/modern-stock-browser/main.py']`, `pathex=['D:/Scripts/modern-stock-browser']`, `datas=[('D:/Scripts/…/resources', …)]`, and `icon='D:/Scripts/…/resources/logo.ico'` — so it only builds on the original author's machine (`StaX.spec:6-13,50`).
2. **`tools/build_installer.py`** *regenerates a different PyInstaller spec at runtime* (`create_spec_file`, `:76-157`), overwriting the committed `StaX.spec`, and hardcodes `APP_VERSION = "1.0.0"` (`:22`).
3. **`setup_freeze.py`** uses **cx_Freeze** and is the definition **`tools/build.ps1` actually invokes** (`build.ps1:213`) and that the Inno Setup installer (`tools/build_win_installer.ps1`) consumes. But `cx-freeze` is **not declared in `pyproject.toml`**, so `uv sync --all-extras` (`build.ps1:132`) never installs it and the build aborts with "cx_Freeze not found" (`build.ps1:154-159`). Its Windows icon points at a **`.png`** (`setup_freeze.py:206`) — Windows executables require a `.ico`, so the icon is silently dropped.

Layered on top, the **version disagrees across all three**: `pyproject.toml` says `0.1.0`, `src/__init__.py` says `0.1.0`, `tools/build_installer.py` says `1.0.0`, and `setup_freeze.py`'s fallback returns `0.0.0`.

**M14 — Logger writes into the read-only install dir; no rotation; new file per process.** `stax_logger.py:26-37` writes logs to `logs/` **next to the module**. In a frozen build installed under `%ProgramFiles%\StaX` that directory is **not user-writable**, so logging silently degrades (the write is swallowed at `stax_logger.py:71-72`). It also creates a **fresh timestamped file every process start** (`stax_{YYYYmmdd_HHMMSS}.log`) with **no rotation**, and is initialized from three entry points (`init.py:62`, `menu.py:44`, `nuke_launcher.py:27`) — an unbounded pile of tiny log files.

The same "writes next to the module / relative to CWD" reasoning applies to the config/data paths (`src/debug_manager.py:17-18` reads `<project>/config/config.json`; `src/config.py` defaults `database_path` to `./data/stax.db`). SP7 lands a shared per-user path resolver that fixes the logger now and gives SP1/config the mechanism to move the DB and config off the install dir.

### Program context (decisions already made)
- **Target platforms:** Windows + Linux (no macOS). The build must run on both; the `.ps1` scripts are Windows-only, so a Linux build/run path must exist.
- **Logging, not print** (locked). The rewritten logger routes through stdlib `logging` with a rotating handler.
- **Flat imports** — `src/` is on `sys.path`; new modules (`src/version.py`, `src/paths.py`) are imported flat (`from version import …`, `from paths import …`).

---

## 2. Goals / Non-Goals

### Goals
- **Converge on exactly one packager: cx_Freeze.** Delete the two PyInstaller definitions (`StaX.spec`, `tools/build_installer.py`), declare `cx-freeze` in `pyproject.toml`, remove the now-unused `pyinstaller` runtime dependency.
- **All build paths derive from `__file__`** — no absolute drive paths in the surviving build definition.
- **Fix the frozen Windows icon** to `resources/logo.ico` (the file already exists in the repo).
- **Single-source the version:** `src/version.py` is the one source of truth; `pyproject.toml` derives its version from it (PEP 621 `dynamic`), and the build scripts read the same file.
- **Per-user writable runtime paths** via a new `src/paths.py`: `%LOCALAPPDATA%\StaX\…` on Windows, XDG dirs (`~/.local/state`, `~/.local/share`, `~/.config`) on Linux, with a temp-dir fallback when the preferred location is unwritable.
- **Rewrite `stax_logger.py`** around stdlib `logging` + `RotatingFileHandler`, writing to `get_log_dir()`, initialized once, preserving the existing public API (`debug/info/warning/error/critical/exception/separator`, `get_logger()`, `init_logger()`).
- **A Linux build/run path**: a `tools/build.sh` (cx_Freeze) and `tools/run_standalone.sh`, plus documented `python setup_freeze.py build_exe` / `python main.py`.
- **Tests** for the version source, the per-OS log-dir resolver, and a static "no absolute paths in the build definition" check.

### Non-Goals (explicitly deferred)
- **A Linux installer package** (`.deb` / `.rpm` / AppImage) — documented follow-up. SP7 delivers a Linux *portable* build + run scripts, not a native installer.
- **Fixing the ffmpeg download supply-chain issues** (C3) — owned by SP4/SP3.
- **Moving the SQLite DB and `config.json` to per-user dirs** — SP7 lands the resolver (`get_data_dir()`, `get_config_dir()`) and wires only the **logger**; rewiring `Config`/`DatabaseManager` defaults is a documented follow-up jointly owned with SP1 (it touches the DB layer under active consolidation).
- **Code-signing / notarization** of the installer.

---

## 3. Approach

**Chosen approach: converge on cx_Freeze; delete the PyInstaller definitions.**

Justification (why cx_Freeze wins over PyInstaller here):

| Criterion | cx_Freeze (`setup_freeze.py`) | PyInstaller (`StaX.spec` + `build_installer.py`) |
|---|---|---|
| **Already wired end-to-end** | ✅ `tools/build.ps1` calls it; `tools/build_win_installer.ps1` (Inno Setup) consumes its output dir | ❌ Neither spec is invoked by the documented build entrypoint or the shipping installer |
| **Absolute-path hygiene** | ✅ Every path derives from `ROOT = os.path.dirname(os.path.abspath(__file__))` | ❌ `StaX.spec` hardcodes `D:/Scripts/…`; `build_installer.py` regenerates a spec at runtime |
| **Produces both required executables** | ✅ One `setup()` emits **StaX.exe** *and* **StaX_nuke_launcher.exe** (the Nuke launcher the Inno installer registers) | ❌ Specs build only a single `StaX` exe — the Nuke launcher is missing |
| **Cross-platform** | ✅ Same `setup_freeze.py build_exe` runs on Linux (`base=None`) | ⚠️ Works but neither spec is set up for it |
| **Version handling** | Reads `src/version.py` first (once single-sourced) | Hardcoded `1.0.0` |

cx_Freeze is the only definition that is already correct *by construction* (paths from `__file__`), already integrated with the installer, and already emits the two-executable layout the Nuke integration needs. The remaining defects in it are small and local (missing dependency declaration, `.png`→`.ico`, version source). PyInstaller would require rebuilding the Inno integration and adding a second-executable spec for no benefit.

Rejected alternatives:
- *Converge on PyInstaller* — throws away the working Inno Setup integration and the dual-executable output; more work, no gain.
- *Keep all three, "just fix paths"* — leaves three drifting definitions and three version numbers; the audit's exact complaint.

**For M14:** a small shared `src/paths.py` provides OS-aware writable directories; the logger is rewritten onto stdlib `logging` + `RotatingFileHandler`. Keeping the existing `StaXLogger` public surface means `init.py` / `menu.py` / `nuke_launcher.py` and ~120 call sites need **no changes**.

---

## 4. Detailed Design

### 4.1 Single-source version (`src/version.py`)

New module `src/version.py` is the sole source of truth:

```python
# src/version.py
__version__ = "0.1.0"

def get_version():
    """Return the canonical StaX version string (single source of truth)."""
    return __version__
```

- `src/__init__.py` re-exports it (`from version import __version__`, package-relative fallback) so `import src; src.__version__` keeps working.
- `pyproject.toml` stops hardcoding the version and declares it **dynamic**, read from `src/version.py` by hatchling:

  ```toml
  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [project]
  name = "StaX"
  dynamic = ["version"]
  # (no  version = "…"  literal)

  [tool.hatch.version]
  path = "src/version.py"

  [tool.hatch.build.targets.wheel]
  packages = ["src"]
  ```

- `setup_freeze.py`'s `_read_version()` already prefers `src/version.py`; it is simplified to read that file canonically (falling back to `pyproject.toml`'s dynamic marker is unnecessary once the file exists).
- `tools/build.ps1` and `tools/build_win_installer.ps1` already regex `src/version.py` for `__version__` (`build.ps1:97-102`), so they resolve the same string with no change.

Net: **one string**, consumed by the wheel metadata, the frozen `Executable(version=…)`, the Inno `AppVersion`, and the app at runtime.

### 4.2 Per-user path resolver (`src/paths.py`)

New module, stdlib-only, imported flat (`from paths import get_log_dir`):

```python
# src/paths.py
import os
import sys
import tempfile

APP_NAME = "StaX"


def _is_windows():
    return sys.platform.startswith("win")


def _user_base(kind):
    """Return the OS-appropriate base dir for 'state' | 'data' | 'config'."""
    if _is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
        return os.path.join(base, APP_NAME)
    home = os.path.expanduser("~")
    xdg = {
        "state":  os.environ.get("XDG_STATE_HOME")  or os.path.join(home, ".local", "state"),
        "data":   os.environ.get("XDG_DATA_HOME")   or os.path.join(home, ".local", "share"),
        "config": os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
    }[kind]
    return os.path.join(xdg, APP_NAME)


def _ensure_writable(path):
    """Create `path`; if that fails or it isn't writable, fall back under the temp dir."""
    try:
        os.makedirs(path, exist_ok=True)
        if os.access(path, os.W_OK):
            return path
    except OSError:
        pass
    fallback = os.path.join(tempfile.gettempdir(), APP_NAME, os.path.basename(path.rstrip("/\\")))
    os.makedirs(fallback, exist_ok=True)
    return fallback


def get_log_dir():
    """Per-user writable directory for StaX logs."""
    return _ensure_writable(os.path.join(_user_base("state"), "logs"))


def get_data_dir():
    """Per-user writable directory for the StaX database and previews."""
    return _ensure_writable(_user_base("data"))


def get_config_dir():
    """Per-user writable directory for StaX configuration."""
    return _ensure_writable(_user_base("config"))
```

Resolution summary:

| Purpose | Windows | Linux |
|---|---|---|
| Logs (`get_log_dir`) | `%LOCALAPPDATA%\StaX\logs` | `$XDG_STATE_HOME/StaX/logs` → `~/.local/state/StaX/logs` |
| Data / DB (`get_data_dir`) | `%LOCALAPPDATA%\StaX` | `$XDG_DATA_HOME/StaX` → `~/.local/share/StaX` |
| Config (`get_config_dir`) | `%LOCALAPPDATA%\StaX` | `$XDG_CONFIG_HOME/StaX` → `~/.config/StaX` |
| Fallback (any, if unwritable) | `%TEMP%\StaX\<name>` | `$TMPDIR/StaX/<name>` |

SP7 wires **`get_log_dir()`** into the logger. `get_data_dir()`/`get_config_dir()` are delivered and tested-adjacent but their consumers (`Config.database_path`, `debug_manager` config read) are a **documented follow-up** (§2 Non-Goals) so SP7 doesn't collide with SP1's DB work.

### 4.3 Rewritten logger (`stax_logger.py`)

Rewrite `StaXLogger` around stdlib `logging` while preserving the exact public surface used across the codebase (verified call sites: `debug`, `info`, `warning`, `error`, `critical`, `exception`, `separator`; module functions `get_logger()`, `init_logger(log_file=None)`):

- **Location:** log file is `os.path.join(get_log_dir(), "stax.log")` (fixed name, not timestamped).
- **Rotation:** `logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")` → at most `stax.log` + `stax.log.1..5` (~12 MB ceiling).
- **Console:** a `StreamHandler` on the original `sys.__stderr__` preserves today's "also print to console" behavior without going through the DebugManager stream proxy (avoids H8's stdout hijack swallowing logs).
- **Initialize once:** the underlying `logging.Logger` is fetched by name (`"stax"`); handlers are attached only if absent, so repeated `init_logger()`/`get_logger()` calls from the three entry points don't multiply handlers or files.
- **API shim:** `StaXLogger` becomes a thin adapter; `.separator()` logs a dashed rule; `.exception()` delegates to `logger.error(msg, exc_info=True)`.

### 4.4 cx_Freeze fixes (`setup_freeze.py`)

Two local edits (paths are already `__file__`-derived — no absolute-path change needed):

1. **Icon → `.ico`:** `_ICON = os.path.join(ROOT, "resources", "logo.png")` → `os.path.join(ROOT, "resources", "logo.ico")` (`setup_freeze.py:206`). The file `resources/logo.ico` already exists.
2. **Version source:** `_read_version()` reads `src/version.py` canonically (already its first candidate).

`pyproject.toml` gains a `build` extra so `uv sync --all-extras` installs the freezer:

```toml
[project.optional-dependencies]
build = ["cx-freeze>=7.2"]
# dev = [...]   # from SP0, retained
```

and drops the runtime `pyinstaller` dependency (no longer used by any surviving build path).

### 4.5 Deletions (M11 convergence)

| Delete | Why |
|---|---|
| `StaX.spec` | Absolute-path PyInstaller spec, not invoked by the shipping build |
| `tools/build_installer.py` | Regenerates a *different* PyInstaller spec at runtime; hardcodes version `1.0.0`; produces an NSIS path that competes with the Inno Setup installer |

The `pyinstaller` entry is removed from `[project].dependencies`.

### 4.6 Cross-platform build/run path (Linux)

The `.ps1` scripts are Windows-only. SP7 adds POSIX equivalents:

- **`tools/build.sh`** — mirrors `build.ps1`'s essentials: resolve repo root from `$0`, `uv sync --all-extras`, then `"$VENV/bin/python" setup_freeze.py build_exe` with `STAX_BUILD_OUT` set. Produces `build/StaX-<version>/` with a Linux ELF `StaX` binary.
- **`tools/run_standalone.sh`** — create/reuse `.venv` via `uv`/`python -m venv`, then `python main.py`.
- **Documented direct path** (no scripts needed): `python setup_freeze.py build_exe` to freeze, `python main.py` to run.

A **native Linux installer** (AppImage/.deb) is an explicit follow-up; the portable frozen dir + `run_standalone.sh` is the SP7 Linux deliverable.

### 4.7 Testing strategy

Packaging is largely un-unit-testable (a real freeze is slow and environment-heavy), so SP7 tests the *pure* pieces and statically asserts the build definition's hygiene:

- **`tests/unit/test_version.py`** — `src/version.py` returns a valid semver string; `get_version() == __version__`; `pyproject.toml` declares `dynamic = ["version"]` and contains **no** hardcoded `version = "…"` literal (proves the single source).
- **`tests/unit/test_paths.py`** — `get_log_dir()` monkeypatched per-OS (`paths._is_windows` + env) returns the expected `%LOCALAPPDATA%\StaX\logs` / `~/.local/state/StaX/logs` path, **creates** the directory, and the result is writable; the temp-dir fallback triggers when the base is unwritable.
- **`tests/unit/test_build_config.py`** — greps `setup_freeze.py` and asserts **no absolute drive path** (`[A-Za-z]:[\\/]`) remains, the icon reference ends in `.ico`, `StaX.spec` and `tools/build_installer.py` **no longer exist**, `pyproject.toml` has no `pyinstaller` dependency and lists `cx-freeze` in the `build` extra.
- A real freeze smoke check is marked `@pytest.mark.slow` / manual (runs `setup_freeze.py build_exe` and asserts the two executables appear) — **not** run in the default CI gate.

---

## 5. Testing Strategy for SP7 itself

`pytest -m "not manual and not slow"` must stay green on Windows + Linux (SP0's CI matrix). The three unit test files above are the acceptance signal: version single-sourced, log-dir resolver correct per-OS, and the build definition free of absolute paths with the PyInstaller files gone. The `slow` freeze test is a manual/local gate for a full build verification.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Switching `pyproject` to dynamic version + hatchling breaks `uv sync`/`uv pip install -e` | Pin the standard `hatchling` backend + `[tool.hatch.build.targets.wheel] packages = ["src"]`; the plan verifies `uv pip install -e ".[dev]"` and `python -c "import src; print(src.__version__)"` before commit |
| `cx-freeze` wheel unavailable for Python 3.9 on a runner | `cx-freeze>=7.2` ships 3.9 wheels for Win/Linux; the build extra is only needed for the (manual/slow) freeze job, not the default gate |
| `get_log_dir()` fallback masks a real permissions problem | Fallback logs a one-line warning to the console handler and is covered by an explicit unit test so the behavior is intentional, not silent |
| Rewritten logger changes output format and surprises log parsers | No machine parses these dev logs; the human-facing `[HH:MM:SS] [LEVEL] msg` shape is preserved by the formatter |
| Deleting `StaX.spec` / `build_installer.py` orphans a doc/README reference | The plan greps the repo for references and updates `README`/docs pointers to `build.ps1`/`build.sh` |

---

## 7. Deliverables Checklist
- [ ] `src/version.py` created; `src/__init__.py` re-exports it.
- [ ] `pyproject.toml`: dynamic version via hatchling; `pyinstaller` removed; `cx-freeze` in a `build` extra.
- [ ] `StaX.spec` and `tools/build_installer.py` deleted.
- [ ] `setup_freeze.py`: icon → `logo.ico`; version read from `src/version.py`.
- [ ] `src/paths.py` created (`get_log_dir`/`get_data_dir`/`get_config_dir` + fallback).
- [ ] `stax_logger.py` rewritten onto `logging` + `RotatingFileHandler`, writing to `get_log_dir()`, initialized once, same public API.
- [ ] `tools/build.sh` + `tools/run_standalone.sh` (Linux build/run path).
- [ ] Tests: `test_version.py`, `test_paths.py`, `test_build_config.py`; slow/manual freeze smoke.

---

## 8. Follow-on
- **SP8 (code quality)** removes the last Py2 shims and the dead orphan modules still referenced in `setup_freeze.py`'s `PACKAGES` list.
- **Config/DB relocation** (jointly with SP1): wire `Config.database_path` and the `config.json` read through `get_data_dir()` / `get_config_dir()` so a `%ProgramFiles%` install writes its DB and settings to a per-user location.
- **Native Linux installer** (AppImage/.deb) built from the SP7 portable freeze.
