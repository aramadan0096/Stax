# SP6 — UI Correctness & Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven daily-use UI correctness bugs and navigation memory leaks (M3, M4, M5, M6, M7, M13, L2) with the smallest testable change per issue, each covered by a headless `tests/gui` test on the SP0 harness.

**Architecture:** Surgical per-issue fixes across `src/ui/media_display_widget.py`, `src/ui/dialogs.py`, `main.py`, `src/icon_loader.py`, `src/video_player_widget.py`, `src/ui/media_info_popup.py`, `src/ui/settings_panel.py`. Two fixes (M3, L2) extract a tiny helper so behaviour is assertable without driving a modal event loop; M4 decouples via a Qt signal. The `BatchEditDialog` apply path depends on `DatabaseManager.update_element_metadata` (delivered by SP1) and is `xfail(strict=True)` until then.

**Tech Stack:** Python 3.9, PySide2 (offscreen), pytest, pytest-qt, pytest-mock. Tests run with `QT_QPA_PLATFORM=offscreen` via the SP0 `conftest.py`.

## Global Constraints

- **Platforms:** Windows + Linux only. Tests are headless (`QT_QPA_PLATFORM=offscreen`, set by `tests/conftest.py`).
- **Python:** 3.9.
- **Test tier:** all SP6 tests live in `tests/gui/` and are marked `@pytest.mark.gui`.
- **Fixtures:** reuse SP0's `stax_db`, `stax_config`, `mock_nuke`, `qtbot`. Do **not** add new global fixtures to `conftest.py`; local helpers go in the test files.
- **Import convention for tests:** import UI widgets via `src.ui.*` / `src.<module>` (the same module identity `main.py` and the widgets use, avoiding the `src.ui.dialogs` vs `ui.dialogs` double-module trap); import `MainWindow` via `from main import MainWindow`.
- **`logging`, not `print`** in any code you add or touch (CLAUDE.md L4).
- **Do not add `DatabaseManager.update_element_metadata`** — that is SP1. State it as an interface assumption and `xfail(strict=True)` the one dependent test.
- **Never weaken a test to make CI pass.** Fix the root cause or `xfail` with the issue id.
- Conventional commits (`fix:`, `test:`), commit per task.

---

## Key signatures (verified against the codebase)

- `MediaDisplayWidget(db_manager, config, nuke_bridge, main_window=None, parent=None)` (`src/ui/media_display_widget.py:24`). Has `self.gif_movies = {}` (`:44`), `self.main_window` (`:29`), `get_selected_element_ids()`, `_update_views_with_elements(elements)` (`:607`), `on_size_changed(value)` (`:449`), `stop_current_gif()` (`:1011`), `show_context_menu(position, element_id)` (`:1112`), `current_list_id`, `current_elements`, `load_elements(list_id)`. Bulk branch builds actions at `:1129-1167`; admin read at `:1125-1126`.
- `MainWindow(config=None)` (`main.py:83`); `self.is_admin` (`:111`), `check_admin_permission(action_name)` (`:527`), `on_element_double_clicked(element_id)` (`:631`), `show_advanced_search()` (`:761`), creates `MediaDisplayWidget(..., main_window=self)` (`:228`), adds it to a `QSplitter` (`:233`).
- `AdvancedSearchDialog(db_manager, parent=None)` (`src/ui/dialogs.py:16`); `on_result_double_clicked(item)` (`:122`), `results_table` with `element_id` in column 0 `UserRole`.
- `IconLoader` singleton; class attr `_icon_cache = {}` (`src/icon_loader.py:19`); `get_icon(icon_name, size=24, color=None)` (`:43`), `clear_cache()` (`:123`); miss returns un-cached `QtGui.QIcon()` (`:66-68`). Module fns `get_icon(...)`, `get_pixmap(...)`.
- `VideoPlayerWidget(db_manager, config, parent=None)` (`src/video_player_widget.py:315`); `self.config` is a `Config` object (`:318`); `_get_config_player()` (`:719`) currently gates on `isinstance(self.config, dict)`.
- `Config.get(key, default=None)` (`src/config.py:169`), `Config.set(key, value)` — **persists to disk** (`:173-176`), `Config(config_path='./config/config.json')`.
- `MediaInfoPopup(parent=None)` (`src/ui/media_info_popup.py:24`); `show_element(element_data, position=None)` (`:264`); sets `self.is_video`/`self.is_sequence` at `:308-317`. Element `type` ∈ `{2D,3D,Toolset}`; `format` = `os.path.splitext(src)[1]` (dot-prefixed, `src/ingestion_core.py:619`).
- Ingestion taxonomy (`src/ingestion_core.py:169-171`): `IMAGE_FORMATS = ['.exr','.dpx','.tif','.tiff','.jpg','.jpeg','.png','.tga']`, `VIDEO_FORMATS = ['.mov','.mp4','.avi','.mxf']`, `GEO_FORMATS = ['.abc','.obj','.fbx','.usd','.usda','.usdc','.glb','.gltf']`.
- `SettingsPanel(config, db_manager, main_window=None, parent=None)` (`src/ui/settings_panel.py:20`); `setup_ui()` runs `QVBoxLayout(self)` (`:30`); `reset_settings()` (`:943`) pops `QMessageBox.question`, then rebuilds.
- `BatchEditDialog(element_ids, db, parent=None)` (`src/ui/batch_edit_dialog.py:96`); `_apply()` (`:250`) → `_write_element` → `self.db.update_element_metadata(element_id, **kwargs)` (`:362`) — **method missing on live `DatabaseManager`** (has only `get_element_by_id` `:829`, `update_element` `:837`). This is the SP1 dependency.
- `NukeBridge(mock_mode=True)` (`src/nuke_bridge.py`).

---

## Task 1: M3 — resolve admin flag through MainWindow

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_admin_menu.py` (new)

**Interfaces:**
- Produces: `MediaDisplayWidget._is_admin_user()` used by `show_context_menu` for bulk-action enablement.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_admin_menu.py`:

```python
import pytest
from PySide2 import QtWidgets

from src.ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


class _FakeMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(_FakeMainWindow, self).__init__()
        self.is_admin = False

    def check_admin_permission(self, action_name="this action"):
        return self.is_admin


def _make_widget(qtbot, stax_db, stax_config):
    mw = _FakeMainWindow()
    qtbot.addWidget(mw)
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w, mw


@pytest.mark.gui
def test_admin_flag_reads_from_main_window_not_parent(qtbot, stax_db, stax_config):
    w, mw = _make_widget(qtbot, stax_db, stax_config)
    # Reparent onto a QSplitter to reproduce the real widget tree (main.py:233).
    splitter = QtWidgets.QSplitter()
    qtbot.addWidget(splitter)
    splitter.addWidget(w)
    assert w.parent() is splitter          # the Qt parent has no is_admin

    mw.is_admin = False
    assert w._is_admin_user() is False
    mw.is_admin = True
    assert w._is_admin_user() is True      # resolves via main_window, not parent()
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/gui/test_admin_menu.py -v`
Expected: FAIL — `MediaDisplayWidget` has no `_is_admin_user` (AttributeError).

- [ ] **Step 3: Add the helper**

In `src/ui/media_display_widget.py`, add this method to `MediaDisplayWidget` (e.g. immediately above `show_context_menu`):

```python
    def _is_admin_user(self):
        """Return True if the owning MainWindow reports an admin session.

        The widget's Qt parent is the central QSplitter (main.py), which has no
        'is_admin' attribute; permission state lives on MainWindow, injected as
        self.main_window at construction. (Fixes audit issue M3.)
        """
        return bool(getattr(self.main_window, 'is_admin', False))
```

- [ ] **Step 4: Use it in `show_context_menu`**

Replace (`:1125-1126`):

```python
        menu = QtWidgets.QMenu(self)
        parent_widget = self.parent()
        is_admin = bool(getattr(parent_widget, 'is_admin', False)) if parent_widget else False
```

with:

```python
        menu = QtWidgets.QMenu(self)
        is_admin = self._is_admin_user()
```

- [ ] **Step 5: Run the test — confirm it passes**

Run: `pytest tests/gui/test_admin_menu.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_admin_menu.py
git commit -m "fix(ui): resolve admin bulk-menu flag via main_window not parent splitter (M3)"
```

---

## Task 2: M4 — advanced-search signal + MainWindow handler

**Files:**
- Modify: `src/ui/dialogs.py`, `main.py`
- Test: `tests/gui/test_advanced_search.py` (new)

**Interfaces:**
- Produces: `AdvancedSearchDialog.result_activated` (Signal), `MainWindow.on_advanced_search_result(element_id)`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_advanced_search.py`:

```python
import os
import pytest
from PySide2 import QtCore, QtWidgets

from src.ui.dialogs import AdvancedSearchDialog


@pytest.mark.gui
def test_double_click_emits_result_activated(qtbot, stax_db):
    dlg = AdvancedSearchDialog(stax_db)
    qtbot.addWidget(dlg)

    # Seed one result row with an element_id in column 0's UserRole.
    dlg.results_table.setRowCount(1)
    cell = QtWidgets.QTableWidgetItem("elem")
    cell.setData(QtCore.Qt.UserRole, 42)
    dlg.results_table.setItem(0, 0, cell)

    with qtbot.waitSignal(dlg.result_activated, timeout=1000) as blocker:
        dlg.on_result_double_clicked(cell)
    assert blocker.args == [42]


@pytest.mark.gui
def test_mainwindow_has_on_advanced_search_result(qtbot, stax_config, mock_nuke, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from main import MainWindow

    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)
    assert callable(getattr(win, "on_advanced_search_result", None))
    # Routing an id must not raise AttributeError (mock nuke insertion is a no-op).
    win.on_advanced_search_result(999999)  # non-existent id -> handled, no crash
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/gui/test_advanced_search.py -v`
Expected: FAIL — `result_activated` signal and `on_advanced_search_result` do not exist yet.

- [ ] **Step 3: Add the signal + emit in `AdvancedSearchDialog`**

In `src/ui/dialogs.py`, add the signal to the class body (just under the class docstring, `:15`):

```python
class AdvancedSearchDialog(QtWidgets.QDialog):
    """Advanced search dialog with property and match type selection."""

    result_activated = QtCore.Signal(int)  # element_id (fixes audit issue M4)

    def __init__(self, db_manager, parent=None):
```

Replace `on_result_double_clicked` (`:122-127`):

```python
    def on_result_double_clicked(self, item):
        """Handle double-click on result by emitting result_activated(element_id).

        Previously called self.parent().on_advanced_search_result(...), a method
        MainWindow does not define -> AttributeError (audit issue M4). Emitting a
        signal decouples the dialog from its owner.
        """
        element_id = self.results_table.item(item.row(), 0).data(QtCore.Qt.UserRole)
        if element_id:
            self.result_activated.emit(int(element_id))
```

- [ ] **Step 4: Add the handler + connection in `MainWindow`**

In `main.py`, add the handler next to `on_element_double_clicked` (e.g. right after it, ~`:650`):

```python
    def on_advanced_search_result(self, element_id):
        """Handle activation of an advanced-search result: insert it, same path
        as a gallery double-click. (Fixes audit issue M4.)"""
        self.on_element_double_clicked(element_id)
```

Update `show_advanced_search` (`:761-765`) to connect the signal once, inside the lazy-construct guard:

```python
    def show_advanced_search(self):
        if not hasattr(self, "advanced_search_dialog") or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
            self.advanced_search_dialog.result_activated.connect(self.on_advanced_search_result)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()
```

- [ ] **Step 5: Run the test — confirm it passes**

Run: `pytest tests/gui/test_advanced_search.py -v`
Expected: PASS (2 passed). If `MainWindow(config=...)` raises for an unrelated reason, confirm SP0's `test_mainwindow_smoke.py` still passes first (SP6 assumes it does).

- [ ] **Step 6: Commit**

```bash
git add src/ui/dialogs.py main.py tests/gui/test_advanced_search.py
git commit -m "fix(ui): route advanced-search double-click via signal to MainWindow handler (M4)"
```

---

## Task 3: M5 — bounded gif/icon caches + debounced size slider

**Files:**
- Modify: `src/ui/media_display_widget.py`, `src/icon_loader.py`
- Test: `tests/gui/test_media_memory.py` (new)

**Interfaces:**
- Produces: `MediaDisplayWidget._clear_gif_movies()`, `MediaDisplayWidget._size_debounce`/`_apply_pending_size`; `IconLoader._MAX_CACHE_ENTRIES`, LRU + miss-caching `_icon_cache`.

- [ ] **Step 1: Write the failing tests**

Create `tests/gui/test_media_memory.py`:

```python
import pytest
from PySide2 import QtGui, QtWidgets

from src.ui.media_display_widget import MediaDisplayWidget
from src.icon_loader import IconLoader, get_icon
from nuke_bridge import NukeBridge


def _make_widget(qtbot, stax_db, stax_config):
    mw = QtWidgets.QMainWindow()
    mw.is_admin = False
    qtbot.addWidget(mw)
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_gif_movies_cleared_on_refresh(qtbot, stax_db, stax_config):
    w = _make_widget(qtbot, stax_db, stax_config)
    movie = QtGui.QMovie()
    movie.frameChanged.connect(lambda n: None)
    w.gif_movies[123] = movie
    w._update_views_with_elements([])          # a refresh with no elements
    assert w.gif_movies == {}                  # cleared + disconnected


@pytest.mark.gui
def test_icon_cache_is_bounded_and_caches_misses():
    loader = IconLoader()
    loader.clear_cache()
    bound = IconLoader._MAX_CACHE_ENTRIES
    # Request more distinct (name,size) keys than the bound.
    for size in range(1, bound + 60):
        get_icon("add", size=size)
    assert len(IconLoader._icon_cache) <= bound

    # A missing icon is cached (no repeated disk stat / no unbounded growth).
    loader.clear_cache()
    get_icon("definitely_not_a_real_icon_name", size=24)
    assert any("definitely_not_a_real_icon_name" in k for k in IconLoader._icon_cache)


@pytest.mark.gui
def test_size_slider_is_debounced(qtbot, stax_db, stax_config, monkeypatch):
    w = _make_widget(qtbot, stax_db, stax_config)
    calls = []
    monkeypatch.setattr(w, "_apply_pending_size", lambda: calls.append(1))
    w.current_elements = [{"element_id": 1, "name": "x", "type": "2D"}]

    w.on_size_changed(256)
    assert w._size_debounce.isActive()         # deferred, not run inline
    assert calls == []                         # not called synchronously

    qtbot.waitUntil(lambda: calls == [1], timeout=2000)   # fires exactly once
```

- [ ] **Step 2: Run them — confirm they fail**

Run: `pytest tests/gui/test_media_memory.py -v`
Expected: FAIL — `_clear_gif_movies` not called (gif_movies not emptied), `IconLoader._MAX_CACHE_ENTRIES` missing, `_size_debounce` missing.

- [ ] **Step 3: Bound the `IconLoader` cache and cache misses**

In `src/icon_loader.py`, replace the imports/class header (`:8-19`):

```python
import os
import logging
from collections import OrderedDict

from PySide2 import QtGui, QtSvg, QtCore

log = logging.getLogger(__name__)


class IconLoader(object):
    """
    Utility class for loading SVG icons with a bounded LRU cache.
    Provides consistent icon access throughout the application.
    """

    _instance = None
    _icon_cache = OrderedDict()
    _MAX_CACHE_ENTRIES = 256
    _MISS = QtGui.QIcon()   # shared sentinel returned/cached for not-found/failed loads
```

Replace `get_icon` (`:43-90`) with an LRU + negative-caching version:

```python
    def get_icon(self, icon_name, size=24, color=None):
        """Get a QIcon from an SVG file, with a bounded LRU cache.

        Cache misses (missing file / render error) are cached as a shared empty
        QIcon so repeated requests (e.g. slider drags) stop re-statting the disk.
        (Fixes audit issue M5.)
        """
        cache_key = "{}_{}_{}".format(icon_name, size, color or 'default')

        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            self._icon_cache.move_to_end(cache_key)   # mark most-recently-used
            return cached

        icon_path = os.path.join(self.icons_dir, "{}.svg".format(icon_name))
        if not os.path.exists(icon_path):
            log.warning("Icon not found: %s", icon_path)
            return self._store_icon(cache_key, self._MISS)

        try:
            renderer = QtSvg.QSvgRenderer(icon_path)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return self._store_icon(cache_key, QtGui.QIcon(pixmap))
        except Exception as exc:
            log.exception("Error loading icon %s: %s", icon_name, exc)
            return self._store_icon(cache_key, self._MISS)

    def _store_icon(self, cache_key, icon):
        """Insert into the LRU cache, evicting the oldest entry over the bound."""
        self._icon_cache[cache_key] = icon
        self._icon_cache.move_to_end(cache_key)
        while len(self._icon_cache) > self._MAX_CACHE_ENTRIES:
            self._icon_cache.popitem(last=False)   # evict least-recently-used
        return icon
```

Replace the `print` in `__init__` (`:41`) with logging:

```python
        if not os.path.exists(self.icons_dir):
            log.warning("Icons directory not found: %s", self.icons_dir)
```

(Leave `get_pixmap` and `clear_cache` as-is; `clear_cache` already calls `self._icon_cache.clear()`.)

- [ ] **Step 4: Add `_clear_gif_movies` and call it on refresh**

In `src/ui/media_display_widget.py`, add the helper (e.g. next to `stop_current_gif`, `:1011`):

```python
    def _clear_gif_movies(self):
        """Stop, disconnect, and drop all cached GIF QMovies (bounds memory to
        the currently rendered page). (Fixes audit issue M5.)"""
        for movie in self.gif_movies.values():
            try:
                movie.stop()
                movie.frameChanged.disconnect()
            except (RuntimeError, TypeError):
                pass   # not connected / already deleted
        self.gif_movies.clear()
```

In `_update_views_with_elements` (`:607-611`), call it right after `stop_current_gif`:

```python
    def _update_views_with_elements(self, elements):
        """Update gallery and table views with given elements."""
        self.stop_current_gif()
        self._clear_gif_movies()
        self.current_gif_item = None
        self.gallery_view.clear()
```

- [ ] **Step 5: Add the debounce timer and split `on_size_changed`**

In `__init__` (after `self.gif_movies = {}`, `:44`), add:

```python
        self.gif_movies = {}  # Cache for QMovie objects {element_id: QMovie}
        self._pending_icon_size = None
        self._size_debounce = QtCore.QTimer(self)
        self._size_debounce.setSingleShot(True)
        self._size_debounce.timeout.connect(lambda: self._apply_pending_size())
```

Replace `on_size_changed` (`:449-459`):

```python
    def on_size_changed(self, value):
        """Handle thumbnail size change - debounced reload (audit issue M5).

        The icon size is applied immediately (cheap, keeps the grid responsive)
        but the expensive page reload is coalesced through a single-shot timer,
        so dragging the slider triggers one reload instead of one per tick.
        """
        self.gallery_view.setIconSize(QtCore.QSize(value, value))
        if not self.current_elements:
            return
        self._pending_icon_size = value
        self._size_debounce.start(150)

    def _apply_pending_size(self):
        """Reload the current view at the pending icon size (debounced target)."""
        if not self.current_elements:
            return
        if self.config.get('pagination_enabled', True) and self.current_list_id:
            self._display_current_page()
        else:
            self._update_views_with_elements(self.current_elements)
```

- [ ] **Step 6: Run the tests — confirm they pass**

Run: `pytest tests/gui/test_media_memory.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add src/ui/media_display_widget.py src/icon_loader.py tests/gui/test_media_memory.py
git commit -m "fix(ui): clear gif QMovies on refresh, bound icon cache with miss-caching, debounce size slider (M5)"
```

---

## Task 4: M6 — persist external player via Config

**Files:**
- Modify: `src/video_player_widget.py`
- Test: `tests/gui/test_external_player.py` (new)

**Interfaces:**
- Consumes: `Config.get`/`Config.set` (persists to disk).

- [ ] **Step 1: Write the failing tests**

Create `tests/gui/test_external_player.py`:

```python
import pytest
from PySide2 import QtWidgets

from src.video_player_widget import VideoPlayerWidget
from config import Config


def _make_player(qtbot, stax_db, stax_config):
    w = VideoPlayerWidget(stax_db, stax_config)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_get_config_player_reads_from_config(qtbot, stax_db, stax_config):
    stax_config.set("external_player", "/usr/bin/mpv")
    w = _make_player(qtbot, stax_db, stax_config)
    assert w._get_config_player() == "/usr/bin/mpv"   # read path un-gated


@pytest.mark.gui
def test_get_config_player_persists_choice(qtbot, stax_db, stax_config, monkeypatch, tmp_path):
    picked = str(tmp_path / "player.exe")
    open(picked, "w").close()

    # Neutralise the file dialog: pretend the user accepted and picked `picked`.
    monkeypatch.setattr(QtWidgets.QFileDialog, "exec_", lambda self: 1)
    monkeypatch.setattr(QtWidgets.QFileDialog, "selectedFiles", lambda self: [picked])

    w = _make_player(qtbot, stax_db, stax_config)
    assert w._get_config_player() == picked
    assert stax_config.get("external_player") == picked

    # Persisted to disk: a fresh Config on the same path sees it.
    reloaded = Config(config_path=stax_config.config_path)
    assert reloaded.get("external_player") == picked
```

> Note: `stax_config.config_path` is the attribute `Config` stores its path under; if the attribute name differs, read it from the fixture's `tmp_path/config.json` instead.

- [ ] **Step 2: Run them — confirm they fail**

Run: `pytest tests/gui/test_external_player.py -v`
Expected: FAIL — the read is gated behind `isinstance(self.config, dict)` (a `Config` is not a dict), so `_get_config_player` ignores the stored value and would try to open a dialog.

- [ ] **Step 3: Add a module logger**

In `src/video_player_widget.py`, add near the top imports (`:8-9`):

```python
import os
import sys
import logging
```

and after the imports block (e.g. below `:25`):

```python
log = logging.getLogger(__name__)
```

- [ ] **Step 4: Rewrite `_get_config_player`**

Replace `_get_config_player` (`:719-759`) with:

```python
    def _get_config_player(self):
        """Return the configured external player path, or prompt and persist one.

        Reads/writes through the Config API (self.config is a Config object, not a
        dict); Config.set writes to disk. (Fixes audit issue M6.)
        """
        player = None
        try:
            player = self.config.get('external_player')
        except Exception:
            log.exception("Failed to read external_player from config")
        if player:
            return player

        dlg = QtWidgets.QFileDialog(self, 'Select external player executable')
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        if dlg.exec_():
            files = dlg.selectedFiles()
            if files:
                player_path = files[0]
                try:
                    self.config.set('external_player', player_path)
                except Exception:
                    log.exception("Failed to persist external_player to config")
                return player_path
        return None
```

- [ ] **Step 5: Run the tests — confirm they pass**

Run: `pytest tests/gui/test_external_player.py -v`
Expected: PASS (2 passed). If `Config` has no `config_path` attribute, adjust the reload assertion to read the fixture's JSON path directly; do not change `Config`.

- [ ] **Step 6: Commit**

```bash
git add src/video_player_widget.py tests/gui/test_external_player.py
git commit -m "fix(player): persist external player through Config.get/set instead of dict gate (M6)"
```

---

## Task 5: M7 — popup detects video/sequence by format

**Files:**
- Modify: `src/ui/media_info_popup.py`
- Test: `tests/gui/test_media_info_popup.py` (new)

**Interfaces:**
- Produces: correct `MediaInfoPopup.is_video`/`is_sequence` for `2D/3D/Toolset` elements.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_media_info_popup.py`:

```python
import pytest

from src.ui.media_info_popup import MediaInfoPopup


def _elem(**kw):
    base = {"name": "e", "type": "2D", "format": "", "frame_range": None, "file_size": 0}
    base.update(kw)
    return base


@pytest.mark.gui
def test_video_controls_detected_by_format(qtbot):
    popup = MediaInfoPopup()
    qtbot.addWidget(popup)

    popup.show_element(_elem(type="2D", format=".mp4"))
    assert popup.is_video is True
    assert popup.is_sequence is False

    popup.show_element(_elem(type="2D", format=".exr", frame_range="1-10"))
    assert popup.is_video is False
    assert popup.is_sequence is True

    popup.show_element(_elem(type="3D", format=".abc"))
    assert popup.is_video is False
    assert popup.is_sequence is False

    # A lone still (png, no frame range) is neither.
    popup.show_element(_elem(type="2D", format=".png", frame_range=None))
    assert popup.is_video is False
    assert popup.is_sequence is False
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/gui/test_media_info_popup.py -v`
Expected: FAIL — current code keys off `type == 'video'/'sequence'`, so `is_video`/`is_sequence` are always `False`.

- [ ] **Step 3: Add extension constants**

In `src/ui/media_info_popup.py`, after the imports (`:10`), add:

```python
# Element `type` is only ever 2D/3D/Toolset, so video/sequence must be detected by
# the file format/extension (dot-prefixed, e.g. ".mp4"). Mirrors the ingestion
# taxonomy in ingestion_core.py. (Fixes audit issue M7.)
VIDEO_EXTS = ('.mov', '.mp4', '.avi', '.mxf')
SEQUENCE_EXTS = ('.exr', '.dpx', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.tga', '.bmp')
```

- [ ] **Step 4: Replace the type check in `show_element`**

Replace (`:307-310`):

```python
        # Determine if video or sequence
        element_type = element_data.get('type', '').lower()
        self.is_video = element_type == 'video'
        self.is_sequence = element_type == 'sequence'
```

with:

```python
        # Determine if video or sequence by format/extension (type is 2D/3D/Toolset).
        fmt = (element_data.get('format') or '').lower()
        if fmt and not fmt.startswith('.'):
            fmt = '.' + fmt
        frame_range = element_data.get('frame_range')
        self.is_video = fmt in VIDEO_EXTS
        self.is_sequence = bool(frame_range) and fmt in SEQUENCE_EXTS
```

- [ ] **Step 5: Run the test — confirm it passes**

Run: `pytest tests/gui/test_media_info_popup.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add src/ui/media_info_popup.py tests/gui/test_media_info_popup.py
git commit -m "fix(ui): detect popup video/sequence controls by format/extension not element type (M7)"
```

---

## Task 6: M13 — clean layout teardown on settings reset

**Files:**
- Modify: `src/ui/settings_panel.py`
- Test: `tests/gui/test_settings_reset.py` (new)

**Interfaces:**
- Consumes: SP0 `stax_config`, `stax_db`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_settings_reset.py`:

```python
import pytest
from PySide2 import QtCore, QtWidgets

from src.ui.settings_panel import SettingsPanel


@pytest.mark.gui
def test_reset_does_not_emit_layout_warning(qtbot, stax_config, stax_db, monkeypatch):
    panel = SettingsPanel(stax_config, stax_db)
    qtbot.addWidget(panel)

    # Confirm the reset dialog + suppress the info popup.
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))

    messages = []
    QtCore.qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
    try:
        panel.reset_settings()
    finally:
        QtCore.qInstallMessageHandler(None)

    assert not any("already has a layout" in m for m in messages)
    assert panel.layout() is not None
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/gui/test_settings_reset.py -v`
Expected: FAIL — Qt emits a "QLayout: Attempting to add QLayout ... which already has a layout" warning captured by the handler.

- [ ] **Step 3: Reparent the old layout before rebuild**

In `src/ui/settings_panel.py`, replace the reset body (`:951-968`, the `if reply == ... Yes:` block) with:

```python
        if reply == QtWidgets.QMessageBox.Yes:
            self.config.reset_to_defaults()

            # Detach the old layout (and its child widgets) from self so setup_ui
            # can install a fresh QVBoxLayout(self) without the Qt "already has a
            # layout" warning. The throwaway QWidget adopts and disposes them.
            # (Fixes audit issue M13.)
            old_layout = self.layout()
            if old_layout is not None:
                QtWidgets.QWidget().setLayout(old_layout)

            # Rebuild UI
            self.setup_ui()

            QtWidgets.QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            self.settings_changed.emit()
```

- [ ] **Step 4: Run the test — confirm it passes**

Run: `pytest tests/gui/test_settings_reset.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/settings_panel.py tests/gui/test_settings_reset.py
git commit -m "fix(ui): reparent old layout before rebuilding settings panel on reset (M13)"
```

---

## Task 7: L2 — wire BatchEditDialog into the bulk menu

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_batch_edit_wiring.py` (new)

**Interfaces:**
- Produces: `MediaDisplayWidget.open_batch_edit(selected_ids=None)` + a bulk-menu action.
- **Consumes (SP1 interface assumption):** `DatabaseManager.update_element_metadata(element_id, **kwargs)` — used by `BatchEditDialog._write_element`, delivered by SP1. The apply-path test is `xfail(strict=True)` until then.

- [ ] **Step 1: Write the tests (open-path passes; apply-path xfail)**

Create `tests/gui/test_batch_edit_wiring.py`:

```python
import pytest
from PySide2 import QtWidgets

from src.ui.media_display_widget import MediaDisplayWidget
from src.ui.batch_edit_dialog import BatchEditDialog
from nuke_bridge import NukeBridge


def _make_widget(qtbot, stax_db, stax_config):
    mw = QtWidgets.QMainWindow()
    mw.is_admin = True
    qtbot.addWidget(mw)
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_open_batch_edit_constructs_dialog(qtbot, stax_db, stax_config, monkeypatch):
    w = _make_widget(qtbot, stax_db, stax_config)
    # Neutralise the modal: pretend the dialog was rejected without blocking.
    monkeypatch.setattr(BatchEditDialog, "exec_", lambda self: QtWidgets.QDialog.Rejected)

    dlg = w.open_batch_edit([1, 2])
    assert isinstance(dlg, BatchEditDialog)
    assert dlg.element_ids == [1, 2]


@pytest.mark.gui
def test_open_batch_edit_needs_two_selection(qtbot, stax_db, stax_config):
    w = _make_widget(qtbot, stax_db, stax_config)
    assert w.open_batch_edit([1]) is None       # single selection -> no dialog


@pytest.mark.gui
@pytest.mark.xfail(reason="L2 apply path depends on SP1 db.update_element_metadata",
                   strict=True)
def test_batch_edit_apply_dependency_present(stax_db):
    # BatchEditDialog._write_element calls db.update_element_metadata, which the
    # live DatabaseManager does not yet expose. SP1 adds it and flips this green.
    assert hasattr(stax_db, "update_element_metadata")
```

- [ ] **Step 2: Run them — confirm the open-path fails, the apply-path xfails**

Run: `pytest tests/gui/test_batch_edit_wiring.py -v`
Expected: `test_open_batch_edit_*` FAIL (no `open_batch_edit`); `test_batch_edit_apply_dependency_present` XFAIL.

- [ ] **Step 3: Add `open_batch_edit`**

In `src/ui/media_display_widget.py`, add the method (e.g. below `show_context_menu`):

```python
    def open_batch_edit(self, selected_ids=None):
        """Open the batch metadata editor for the current multi-selection.

        Wires the finished BatchEditDialog into the UI (audit issue L2). Returns
        the dialog (constructed only for a 2+ selection) or None.
        """
        if selected_ids is None:
            selected_ids = self.get_selected_element_ids()
        if len(selected_ids) < 2:
            return None
        from src.ui.batch_edit_dialog import BatchEditDialog
        dlg = BatchEditDialog(selected_ids, self.db, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted and self.current_list_id:
            self.load_elements(self.current_list_id)
        return dlg
```

- [ ] **Step 4: Add the bulk-menu action + dispatch**

In `show_context_menu`, in the multi-select branch, add the action after the "Add All to Playlist..." action (`:1143`, before the separator at `:1145`):

```python
            # Bulk add to playlist
            bulk_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")

            # Batch metadata edit (L2)
            bulk_edit_action = menu.addAction(get_icon('edit', size=16), "Batch Edit Metadata...")

            menu.addSeparator()
```

and add its dispatch in the `action == ...` chain (after the `bulk_playlist_action` branch, `:1162-1163`):

```python
            elif action == bulk_playlist_action:
                self.bulk_add_to_playlist(selected_ids)
            elif action == bulk_edit_action:
                self.open_batch_edit(selected_ids)
```

- [ ] **Step 5: Run the tests — confirm open passes, apply xfails**

Run: `pytest tests/gui/test_batch_edit_wiring.py -v`
Expected: `test_open_batch_edit_constructs_dialog` PASS, `test_open_batch_edit_needs_two_selection` PASS, `test_batch_edit_apply_dependency_present` XFAIL. (0 failed, 0 xpassed.)

- [ ] **Step 6: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_batch_edit_wiring.py
git commit -m "feat(ui): wire BatchEditDialog into the bulk context menu (L2); apply-path xfail until SP1"
```

---

## Task 8: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole collected suite**

Run: `pytest -m "not manual"`
Expected: all SP0 + SP6 tests pass or xfail; **0 failed, 0 errored, 0 xpassed**. Exactly one *new* xfail from SP6 (`test_batch_edit_apply_dependency_present`), plus SP0's pre-existing xfails.

- [ ] **Step 2: Confirm no regression in SP0 smoke tests**

Run: `pytest tests/gui/test_mainwindow_smoke.py tests/gui/test_api_smoke.py -v`
Expected: unchanged from SP0 (MainWindow constructs; API health passes; C1 analytics still xfails). If `MainWindow` now fails to construct, the M4 `main.py` edit is at fault — re-check the `on_advanced_search_result` indentation and the `show_advanced_search` connect.

- [ ] **Step 3: Final commit (if any lint/whitespace cleanup)**

```bash
git status
# only commit if there are stray changes; otherwise nothing to do
```

---

## Self-Review

**1. Spec coverage:**
- M3 admin-flag via main_window → Task 1 ✓
- M4 advanced-search signal + MainWindow handler → Task 2 ✓
- M5 gif clear + icon-cache bound/miss-cache + size debounce → Task 3 ✓
- M6 Config-backed external player → Task 4 ✓
- M7 popup detect-by-format → Task 5 ✓
- M13 clean layout teardown → Task 6 ✓
- L2 batch-edit wiring + SP1 xfail → Task 7 ✓
- Full-suite green verification → Task 8 ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every code step is complete, real code against verified signatures. Fallbacks (Config lacking `config_path`; MainWindow construction failure) specify the exact alternative and forbid changing product code beyond the issue at hand.

**3. Type/interface consistency:**
- `MediaDisplayWidget(db, config, nuke_bridge, main_window=...)`, `gif_movies` dict, `_update_views_with_elements(elements)`, `on_size_changed(value)`, `get_selected_element_ids()`, `current_list_id`/`current_elements`, `load_elements(list_id)` — all match `src/ui/media_display_widget.py`.
- `AdvancedSearchDialog(db, parent=None)` + `results_table` UserRole in col 0 — matches `src/ui/dialogs.py`.
- `MainWindow.on_element_double_clicked`, `show_advanced_search`, `is_admin` — match `main.py`.
- `Config.get/set` (set persists) — matches `src/config.py:169-176`.
- `MediaInfoPopup(parent=None)`, `show_element(element_data, position=None)`, `is_video`/`is_sequence` — match `src/ui/media_info_popup.py`. Extension lists mirror `ingestion_core.py:169-171`; `format` is dot-prefixed.
- `SettingsPanel(config, db, ...)`, `setup_ui` → `QVBoxLayout(self)`, `reset_settings` — match `src/ui/settings_panel.py`.
- `BatchEditDialog(element_ids, db, parent=None)`, `_write_element` → `db.update_element_metadata` (missing on live DB) — matches `src/ui/batch_edit_dialog.py:96/362`; SP1 dependency correctly `xfail(strict)`.
- `NukeBridge(mock_mode=True)`, `IconLoader` singleton + `clear_cache()` + `_icon_cache` — match the codebase.

**4. Test tier/fixtures:** every test is `@pytest.mark.gui`, uses SP0's `stax_db`/`stax_config`/`mock_nuke`/`qtbot`, imports UI widgets via `src.ui.*`/`src.<module>` (single module identity), and neutralises modals via monkeypatch rather than driving them.

---

## Notes for the executor
- **Do not add `DatabaseManager.update_element_metadata`** to make Task 7's apply-path test pass — that is SP1's deliverable. Leave it `xfail(strict=True)`.
- Run the target task's test file before every commit; run `pytest -m "not manual"` before the final commit.
- If a construction-time defect surfaces in a widget unrelated to the issue you're fixing, `xfail(strict=True)` it with the issue id and report it — do not fix out-of-scope bugs in SP6.
- Match each edited file's existing import style (`src.ui.*` in the UI modules) and use `logging`, never `print`, in code you add or touch.
