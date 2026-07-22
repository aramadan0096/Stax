# SP7 — Build, Packaging & Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge StaX on **one packager (cx_Freeze)**, delete the two PyInstaller build definitions, single-source the version through `src/version.py`, fix the frozen Windows icon to `.ico`, move logs to a per-user writable directory with rotation (M14), and add a Linux build/run path — all TDD, with conventional commits.

**Architecture:** A new `src/version.py` is the single version source; `pyproject.toml` derives its version dynamically (hatchling) and declares `cx-freeze` (build extra) instead of `pyinstaller`. A new `src/paths.py` resolves per-user writable dirs (`%LOCALAPPDATA%\StaX` / XDG) with a temp-dir fallback. `stax_logger.py` is rewritten onto stdlib `logging` + `RotatingFileHandler` writing to `get_log_dir()`, keeping its public API. `StaX.spec` and `tools/build_installer.py` are removed; `setup_freeze.py` (already `__file__`-relative) gets the icon + version fixes. `tools/build.sh` + `tools/run_standalone.sh` provide the Linux path.

**Tech Stack:** Python 3.9, cx_Freeze (build), hatchling (metadata/version), stdlib `logging`, uv, pytest (SP0 harness), PowerShell (Windows scripts) + POSIX sh (Linux scripts), Inno Setup (Windows installer, unchanged).

## Global Constraints

- **Platforms:** Windows + Linux only (no macOS). Any path/binary logic branches on `sys.platform`.
- **Python:** 3.9 (`requires-python >=3.9`).
- **One packager only:** cx_Freeze via `setup_freeze.py`. No PyInstaller definition survives.
- **No absolute drive paths** in any surviving build definition — everything derives from `__file__`.
- **Single version source:** `src/version.py`. Nothing else hardcodes a version literal (`pyproject.toml` is `dynamic`).
- **Logging, not print** (locked). The logger uses stdlib `logging`; new code never uses bare `print`.
- **Flat imports:** `src/` is on `sys.path`; import new modules flat — `from version import get_version`, `from paths import get_log_dir`.
- **Preserve the logger's public API** — `debug/info/warning/error/critical/exception/separator`, `get_logger()`, `init_logger(log_file=None)` — so `init.py`/`menu.py`/`nuke_launcher.py` and ~120 call sites are untouched.
- **Do not rewire `Config`/`DatabaseManager` paths here** — that's a documented follow-up shared with SP1. SP7 wires only the logger to the resolver.

---

## Key signatures (verified against the codebase)

- **Logger public surface used across the repo** (verified): `StaXLogger.{debug,info,warning,error,critical,exception,separator}(message)`; module `get_logger()` (memoized singleton) and `init_logger(log_file=None)`; initialized at `init.py:62-63`, `menu.py:43-44`, `nuke_launcher.py:26-27`. Call-site counts: `info`×74, `exception`×30, `warning`×8, `error`×5, `critical`×2, `separator`×5.
- **Current version literals** (to be unified): `src/__init__.py:6` `__version__ = '0.1.0'`; `pyproject.toml:3` `version = "0.1.0"`; `tools/build_installer.py:22` `APP_VERSION = "1.0.0"` (deleted); `setup_freeze.py:55` fallback `"0.0.0"`.
- **cx_Freeze setup** (`setup_freeze.py`): `ROOT = os.path.dirname(os.path.abspath(__file__))`; `_read_version()` (`:40`) reads `main.py` → `src/version.py` → `pyproject.toml`; `_ICON = os.path.join(ROOT, "resources", "logo.png")` (`:206`); two `Executable(...)` entries → `StaX.exe` + `StaX_nuke_launcher.exe` (`:209-226`).
- **Build entrypoints already reading `src/version.py`:** `tools/build.ps1:97-102`, `tools/build_win_installer.ps1:99-105` (regex `__version__\s*=\s*"(?<v>[^"]+)"`). No change needed once the file exists.
- **Icon asset present:** `resources/logo.ico` and `resources/logo.png` both exist.
- **SP0 test harness:** `tests/conftest.py` puts repo-root + `src/` on `sys.path`; `tests/unit/` is the pure-logic tier; markers `unit`, `slow`, `manual` registered in `pytest.ini`.

---

## Task 1: Single-source the version (`src/version.py` + pyproject dynamic)

**Files:**
- Create: `src/version.py`
- Modify: `src/__init__.py`, `pyproject.toml`
- Test: `tests/unit/test_version.py` (new)

**Interfaces:**
- Produces: `get_version()` / `__version__` consumed by `setup_freeze.py`, the build scripts, and the app; `pyproject.toml` version derived dynamically from `src/version.py`.

- [ ] **Step 1: Write the failing version test**

Create `tests/unit/test_version.py`:

```python
import os
import re

import pytest

import version  # flat import: src/ is on sys.path (conftest)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PYPROJECT = os.path.join(_REPO_ROOT, "pyproject.toml")


@pytest.mark.unit
def test_version_is_semver_and_consistent():
    assert re.match(r"^\d+\.\d+\.\d+$", version.__version__), version.__version__
    assert version.get_version() == version.__version__


@pytest.mark.unit
def test_pyproject_version_is_single_sourced():
    text = open(_PYPROJECT, encoding="utf-8").read()
    # Version must be derived from src/version.py, not hardcoded.
    assert 'dynamic = ["version"]' in text
    # No literal  version = "x.y.z"  under [project]  (hatch uses  path = ...  instead).
    assert re.search(r'^\s*version\s*=\s*["\']', text, re.MULTILINE) is None
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_version.py -v`
Expected: FAIL/ERROR — `import version` fails (no `src/version.py`) and `pyproject.toml` still has `version = "0.1.0"`.

- [ ] **Step 3: Create `src/version.py`**

```python
# -*- coding: utf-8 -*-
"""Single source of truth for the StaX version.

Consumed by pyproject.toml (hatchling dynamic version), setup_freeze.py,
tools/build.ps1, tools/build_win_installer.ps1, and the running app.
"""

__version__ = "0.1.0"


def get_version():
    """Return the canonical StaX version string."""
    return __version__
```

- [ ] **Step 4: Re-export from `src/__init__.py`**

Replace `__version__ = '0.1.0'` in `src/__init__.py` with a re-export so `src.__version__` still resolves:

```python
# -*- coding: utf-8 -*-
"""
StaX - Advanced solution for mass production stock footage management
"""

try:
    from version import __version__          # flat (src/ on sys.path)
except ImportError:                          # imported as a package
    from .version import __version__

__author__ = 'Ahmed Ramadan'
```

- [ ] **Step 5: Make `pyproject.toml` version dynamic**

Add a `[build-system]` table at the top of `pyproject.toml`, change `[project]` to declare a dynamic version (delete the `version = "0.1.0"` line), and add the hatch version/wheel tables. The result (relevant parts):

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "StaX"
dynamic = ["version"]
description = "Open-source advanced solution for mass production stock footage management"
readme = "README.md"
requires-python = ">=3.9"
dependencies = [
    "ffpyplayer>=4.5.3",
    "flask>=3.1.3",
    "imagehash>=4.3.2",
    "numpy>=2.0.2",
    "opencv-python>=4.13.0.92",
    "pillow>=11.3.0",
    "pyside2>=5.15.2.1",
    "pytest>=8.4.2",
    "pytest-mock>=3.15.1",
]

[tool.hatch.version]
path = "src/version.py"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

(Note: `pyinstaller` is intentionally dropped from `dependencies` here — it is removed in Task 3. If SP0's `[project.optional-dependencies] dev = [...]` table is present, leave it untouched; Task 3 adds the `build` extra alongside it.)

- [ ] **Step 6: Verify the metadata still resolves and the test passes**

Run:
```bash
uv pip install -e "." && python -c "import src; print(src.__version__)"
python -c "import importlib.metadata as m; print(m.version('StaX'))"
pytest tests/unit/test_version.py -v
```
Expected: both `print`s emit `0.1.0`; `test_version.py` → 2 passed. If `uv pip install -e .` errors on the build backend, confirm `hatchling` resolved and `[tool.hatch.build.targets.wheel] packages = ["src"]` is present.

- [ ] **Step 7: Commit**

```bash
git add src/version.py src/__init__.py pyproject.toml tests/unit/test_version.py
git commit -m "build: single-source version via src/version.py and dynamic pyproject metadata"
```

---

## Task 2: Per-user path resolver (`src/paths.py`)

**Files:**
- Create: `src/paths.py`
- Test: `tests/unit/test_paths.py` (new)

**Interfaces:**
- Produces: `get_log_dir()` (consumed by the logger in Task 4), `get_data_dir()`, `get_config_dir()` (delivered for the SP1 follow-up).

- [ ] **Step 1: Write the failing resolver test**

Create `tests/unit/test_paths.py`:

```python
import os

import pytest

import paths  # flat import


@pytest.mark.unit
def test_log_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    local = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    d = paths.get_log_dir()
    assert d == os.path.join(str(local), "StaX", "logs")
    assert os.path.isdir(d)
    assert os.access(d, os.W_OK)


@pytest.mark.unit
def test_log_dir_linux_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    d = paths.get_log_dir()
    assert d == os.path.join(str(state), "StaX", "logs")
    assert os.path.isdir(d)


@pytest.mark.unit
def test_log_dir_linux_default_home(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    d = paths.get_log_dir()
    assert d == os.path.join(str(tmp_path), ".local", "state", "StaX", "logs")
    assert os.path.isdir(d)


@pytest.mark.unit
def test_data_and_config_dirs_created(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert os.path.isdir(paths.get_data_dir())
    assert os.path.isdir(paths.get_config_dir())
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_paths.py -v`
Expected: ERROR — no module `paths`.

- [ ] **Step 3: Create `src/paths.py`**

```python
# -*- coding: utf-8 -*-
"""OS-aware, per-user writable directories for StaX.

Frozen builds install under a read-only location (e.g. %ProgramFiles%\\StaX),
so logs, the database, and config must live in a per-user writable dir.

    Windows :  %LOCALAPPDATA%\\StaX\\{logs, ...}
    Linux   :  $XDG_STATE_HOME/StaX/logs, $XDG_DATA_HOME/StaX, $XDG_CONFIG_HOME/StaX
    Fallback:  %TEMP%/StaX/<name>   (when the preferred base is unwritable)
"""

import os
import sys
import tempfile

APP_NAME = "StaX"


def _is_windows():
    return sys.platform.startswith("win")


def _user_base(kind):
    """Base dir for kind in {'state', 'data', 'config'}."""
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
    """Create `path`; on failure or if not writable, fall back under the temp dir."""
    try:
        os.makedirs(path, exist_ok=True)
        if os.access(path, os.W_OK):
            return path
    except OSError:
        pass
    fallback = os.path.join(
        tempfile.gettempdir(), APP_NAME, os.path.basename(path.rstrip("/\\")) or APP_NAME
    )
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_paths.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/paths.py tests/unit/test_paths.py
git commit -m "feat: add per-user writable path resolver (paths.get_log_dir/data/config)"
```

---

## Task 3: Converge on cx_Freeze — delete PyInstaller, declare the freezer

**Files:**
- Delete: `StaX.spec`, `tools/build_installer.py`
- Modify: `pyproject.toml`, `setup_freeze.py`
- Test: `tests/unit/test_build_config.py` (new)

**Interfaces:**
- Consumes: `resources/logo.ico`, `src/version.py`.
- Produces: a single, absolute-path-free build definition (`setup_freeze.py`) with `cx-freeze` installable via `uv sync --all-extras`.

- [ ] **Step 1: Write the failing build-hygiene test**

Create `tests/unit/test_build_config.py`:

```python
import os
import re

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel):
    with open(os.path.join(_REPO_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.unit
def test_pyinstaller_definitions_are_deleted():
    assert not os.path.exists(os.path.join(_REPO_ROOT, "StaX.spec"))
    assert not os.path.exists(os.path.join(_REPO_ROOT, "tools", "build_installer.py"))


@pytest.mark.unit
def test_setup_freeze_has_no_absolute_drive_paths():
    text = _read("setup_freeze.py")
    # e.g. D:/... or C:\...  — none may survive; all paths derive from __file__.
    assert re.search(r"[A-Za-z]:[\\/]", text) is None


@pytest.mark.unit
def test_setup_freeze_uses_ico_icon():
    text = _read("setup_freeze.py")
    assert "logo.ico" in text
    assert "logo.png" not in text  # icon must not point at a PNG


@pytest.mark.unit
def test_pyproject_declares_cxfreeze_not_pyinstaller():
    text = _read("pyproject.toml")
    assert "pyinstaller" not in text.lower()
    assert "cx-freeze" in text.lower()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_build_config.py -v`
Expected: multiple FAIL — `StaX.spec`/`build_installer.py` still present; `setup_freeze.py` uses `logo.png`; `pyproject.toml` still lists `pyinstaller`, not `cx-freeze`.

- [ ] **Step 3: Delete the two PyInstaller definitions**

```bash
git rm StaX.spec tools/build_installer.py
```

- [ ] **Step 4: Fix the icon in `setup_freeze.py`**

Change `setup_freeze.py:206` from the PNG to the ICO:

```python
_ICON        = os.path.join(ROOT, "resources", "logo.ico")
_ICON        = _ICON if os.path.isfile(_ICON) else None
```

- [ ] **Step 5: Simplify the version read in `setup_freeze.py`**

Replace the body of `_read_version()` (`setup_freeze.py:40-55`) so `src/version.py` is the canonical source (keeping the `pyproject.toml` fallback for safety):

```python
def _read_version():
    """Read __version__ from the single source (src/version.py); fall back to pyproject.toml."""
    version_py = os.path.join(ROOT, "src", "version.py")
    if os.path.isfile(version_py):
        with open(version_py, encoding="utf-8") as fh:
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', fh.read())
            if m:
                return m.group(1)
    pyproject = os.path.join(ROOT, "pyproject.toml")
    if os.path.isfile(pyproject):
        with open(pyproject, encoding="utf-8") as fh:
            m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', fh.read(), re.MULTILINE)
            if m:
                return m.group(1)
    return "0.0.0"
```

- [ ] **Step 6: Declare `cx-freeze` and drop `pyinstaller` in `pyproject.toml`**

Remove `"pyinstaller>=6.19.0",` from `[project].dependencies` (already gone if Task 1 Step 5 rewrote the block), and add a `build` extra so `uv sync --all-extras` installs the freezer:

```toml
[project.optional-dependencies]
build = ["cx-freeze>=7.2"]
# dev = [ ... ]   # from SP0 — retain if present
```

- [ ] **Step 7: Run the hygiene test + confirm cx_Freeze installs**

Run:
```bash
pytest tests/unit/test_build_config.py -v
uv sync --all-extras
python -c "import cx_Freeze; print(cx_Freeze.__version__)"
```
Expected: `test_build_config.py` → 4 passed; `uv sync` completes; the last line prints a cx_Freeze version (≥7.2). If `uv sync` reports cx_Freeze missing, confirm the `build` extra is spelled `cx-freeze` (PyPI name) and re-run.

- [ ] **Step 8: Grep for stale references to the deleted files**

Run:
```bash
grep -rn "build_installer\|StaX\.spec" --include=*.md --include=*.ps1 --include=*.py . | grep -v docs/superpowers
```
Expected: no functional references remain (a historical mention in `STAX_AUDIT_REPORT.md` is fine). If `README.md` or a script points at `build_installer.py`, repoint it to `tools/build.ps1` / `tools/build.sh` in this commit.

- [ ] **Step 9: Commit**

```bash
git add -A pyproject.toml setup_freeze.py tests/unit/test_build_config.py
git commit -m "build: converge on cx_Freeze; delete PyInstaller specs; fix icon to .ico"
```

---

## Task 4: Rewrite the logger onto stdlib logging + rotation, writing per-user (M14)

**Files:**
- Modify (replace): `stax_logger.py`
- Test: `tests/unit/test_stax_logger.py` (new)

**Interfaces:**
- Consumes: `paths.get_log_dir()` (Task 2).
- Preserves: `StaXLogger.{debug,info,warning,error,critical,exception,separator}`, `get_logger()`, `init_logger(log_file=None)` — the surface `init.py`/`menu.py`/`nuke_launcher.py` and all call sites depend on.

- [ ] **Step 1: Write the failing logger test**

Create `tests/unit/test_stax_logger.py`:

```python
import os
import logging

import pytest

import stax_logger


@pytest.fixture(autouse=True)
def _reset_logger():
    # Ensure each test starts from a clean singleton + handler set.
    stax_logger._logger = None
    logging.getLogger("stax").handlers = []
    yield
    stax_logger._logger = None
    logging.getLogger("stax").handlers = []


@pytest.mark.unit
def test_logs_go_to_per_user_dir(monkeypatch, tmp_path):
    logdir = tmp_path / "stax-logs"
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(logdir))
    logdir.mkdir()
    log = stax_logger.init_logger()
    log.info("hello sp7")
    for h in logging.getLogger("stax").handlers:
        h.flush()
    logfile = logdir / "stax.log"
    assert logfile.is_file()
    assert "hello sp7" in logfile.read_text(encoding="utf-8")


@pytest.mark.unit
def test_public_api_methods_exist():
    log = stax_logger.get_logger()
    for name in ("debug", "info", "warning", "error", "critical", "exception", "separator"):
        assert callable(getattr(log, name))


@pytest.mark.unit
def test_initialized_once_does_not_duplicate_handlers(monkeypatch, tmp_path):
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(tmp_path))
    stax_logger.init_logger()
    n1 = len(logging.getLogger("stax").handlers)
    stax_logger.init_logger()   # re-init from a second entry point
    n2 = len(logging.getLogger("stax").handlers)
    assert n1 == n2  # no handler pile-up -> no second log file per process


@pytest.mark.unit
def test_uses_rotating_file_handler(monkeypatch, tmp_path):
    from logging.handlers import RotatingFileHandler
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(tmp_path))
    stax_logger.init_logger()
    handlers = logging.getLogger("stax").handlers
    assert any(isinstance(h, RotatingFileHandler) for h in handlers)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_stax_logger.py -v`
Expected: FAIL — the current logger has no `get_log_dir`, writes timestamped files next to the module, and isn't backed by `logging`.

- [ ] **Step 3: Replace `stax_logger.py`**

```python
# -*- coding: utf-8 -*-
"""
StaX Logger
===========
Centralized logging for StaX, built on stdlib ``logging``.

- Writes to a per-user writable directory (paths.get_log_dir()), NOT next to
  the module — so a frozen install under %ProgramFiles% still logs (fixes M14).
- Uses a RotatingFileHandler (fixed filename + rollover), so a fresh file is
  NOT created on every process start.
- Initialized once: the underlying logging.Logger('stax') gets its handlers
  attached a single time even when init.py / menu.py / nuke_launcher.py each
  call get_logger()/init_logger().
- Preserves the historical public API used across the codebase.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

try:
    from paths import get_log_dir          # flat (src/ on sys.path)
except ImportError:                         # imported as a package
    from src.paths import get_log_dir

_LOGGER_NAME = "stax"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


class StaXLogger(object):
    """Thin adapter over logging.Logger preserving StaX's historical API."""

    def __init__(self, log_file=None):
        self._log = logging.getLogger(_LOGGER_NAME)
        self._log.setLevel(logging.DEBUG)
        self._log.propagate = False
        self.log_file = log_file or os.path.join(get_log_dir(), "stax.log")
        self.enabled = True
        self._configure()

    def _configure(self):
        """Attach handlers once; safe to call repeatedly (idempotent)."""
        have_file = any(isinstance(h, RotatingFileHandler) for h in self._log.handlers)
        have_stream = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
            for h in self._log.handlers
        )
        fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")

        if not have_file:
            try:
                fh = RotatingFileHandler(
                    self.log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
                    encoding="utf-8",
                )
                fh.setFormatter(fmt)
                self._log.addHandler(fh)
            except OSError as exc:
                sys.__stderr__.write("[StaX Logger] file handler failed: {}\n".format(exc))

        if not have_stream:
            # Write to the ORIGINAL stderr, bypassing DebugManager's stream proxy.
            sh = logging.StreamHandler(sys.__stderr__)
            sh.setFormatter(fmt)
            self._log.addHandler(sh)

    # -- public API (unchanged surface) -------------------------------------
    def debug(self, message):    self._log.debug(message)
    def info(self, message):     self._log.info(message)
    def warning(self, message):  self._log.warning(message)
    def error(self, message):    self._log.error(message)
    def critical(self, message): self._log.critical(message)

    def exception(self, message):
        # Log with the active traceback, matching the old behavior.
        self._log.error(message, exc_info=True)

    def separator(self):
        self._log.info("-" * 80)


# --- module-level singleton (memoized, initialized once) --------------------
_logger = None


def get_logger():
    """Get or create the global StaX logger."""
    global _logger
    if _logger is None:
        _logger = StaXLogger()
    return _logger


def init_logger(log_file=None):
    """Initialize (or reconfigure) the global logger.

    Reuses the singleton so repeated calls from multiple entry points do not
    create duplicate handlers or a new file per process.
    """
    global _logger
    if _logger is None:
        _logger = StaXLogger(log_file)
    elif log_file is not None:
        _logger.log_file = log_file
        _logger._configure()
    return _logger
```

- [ ] **Step 4: Run the logger test to verify it passes**

Run: `pytest tests/unit/test_stax_logger.py -v`
Expected: 4 passed. If `test_uses_rotating_file_handler` fails because the file handler was skipped, confirm `get_log_dir()` was monkeypatched to a writable `tmp_path`.

- [ ] **Step 5: Smoke-check the three entry points still import cleanly**

Run:
```bash
python -c "import sys, os; sys.path.insert(0, 'src'); import stax_logger; l = stax_logger.init_logger(); l.info('ok'); l.separator(); l.warning('w'); print('logfile:', l.log_file)"
```
Expected: prints `logfile: <per-user dir>/stax.log` and the log lines to stderr; no exception. (`init.py`/`menu.py`/`nuke_launcher.py` use exactly these methods — no edits needed there.)

- [ ] **Step 6: Commit**

```bash
git add stax_logger.py tests/unit/test_stax_logger.py
git commit -m "fix: log to per-user dir with rotation, initialized once (M14)"
```

---

## Task 5: Linux build/run path

**Files:**
- Create: `tools/build.sh`, `tools/run_standalone.sh`

**Interfaces:**
- Consumes: `setup_freeze.py`, `src/version.py`, `uv`.
- Produces: `build/StaX-<version>/` (Linux portable) and a `python main.py` launcher on Linux.

- [ ] **Step 1: Create `tools/build.sh`**

```bash
#!/usr/bin/env bash
# Build a portable StaX with cx_Freeze on Linux.
# Mirrors tools/build.ps1's essentials. Full native installer (AppImage/.deb)
# is a documented follow-up.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stax_root="$(dirname "$script_dir")"
cd "$stax_root"

command -v uv >/dev/null 2>&1 || { echo "uv not found: https://github.com/astral-sh/uv"; exit 1; }

# Single-sourced version from src/version.py
version="$(python - <<'PY'
import re, io
m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', io.open("src/version.py", encoding="utf-8").read())
print(m.group(1) if m else "0.0.0")
PY
)"
echo ">>> StaX version: $version"

echo ">>> Syncing uv environment ..."
uv sync --all-extras

build_out="$stax_root/build/StaX-$version"
rm -rf "$build_out"
mkdir -p "$build_out"

echo ">>> Building StaX with cx_Freeze ..."
STAX_BUILD_OUT="$build_out" .venv/bin/python setup_freeze.py build_exe

echo "*** Portable build: $build_out"
```

- [ ] **Step 2: Create `tools/run_standalone.sh`**

```bash
#!/usr/bin/env bash
# Create/reuse a .venv and run StaX directly on Linux.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(dirname "$script_dir")"
cd "$repo_root"

venv_dir="$repo_root/.venv"
if [ ! -x "$venv_dir/bin/python" ]; then
    echo "[info] creating venv at $venv_dir"
    if command -v uv >/dev/null 2>&1; then
        uv venv --python 3.9 "$venv_dir"
        uv pip install --python "$venv_dir/bin/python" -e .
    else
        python3 -m venv "$venv_dir"
        "$venv_dir/bin/python" -m pip install -e .
    fi
fi

echo "[info] launching StaX"
exec "$venv_dir/bin/python" main.py
```

- [ ] **Step 3: Make them executable and syntax-check**

Run:
```bash
chmod +x tools/build.sh tools/run_standalone.sh
bash -n tools/build.sh && bash -n tools/run_standalone.sh && echo "sh syntax ok"
```
Expected: prints `sh syntax ok`. (On a Windows-only dev box without bash, skip the run and rely on CI's Linux job; note it in the commit.)

- [ ] **Step 4: Commit**

```bash
git add tools/build.sh tools/run_standalone.sh
git commit -m "build: add Linux build.sh and run_standalone.sh (cx_Freeze portable + direct run)"
```

---

## Task 6: Full-build smoke test (slow / manual) + suite green

**Files:**
- Create: `tests/manual/test_freeze_smoke.py` (collected only when explicitly selected)

**Interfaces:**
- Consumes: `setup_freeze.py`. Not part of the default CI gate.

- [ ] **Step 1: Write the slow freeze smoke test**

Create `tests/manual/test_freeze_smoke.py`:

```python
"""Real cx_Freeze build smoke test. Slow; excluded from the default gate.

Run explicitly:  pytest tests/manual/test_freeze_smoke.py -m slow --override-ini="testpaths=tests/manual"
"""
import os
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.slow
def test_cx_freeze_build_produces_executables(tmp_path):
    pytest.importorskip("cx_Freeze")
    env = dict(os.environ, STAX_BUILD_OUT=str(tmp_path / "StaX-build"))
    proc = subprocess.run(
        [sys.executable, "setup_freeze.py", "build_exe"],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=1800,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = tmp_path / "StaX-build"
    names = {p.name.lower() for p in out.iterdir()}
    exe = ".exe" if sys.platform.startswith("win") else ""
    assert ("stax" + exe) in names
    assert ("stax_nuke_launcher" + exe) in names
```

- [ ] **Step 2: Confirm it is NOT collected by the default gate**

Run: `pytest -m "not manual and not slow" --collect-only -q | grep -c freeze_smoke || true`
Expected: `0` — `tests/manual/` is outside `testpaths` and the test is `slow`. It runs only when explicitly targeted.

- [ ] **Step 3: Run the whole default suite**

Run: `pytest -m "not manual and not slow"`
Expected: all SP7 unit tests pass (`test_version`, `test_paths`, `test_build_config`, `test_stax_logger`) alongside the existing SP0 suite; **0 failed, 0 errored**.

- [ ] **Step 4: (Optional, local) run the real freeze**

Run: `pytest tests/manual/test_freeze_smoke.py -m slow --override-ini="testpaths=tests/manual"`
Expected: builds `build/StaX-<version>/` containing `StaX(.exe)` and `StaX_nuke_launcher(.exe)`. If cx_Freeze is absent the test skips; if the build fails, read `proc.stderr` — do not weaken the assertions.

- [ ] **Step 5: Commit**

```bash
git add tests/manual/test_freeze_smoke.py
git commit -m "test: add slow/manual cx_Freeze build smoke test"
```

---

## Self-Review

**1. Spec coverage:**
- Converge on one packager (cx_Freeze) + delete PyInstaller defs → Task 3 ✓
- No absolute paths in the surviving build def (verified by test) → Task 3 (`test_build_config`) ✓
- Fix frozen icon to `.ico` → Task 3 Step 4 ✓
- Declare `cx-freeze`, drop `pyinstaller` → Task 3 Steps 6-7 ✓
- Single-source version (`src/version.py`, dynamic pyproject) → Task 1 ✓
- Per-user writable log dir + rotation + init-once (M14) → Tasks 2 + 4 ✓
- `get_data_dir`/`get_config_dir` delivered for the SP1 follow-up → Task 2 ✓
- Linux build/run path → Task 5 ✓
- Tests: version source, per-OS log-dir resolver, no-absolute-paths grep; real build marked slow/manual → Tasks 1,2,3,6 ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every step ships complete code and exact commands with expected output. Fallbacks (e.g. skip `bash -n` on Windows, cx_Freeze `importorskip`) name the exact alternative.

**3. Type/name consistency:** `get_log_dir()` is defined in `paths.py` (Task 2) and consumed in `stax_logger.py` (Task 4) under the same name; the logger test monkeypatches `stax_logger.get_log_dir` (the name imported into the module). `get_version()`/`__version__` in `src/version.py` (Task 1) match the `setup_freeze._read_version()` regex and the build scripts' regex. `Executable(... target_name="StaX.exe"/"StaX_nuke_launcher.exe")` matches the freeze smoke test's expected names. The `build` extra name `cx-freeze` (PyPI) matches `uv sync --all-extras` in `build.ps1`/`build.sh`.

---

## Notes for the executor
- **Do not touch `Config` / `DatabaseManager` path defaults.** SP7 wires only the logger to `paths`. Moving the DB/config to `get_data_dir()`/`get_config_dir()` is the SP1-joint follow-up recorded in the spec.
- **Preserve the logger's public API exactly.** If a call site uses a method not on the adapter, add the method to `StaXLogger` — never edit the 120+ call sites or the three entry points.
- Run `pytest -m "not manual and not slow"` before every commit.
- If `uv`'s default build backend already worked without `[build-system]`, still add the explicit `hatchling` table — the dynamic version source depends on `[tool.hatch.version]`.
- Keep commits conventional and scoped: `build:` for packaging/deps, `feat:` for `paths.py`, `fix:` for the M14 logger, `test:` for the smoke test.
