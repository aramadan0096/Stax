# SP8 — Code Quality & Consistency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the L10 duplication (one `resolve_path`, one `human_size`, one dark palette, one bulk-menu builder) and establish the L4 error-handling pattern (narrowed `except` → `logging`) on a bounded set of the worst offenders — **cleanup only, no behavior changes beyond error-handling/logging**, with every extraction proven behavior-preserving by a test.

**Architecture:** New `src/utils/` package (`paths.py`, `formatting.py`). Migrate the 4 `_resolve_path`/`_resolve_storage_path` copies and the 3 file-size formatters onto the shared helpers, per-call-site params reproducing each prior branch. Delete `main.py._apply_fallback_palette`, calling `src/dark_palette.py::apply_dark_palette` directly. Extract a single bulk-menu builder on `MediaDisplayWidget`. Convert 6 enumerated exception-swallowing sites to `logging`. The god-module split is **deferred** (design §4.6) — not in this plan.

**Tech Stack:** Python 3.9, pytest, pytest-qt (offscreen), PySide2, stdlib `logging`, the SP0 fixtures (`stax_db`, `stax_config`, `mock_nuke`).

## Global Constraints

- **Cleanup only.** No functional/behavior change beyond error-handling/logging. The full SP0 suite (`pytest -m "not manual"`) must stay green after **every** task.
- **Platforms:** Windows + Linux. Python 3.9.
- **Imports:** match the file you edit. `media_display_widget.py`, `media_info_popup.py`, `video_player_widget.py`, `drag_gallery_view.py`, `main.py` all use `from src.xxx import ...`; use `from src.utils.paths import resolve_path` there. Tests use flat imports (`from utils.paths import resolve_path`), matching SP0 test style — both repo-root and `src/` are on `sys.path` via `conftest.py`.
- **Logging, not print.** New/converted error paths use `logging.getLogger(__name__)`; never `print`, never bare `except:`.
- **Do not touch code owned by other SPs:** the `is_admin` parent-lookup line (M3/SP6), the `gif_movies` lifecycle (M5/SP6), the drop-ingest handlers (H7/SP6), `nuke_bridge._resolve_storage_path` (SP5). Preserve them verbatim.
- **Commits:** conventional prefixes (`refactor:`, `test:`, `fix:`), one concern per commit. Do **not** edit `docs/superpowers/IMPLEMENTATION_PROGRESS.md`.

---

## Key signatures (verified against the codebase)

- Simple `_resolve_path(self, path)` — strip; `None`/empty→`None`; `isabs`→`normpath`; else `normpath(join(self._project_root, path))`. Copies at `src/ui/media_display_widget.py:1091`, `src/ui/media_info_popup.py:510`, `src/video_player_widget.py:618`. All three `self._project_root` resolve to the repo root (`media_display_widget.py:48`, `media_info_popup.py:34`, `video_player_widget.py:322`).
- Storage `_resolve_storage_path(self, path_value)` — `None`/empty→`None`; `isabs`→`normpath`; else `config.resolve_path(path)` if `self.config` else project-root join. `src/ui/drag_gallery_view.py:26` (project_root at `:22`).
- `Config.resolve_path(path, ensure_dir=False, treat_as_dir=None)` → normalized path rooted at `self.root_dir`, or `None` for falsy input (`src/config.py:289`).
- `Config(config_path='./config/config.json')`; `.get`, `.get_all`, `.set`; loads on construction; `.load()` at `src/config.py:141`, `.save()` at `:154` (both `print` on failure).
- File-size formatters: `media_display_widget.py:707-714` (table), `media_info_popup.py:286-296`, `video_player_widget.py:672-684` and `:919-924`.
- `apply_dark_palette(app)` — `src/dark_palette.py:28`. `_apply_fallback_palette(app)` — `main.py:793` (missing `LinkVisited`; delete). Call site `main.py:842-846`.
- Bulk menus in `MediaDisplayWidget`: `show_context_menu` multi-select branch `src/ui/media_display_widget.py:1128-1167`; `show_bulk_menu` `:1334-1370`. Dispatch targets `bulk_add_to_favorites`/`bulk_add_to_playlist`/`bulk_mark_deprecated`/`bulk_delete`. `get_icon` already imported.
- `MediaDisplayWidget(db_manager, config, nuke_bridge, main_window=None, parent=None)` (`src/ui/media_display_widget.py:24`).
- `db_manager.get_connection` cleanup bare excepts: `src/db_manager.py:172-173, 180-181`.
- `ingest_file` outer catch `src/ingestion_core.py:902`; Blender idle `except Exception: pass` `:506-507`.
- Analytics swallow `main.py:646-647`. `main.py` already imports `logging` (`:20`).

---

## Task 1: Create `src/utils/` package + `resolve_path` (unit-tested)

**Files:**
- Create: `src/utils/__init__.py`, `src/utils/paths.py`
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Produces: `resolve_path(path, project_root=None, config=None)` consumed by Task 2's call-site migration.

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_paths.py`:

```python
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
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/unit/test_paths.py -v`
Expected: ERROR/collection failure — `utils.paths` does not exist yet.

- [ ] **Step 3: Create the package + helper**

Create `src/utils/__init__.py` (empty file):

```python
# -*- coding: utf-8 -*-
```

Create `src/utils/paths.py`:

```python
# -*- coding: utf-8 -*-
"""Shared path helpers (consolidates the former per-widget _resolve_path copies)."""

import os


def resolve_path(path, project_root=None, config=None):
    """Resolve a stored (possibly relative) asset path to an absolute filesystem path.

    Args:
        path (str | None): Stored path. Empty / whitespace-only returns None.
        project_root (str | None): Root to join relative paths against.
        config (Config | None): If given and the path is relative, ``config.resolve_path``
            is consulted first (used by the drag/storage call site).

    Returns:
        str | None: A normalized absolute path, or None for falsy input.
    """
    if not path:
        return None
    path = path.strip()
    if not path:
        return None
    if os.path.isabs(path):
        return os.path.normpath(path)
    if config is not None:
        resolved = config.resolve_path(path)
        if resolved:
            return os.path.normpath(resolved)
    if project_root:
        return os.path.normpath(os.path.join(project_root, path))
    return os.path.normpath(path)
```

- [ ] **Step 4: Run it — confirm it passes**

Run: `pytest tests/unit/test_paths.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/utils/__init__.py src/utils/paths.py tests/unit/test_paths.py
git commit -m "refactor: add src/utils.paths.resolve_path shared helper with unit tests"
```

---

## Task 2: Migrate the 4 `_resolve_path` copies onto the shared helper

**Files:**
- Modify: `src/ui/media_display_widget.py`, `src/ui/media_info_popup.py`, `src/video_player_widget.py`, `src/ui/drag_gallery_view.py`

**Interfaces:**
- Consumes: `resolve_path` from Task 1.

- [ ] **Step 1: `media_display_widget.py` — import + replace the method body**

Add to the `from src.` import block near the top:

```python
from src.utils.paths import resolve_path
```

Replace the method at `:1091-1100`:

```python
    def _resolve_path(self, path):
        """Convert stored relative paths to absolute paths rooted at the project."""
        return resolve_path(path, project_root=self._project_root)
```

(Keep the method as a thin wrapper so the ~6 internal `self._resolve_path(...)` call sites are untouched.)

- [ ] **Step 2: `media_info_popup.py` — same**

Add `from src.utils.paths import resolve_path` to its import block, and replace `:510-519`:

```python
    def _resolve_path(self, path):
        """Resolve project-relative paths to absolute ones for file access."""
        return resolve_path(path, project_root=self._project_root)
```

- [ ] **Step 3: `video_player_widget.py` — same**

Add `from src.utils.paths import resolve_path` (next to `from src.icon_loader import get_pixmap`), and replace `:618-627`:

```python
    def _resolve_path(self, path):
        """Resolve stored relative paths against the project root."""
        return resolve_path(path, project_root=self._project_root)
```

- [ ] **Step 4: `drag_gallery_view.py` — storage variant (with config)**

Add `from src.utils.paths import resolve_path` (next to `from src.ingestion_core import SequenceDetector`), and replace `:26-35`:

```python
    def _resolve_storage_path(self, path_value):
        return resolve_path(path_value, project_root=self._project_root, config=self.config)
```

- [ ] **Step 5: Write the characterization test**

Create `tests/gui/test_resolve_path_widgets.py` (gui tier: these widgets pull in Qt):

```python
import os
import pytest

from utils.paths import resolve_path


@pytest.mark.gui
def test_widget_wrapper_matches_shared_helper(tmp_path, stax_config, mock_nuke):
    """The widget wrappers must produce exactly what the shared helper produces."""
    from nuke_bridge import NukeBridge
    from ui.media_display_widget import MediaDisplayWidget

    w = MediaDisplayWidget(None, stax_config, NukeBridge(mock_mode=True))
    rel = os.path.join("previews", "a.png")
    assert w._resolve_path(rel) == resolve_path(rel, project_root=w._project_root)
    assert w._resolve_path(None) is None
    ap = os.path.abspath(str(tmp_path / "b.png"))
    assert w._resolve_path(ap) == os.path.normpath(ap)
```

- [ ] **Step 6: Run the characterization test + full suite**

Run: `pytest tests/gui/test_resolve_path_widgets.py -v`
Expected: PASS. If `MediaDisplayWidget(None, ...)` raises during construction (needs a real db for something in `__init__`), pass `stax_db` as the first arg instead of `None` and note it.

Run: `pytest -m "not manual"`
Expected: 0 failed, 0 errored (xfail count unchanged from SP0/earlier SPs).

- [ ] **Step 7: Commit**

```bash
git add src/ui/media_display_widget.py src/ui/media_info_popup.py src/video_player_widget.py src/ui/drag_gallery_view.py tests/gui/test_resolve_path_widgets.py
git commit -m "refactor: replace 4 _resolve_path copies with src/utils.paths.resolve_path"
```

---

## Task 3: `human_size` helper + migrate the 3 file-size formatters

**Files:**
- Create: `src/utils/formatting.py`
- Test: `tests/unit/test_formatting.py`
- Modify: `src/ui/media_display_widget.py`, `src/ui/media_info_popup.py`, `src/video_player_widget.py`

**Interfaces:**
- Produces: `human_size(num_bytes)`.

- [ ] **Step 1: Write the failing boundary test**

Create `tests/unit/test_formatting.py`:

```python
import pytest

from utils.formatting import human_size


@pytest.mark.unit
@pytest.mark.parametrize("num_bytes,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1023, "1023 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1048576, "1.0 MB"),
    (5 * 1048576, "5.0 MB"),          # reproduces old >=1MB output
    (2 * 1024 ** 3, "2.0 GB"),        # reproduces old GB output
    (512 * 1024, "512.0 KB"),         # documented sub-MB refinement (was "0.5 MB")
])
def test_boundaries(num_bytes, expected):
    assert human_size(num_bytes) == expected


@pytest.mark.unit
def test_non_numeric_is_safe():
    assert human_size(None) == "0 B"
    assert human_size("bad") == "0 B"
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/unit/test_formatting.py -v`
Expected: ERROR — `utils.formatting` does not exist.

- [ ] **Step 3: Create the helper**

Create `src/utils/formatting.py`:

```python
# -*- coding: utf-8 -*-
"""Shared human-readable formatting helpers."""


def human_size(num_bytes):
    """Format a byte count as a human-readable string (B / KB / MB / GB / TB)."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    if size < 0:
        size = 0.0
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            if unit == "B":
                return "{:.0f} {}".format(size, unit)
            return "{:.1f} {}".format(size, unit)
        size /= 1024.0
    return "{:.1f} TB".format(size)
```

- [ ] **Step 4: Run it — confirm it passes**

Run: `pytest tests/unit/test_formatting.py -v`
Expected: PASS (11 passed).

- [ ] **Step 5: Migrate `media_display_widget.py` (table, `:707-714`)**

Add `from src.utils.formatting import human_size` to the import block. Replace:

```python
            size_str = ''
            if element.get('file_size'):
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
```

with:

```python
            size_str = human_size(element['file_size']) if element.get('file_size') else ''
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
```

- [ ] **Step 6: Migrate `media_info_popup.py` (`:286-296`)**

Add `from src.utils.formatting import human_size` to the import block. Replace:

```python
        file_size = element_data.get('file_size', 0)
        if file_size:
            size_mb = file_size / (1024.0 * 1024.0)
            if size_mb < 1024:
                size_str = "{:.1f} MB".format(size_mb)
            else:
                size_str = "{:.2f} GB".format(size_mb / 1024.0)
        else:
            size_str = 'N/A'
        self.size_label.setText(size_str)
```

with:

```python
        file_size = element_data.get('file_size', 0)
        size_str = human_size(file_size) if file_size else 'N/A'
        self.size_label.setText(size_str)
```

- [ ] **Step 7: Migrate `video_player_widget.py` (both spots)**

Add `from src.utils.formatting import human_size` to the import block.

At `:676-685` replace the `size_mb = size_bytes / (1024.0 * 1024.0) ...` computation and the `" ({:.2f} MB)".format(size_mb)` status suffix so it reads:

```python
            ok, load_message = self.geometry_viewer.load_geometry(geometry_path)
            if not ok:
                status = load_message or "Unable to load GLB preview."
                self.geometry_status_label.setText(status)
            else:
                status = "GLB preview ready: {}".format(display_name)
                if size_bytes:
                    status += " ({})".format(human_size(size_bytes))
                self.geometry_status_label.setText(status)
```

At `:919-924` replace:

```python
            size_mb = file_size / (1024.0 * 1024.0)
            metadata_lines.append("<b>File Size:</b> {:.2f} MB".format(size_mb))
```

with:

```python
            metadata_lines.append("<b>File Size:</b> {}".format(human_size(file_size)))
```

(Verify the surrounding `if file_size:` / `if size_bytes:` guards remain so the "no size" paths are unchanged.)

- [ ] **Step 8: Run the full suite**

Run: `pytest -m "not manual"`
Expected: 0 failed, 0 errored.

- [ ] **Step 9: Commit**

```bash
git add src/utils/formatting.py tests/unit/test_formatting.py src/ui/media_display_widget.py src/ui/media_info_popup.py src/video_player_widget.py
git commit -m "refactor: replace 3 file-size formatters with src/utils.formatting.human_size"
```

---

## Task 4: Consolidate the dark palette to `src/dark_palette.py`

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `apply_dark_palette` (`src/dark_palette.py:28`).

- [ ] **Step 1: Delete the duplicate + hoist the import**

Delete the whole `_apply_fallback_palette` function (`main.py:793-823`).

Add to `main.py`'s top-level `from src.` imports (near `from src.icon_loader import get_icon`):

```python
from src.dark_palette import apply_dark_palette
```

- [ ] **Step 2: Replace the call site (`main.py:842-846`)**

Replace:

```python
    # STEP 2 — Dark palette (MUST be before any widget construction and before QSS)
    try:
        from src.dark_palette import apply_dark_palette
        apply_dark_palette(app)
    except ImportError:
        _apply_fallback_palette(app)
```

with:

```python
    # STEP 2 — Dark palette (MUST be before any widget construction and before QSS)
    try:
        apply_dark_palette(app)
    except Exception:
        logging.getLogger(__name__).exception("Failed to apply dark palette; using default")
```

- [ ] **Step 3: Verify no dangling reference**

Run:
```bash
grep -n "_apply_fallback_palette" main.py
```
Expected: no output (the function and its only caller are both gone).

- [ ] **Step 4: Run the MainWindow smoke + full suite**

Run: `pytest tests/gui/test_mainwindow_smoke.py -v`
Expected: PASS (MainWindow still constructs; palette applied from the single source).

Run: `pytest -m "not manual"`
Expected: 0 failed, 0 errored.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "refactor: consolidate dark palette to src/dark_palette.py, drop main.py fallback copy"
```

---

## Task 5: Single bulk-menu builder in `MediaDisplayWidget`

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_bulk_menu.py`

**Interfaces:**
- Produces: `_populate_bulk_menu` / `_dispatch_bulk_action`, used by `show_context_menu` and `show_bulk_menu`.

- [ ] **Step 1: Add the two builder methods**

Add these methods to `MediaDisplayWidget` (e.g. just above `show_bulk_menu` at `:1334`):

```python
    def _populate_bulk_menu(self, menu, selected_ids, is_admin, with_header):
        """Add the shared bulk-operation actions to `menu`; return {name: QAction}."""
        if with_header:
            header_label = QtWidgets.QLabel("  {} items selected  ".format(len(selected_ids)))
            header_label.setStyleSheet("font-weight: bold; color: #16c6b0; padding: 5px;")
            header_action = QtWidgets.QWidgetAction(self)
            header_action.setDefaultWidget(header_label)
            menu.addAction(header_action)
            menu.addSeparator()
        actions = {}
        actions['fav'] = menu.addAction(get_icon('favorite', size=16), "Add All to Favorites")
        actions['playlist'] = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")
        menu.addSeparator()
        actions['deprecate'] = menu.addAction(get_icon('deprecated', size=16), "Mark All as Deprecated")
        actions['delete'] = menu.addAction(get_icon('delete', size=16), "Delete All Selected")
        if not is_admin:
            actions['deprecate'].setEnabled(False)
            actions['delete'].setEnabled(False)
        return actions

    def _dispatch_bulk_action(self, action, actions, selected_ids):
        """Route a chosen bulk QAction to its handler."""
        if action == actions['fav']:
            self.bulk_add_to_favorites(selected_ids)
        elif action == actions['playlist']:
            self.bulk_add_to_playlist(selected_ids)
        elif action == actions['deprecate']:
            self.bulk_mark_deprecated(selected_ids)
        elif action == actions['delete']:
            self.bulk_delete(selected_ids)
```

- [ ] **Step 2: Rewrite the `show_context_menu` multi-select branch (`:1128-1167`)**

Replace the whole `if len(selected_ids) > 1:` block body with:

```python
        # If multiple items selected, show bulk operations menu
        if len(selected_ids) > 1:
            actions = self._populate_bulk_menu(menu, selected_ids, is_admin, with_header=True)
            action = menu.exec_(position)
            self._dispatch_bulk_action(action, actions, selected_ids)
```

Leave the `is_admin = bool(getattr(parent_widget, 'is_admin', False))` line (`:1126`) **exactly as it is** (M3 is SP6's fix).

- [ ] **Step 3: Rewrite `show_bulk_menu` (`:1343-1370`)**

Replace the menu construction + dispatch (keep the empty-selection guard and `menu = QtWidgets.QMenu(self)`):

```python
        # Create menu
        menu = QtWidgets.QMenu(self)
        actions = self._populate_bulk_menu(menu, selected_ids, is_admin=True, with_header=False)
        action = menu.exec_(QtGui.QCursor.pos())
        self._dispatch_bulk_action(action, actions, selected_ids)
```

(`is_admin=True` reproduces the prior behavior where `show_bulk_menu` never disabled deprecate/delete.)

- [ ] **Step 4: Write the characterization test**

Create `tests/gui/test_bulk_menu.py`:

```python
import pytest

from PySide2 import QtWidgets


def _widget(stax_db, stax_config, mock_nuke):
    from nuke_bridge import NukeBridge
    from ui.media_display_widget import MediaDisplayWidget
    return MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))


@pytest.mark.gui
def test_bulk_menu_actions_and_admin_gating(stax_db, stax_config, mock_nuke):
    w = _widget(stax_db, stax_config, mock_nuke)

    menu = QtWidgets.QMenu()
    actions = w._populate_bulk_menu(menu, [1, 2, 3], is_admin=True, with_header=False)
    texts = {menu_action.text() for menu_action in menu.actions() if menu_action.text()}
    assert "Add All to Favorites" in texts
    assert "Add All to Playlist..." in texts
    assert "Mark All as Deprecated" in texts
    assert "Delete All Selected" in texts
    assert actions['deprecate'].isEnabled() and actions['delete'].isEnabled()

    # Non-admin disables destructive actions
    menu2 = QtWidgets.QMenu()
    actions2 = w._populate_bulk_menu(menu2, [1, 2], is_admin=False, with_header=False)
    assert not actions2['deprecate'].isEnabled()
    assert not actions2['delete'].isEnabled()
    assert actions2['fav'].isEnabled()  # non-destructive stays enabled


@pytest.mark.gui
def test_bulk_menu_header_only_when_requested(stax_db, stax_config, mock_nuke):
    w = _widget(stax_db, stax_config, mock_nuke)
    with_header = QtWidgets.QMenu()
    w._populate_bulk_menu(with_header, [1, 2], is_admin=True, with_header=True)
    without = QtWidgets.QMenu()
    w._populate_bulk_menu(without, [1, 2], is_admin=True, with_header=False)
    # header adds one QWidgetAction + a separator, so more total actions
    assert len(with_header.actions()) == len(without.actions()) + 2
```

- [ ] **Step 5: Run the test + full suite**

Run: `pytest tests/gui/test_bulk_menu.py -v`
Expected: PASS (2 passed). If `MediaDisplayWidget(stax_db, ...)` construction fails for an unrelated reason, reuse whatever construction the existing `tests/gui/test_mainwindow_smoke.py` proves works and note it.

Run: `pytest -m "not manual"`
Expected: 0 failed, 0 errored.

- [ ] **Step 6: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_bulk_menu.py
git commit -m "refactor: single bulk-menu builder shared by context and toolbar bulk menus"
```

---

## Task 6: L4 — error-handling pattern + bounded application

**Files:**
- Modify: `src/config.py`, `src/db_manager.py`, `src/ingestion_core.py`, `src/video_player_widget.py`, `main.py`
- Test: `tests/unit/test_config_logging.py`

**Interfaces:**
- Establishes: `logger = logging.getLogger(__name__)` + narrowed `except` → `logger.exception/warning/debug`, preserving each existing fallback value.

- [ ] **Step 1: Write the failing `caplog` test**

Create `tests/unit/test_config_logging.py`:

```python
import logging
import pytest

from config import Config


@pytest.mark.unit
def test_malformed_config_logs_and_keeps_defaults(tmp_path, caplog, monkeypatch):
    monkeypatch.delenv("STOCK_DB", raising=False)
    bad = tmp_path / "config.json"
    bad.write_text("{ this is not valid json ")
    with caplog.at_level(logging.ERROR):
        cfg = Config(config_path=str(bad))
    # It logged the failure (no longer swallowed to stdout only)...
    assert any("config" in rec.message.lower() for rec in caplog.records)
    # ...and returned a safe, usable config (defaults intact).
    assert isinstance(cfg.get_all(), dict)


@pytest.mark.unit
def test_save_failure_logs_without_raising(tmp_path, caplog, monkeypatch):
    monkeypatch.delenv("STOCK_DB", raising=False)
    cfg = Config(config_path=str(tmp_path / "config.json"))
    # Point the path at a directory so the file open for write fails.
    dir_as_path = tmp_path / "adir"
    dir_as_path.mkdir()
    cfg.config_path = str(dir_as_path)
    with caplog.at_level(logging.ERROR):
        cfg.save()  # must not raise
    assert any("config" in rec.message.lower() for rec in caplog.records)
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/unit/test_config_logging.py -v`
Expected: FAIL — `config.py` currently `print`s (not `logging`), so `caplog.records` is empty.

- [ ] **Step 3: Convert `src/config.py` to logging**

Add after the existing imports (`:8-10`):

```python
import logging

logger = logging.getLogger(__name__)
```

Replace the failure `print`s in `load()` (`:150,152`), `save()` (`:165,167`), and the `[Config]` status/warning prints in `_load_from_database`/`_save_to_database`/`ensure_directories`:
- `print("Failed to load configuration: {}".format(e))` → `logger.exception("Failed to load configuration from %s", self.config_path)`
- `print("Failed to save configuration: {}".format(e))` → `logger.exception("Failed to save configuration to %s", self.config_path)`
- informational `print(...)` (loaded/saved/creating-directory) → `logger.info(...)` with the same message
- the two `[Config] Warning: Could not ... settings from/to database` → `logger.warning(...)`
- the `[WARN] Failed to create directory` → `logger.warning(...)`

Keep every `except Exception as e:` narrowed as-is (they already catch `Exception`, not bare) and keep all existing return/fallback behavior unchanged.

- [ ] **Step 4: Run the caplog test — confirm it passes**

Run: `pytest tests/unit/test_config_logging.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Fix `db_manager.get_connection` cleanup bare excepts (`:172-173,180-181`)**

Add near the top of `src/db_manager.py` imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Replace both cleanup blocks:

```python
            if conn:
                try:
                    conn.close()
                    self._log("Connection closed")
                except Exception:
                    logger.debug("Error closing DB connection", exc_info=True)

            if file_lock:
                try:
                    file_lock.release()
                    self._log("File lock released")
                except Exception:
                    logger.debug("Error releasing file lock", exc_info=True)
```

- [ ] **Step 6: Surface the masked error in `ingest_file` (`:902`) + Blender idle (`:506-507`)**

Add to `src/ingestion_core.py` imports:

```python
import logging

logger = logging.getLogger(__name__)
```

At `:902`, add a log line before the existing `log_ingestion` + return (keep both):

```python
        except Exception as e:
            error_msg = 'Ingestion failed: {}'.format(str(e))
            logger.exception("Ingestion failed for %s", source_path)
            # Log error
            self.db.log_ingestion(
                ...
            )
            return {'success': False, 'message': error_msg}
```

At `:506-507` replace `except Exception: pass` with:

```python
            except Exception:
                logger.warning("Blender idle-timeout cleanup failed", exc_info=True)
```

- [ ] **Step 7: Fix `main.py` analytics swallow (`:646-647`)**

`main.py` already imports `logging`. Replace:

```python
                except Exception:
                    pass
```

with:

```python
                except Exception:
                    logging.getLogger(__name__).warning("Analytics logging failed", exc_info=True)
```

- [ ] **Step 8: Narrow the `video_player_widget` getsize swallow (`:674-675`)**

Add to `src/video_player_widget.py` imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Replace:

```python
            try:
                size_bytes = os.path.getsize(geometry_path)
            except Exception:
                size_bytes = 0
```

with:

```python
            try:
                size_bytes = os.path.getsize(geometry_path)
            except OSError:
                logger.debug("Could not stat %s", geometry_path, exc_info=True)
                size_bytes = 0
```

- [ ] **Step 9: Run the full suite**

Run: `pytest -m "not manual"`
Expected: 0 failed, 0 errored. The new `test_config_logging` tests pass; all prior tests still pass (fallback values unchanged).

- [ ] **Step 10: Commit**

```bash
git add src/config.py src/db_manager.py src/ingestion_core.py src/video_player_widget.py main.py tests/unit/test_config_logging.py
git commit -m "fix: route bounded set of swallowed exceptions through logging (L4)"
```

---

## Self-Review

**1. Spec coverage:**
- One shared `resolve_path` replacing 4 copies → Tasks 1–2 ✓
- One shared `human_size` replacing 3 formatters → Task 3 ✓
- Dark palette consolidated to `src/dark_palette.py` only → Task 4 ✓
- Single bulk-menu builder → Task 5 ✓
- L4 pattern + bounded application (6 enumerated offenders) → Task 6 ✓
- Unit tests (paths, formatting), caplog logging tests (config), GUI characterization (bulk menu, resolve_path wrappers) → Tasks 1,3,5,6 + Task 2 ✓
- God-module split → **deferred** by design (§4.6); not a task here. No gap — this is the locked YAGNI decision.

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every step shows complete code and exact commands with expected output. Fallback instructions (e.g. pass `stax_db` if `None` construction fails) specify the exact alternative.

**3. Type/behavior consistency:**
- `resolve_path(path, project_root=None, config=None)` is defined in Task 1 and consumed with `project_root=self._project_root` (simple sites) and `+config=self.config` (storage site) in Task 2 — reproducing each prior branch. All `self._project_root` = repo root (verified).
- `human_size(num_bytes)` reproduces the old ≥1MB outputs (`5*1048576 → "5.0 MB"`, `2*1024**3 → "2.0 GB"`); the sub-MB refinement (`512*1024 → "512.0 KB"`) is asserted and flagged in the design for reviewer veto. Call sites keep their `''` / `'N/A'` no-size guards, so those paths are unchanged.
- Bulk-menu builder is parameterized (`with_header`, `is_admin`) so `show_context_menu` (header + existing `is_admin`) and `show_bulk_menu` (no header, admin-enabled) both reproduce prior behavior. The M3 `is_admin` line is left verbatim.
- L4 conversions keep every existing return/fallback value; only visibility changes. `logging.getLogger(__name__)` guarantees `caplog` capture.

---

## Notes for the executor
- **Cleanup only.** If any characterization/SP0 test goes from pass to fail, a migration changed behavior — STOP, diff the removed copy against the shared helper, and reconcile; do not "fix" the test. Report if the codebase's real behavior contradicts a step.
- Run `pytest -m "not manual"` before every commit.
- Do **not** touch the `is_admin` parent lookup, `gif_movies` lifecycle, drop-ingest handlers, or `nuke_bridge._resolve_storage_path` — they belong to SP5/SP6. If a task tempts you into them, stop at the boundary described here.
- Do **not** edit `docs/superpowers/IMPLEMENTATION_PROGRESS.md` (tracked separately).
- The god-module split is intentionally out of scope; if asked to "finish the split", point back to design §4.6 (deferred until after SP2/SP6).
