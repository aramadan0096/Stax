# SP6 — UI Correctness & Memory — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). SP6 fixes the everyday-UI correctness bugs and the navigation memory leaks users hit in the desktop/panel app. It builds on the SP0 harness (`stax_db`, `stax_config`, `mock_nuke`, headless Qt) and is independent of SP1–SP5 except for one stated interface assumption (L2 → `DatabaseManager.update_element_metadata`, delivered by SP1).

---

## 1. Background & Motivation

The StaX audit (`STAX_AUDIT_REPORT.md`) ranks a cluster of medium-severity UI defects that degrade daily use or leak memory across gallery navigation. SP6 remediates seven of them plus one low item:

| Issue | File(s) | Symptom |
|---|---|---|
| **M3** | `src/ui/media_display_widget.py:1125-1126` | Admin bulk actions ("Mark All as Deprecated" / "Delete All Selected") are permanently greyed out — `is_admin` is read from `self.parent()`, which is the `QSplitter` (`main.py:233`), never the `MainWindow`. |
| **M4** | `src/ui/dialogs.py:122-127` | Double-clicking an advanced-search result calls `self.parent().on_advanced_search_result(...)`, a method `MainWindow` does not define → `AttributeError` every time. |
| **M5** | `src/ui/media_display_widget.py:44/642-648`, `src/icon_loader.py:19/56/65` | `gif_movies` QMovies accumulate forever (never cleared, `frameChanged` lambdas never disconnected); the icon cache is unbounded, keyed by live slider size (64–512), and never caches misses; `on_size_changed` reloads the whole page on every slider tick. |
| **M6** | `src/video_player_widget.py:719-759` | External-player config is gated behind `isinstance(self.config, dict)`, but `config` is a `Config` object, so the chosen player is never persisted (re-prompted every launch) and the dead `json.dump(self.config, ...)` path would raise if reached. |
| **M7** | `src/ui/media_info_popup.py:307-317` | Video/sequence controls are gated on `type == 'video'` / `type == 'sequence'`, but element `type` is only ever `2D`/`3D`/`Toolset`, so the scrubber/play/stop UI never appears. |
| **M13** | `src/ui/settings_panel.py:943-968` | `reset_settings` empties the layout's items then calls `setup_ui()`, which runs `QVBoxLayout(self)` while `self` still owns the old layout → Qt "already has a layout" warning + orphaned widgets. |
| **L2** | `src/ui/batch_edit_dialog.py` (+ `media_display_widget.py`) | The finished `BatchEditDialog` is never opened by any menu — the bulk context menu offers no "Batch Edit" action. |

### Program context (decisions already locked)
- **Wire, don't delete:** `BatchEditDialog` is finished code that is simply unwired — SP6 wires it (L2), it does not remove it.
- **Windows + Linux**, hybrid 3-tier testing, flat imports, `logging` not `print`, TDD + frequent conventional commits.

---

## 2. Goals / Non-Goals

### Goals
- Admin bulk-menu enablement resolves through `MainWindow` (M3).
- Advanced-search double-click routes to a real handler with no `AttributeError` (M4).
- Gallery navigation no longer leaks `QMovie`/icon objects; the icon cache is LRU-bounded and caches misses; the size slider is debounced (M5).
- The embedded player persists its external-player choice through `Config` (M6).
- The media-info popup shows video/sequence controls for the correct elements, detected by format/extension (M7).
- Settings reset rebuilds cleanly with no Qt layout warning (M13).
- `BatchEditDialog` opens from the multi-select bulk menu (L2).
- Every fix is covered by a `tests/gui` (pytest-qt, offscreen) test built on the SP0 fixtures, using real widgets.

### Non-Goals (explicitly deferred)
- Adding `DatabaseManager.update_element_metadata` — that is **SP1**. SP6 wires the dialog and states the interface assumption; the apply-path test is `xfail(strict=True)` until SP1 lands (see §5).
- The god-module split of `media_display_widget.py` / `video_player_widget.py` / `dialogs.py` (L10) — **SP8**.
- Threading ingest/preview off the GUI thread (C4/M9) — **SP2/SP3**.
- Reworking the auth model behind `is_admin` (M3 only fixes the *lookup*, not the permission model).
- Any change to `icon_loader`'s SVG render path beyond bounding the cache.

---

## 3. Approach

Chosen approach: **surgical, per-issue fixes with a thin testability seam.** Each defect is fixed at its root cause with the smallest change that is also unit-testable headlessly. Two fixes extract a tiny helper so behaviour can be asserted without driving a modal (`QMenu.exec_`/`QDialog.exec_`) event loop:

- **M3** extracts `MediaDisplayWidget._is_admin_user()` (reads `self.main_window.is_admin`); `show_context_menu` calls it. The test asserts the helper, not the modal menu.
- **L2** adds `MediaDisplayWidget.open_batch_edit(selected_ids)`; the bulk menu action calls it. The test calls the method with `exec_` monkeypatched, so no modal blocks.

**M4** is decoupled with a Qt signal: `AdvancedSearchDialog.result_activated = Signal(int)`. The dialog emits instead of reaching into `self.parent()`; `MainWindow.show_advanced_search` connects it to a new `MainWindow.on_advanced_search_result(element_id)` that routes to the existing insertion path (`on_element_double_clicked`). This removes the fragile parent-walk entirely and is testable both in isolation (signal spy) and on `MainWindow` (method presence + no-raise).

**M5** is three independent bounded-memory fixes in two files:
1. `MediaDisplayWidget._clear_gif_movies()` stops each movie, disconnects `frameChanged`, and empties `gif_movies`; it runs at the top of `_update_views_with_elements`, so the cache is bounded to the currently rendered page.
2. `IconLoader._icon_cache` becomes an LRU `OrderedDict` bounded by `_MAX_CACHE_ENTRIES`, and **misses are cached** (a shared empty `QIcon`) so slider drags and missing icons stop re-statting the disk.
3. `on_size_changed` is **debounced** through a single-shot `QTimer` (`_size_debounce`), coalescing rapid slider ticks into one reload.

**M6/M7/M13** are direct in-place corrections (use `Config.get/set`; detect by extension against the existing `IMAGE_FORMATS`/`VIDEO_FORMATS` taxonomy; reparent the stale layout to a throwaway `QWidget` before rebuilding).

Rejected alternatives:
- *M4 keep the method-call but store an owner ref* — still couples the dialog to a concrete `MainWindow` API; the signal is cleaner and independently testable.
- *M5 make `gif_movies` a global LRU cache* — over-engineered; clearing per page refresh is simpler and already bounds it to visible items, matching the Ulaavi pattern the code follows.
- *M3 call `check_admin_permission` for menu enablement* — that method pops modal dialogs (login/permission-denied); wrong for silently greying a menu item. The silent `is_admin` read is correct for enablement; the action handlers keep their own `check_admin_permission` gate at execution time.

---

## 4. Detailed Design

### 4.1 M3 — admin flag via `main_window`
Add to `MediaDisplayWidget`:
```python
def _is_admin_user(self):
    """Return True if the owning MainWindow reports an admin session.

    The widget's Qt parent is the central QSplitter (main.py), which has no
    'is_admin' attribute; permission state lives on MainWindow, injected as
    self.main_window at construction.
    """
    return bool(getattr(self.main_window, 'is_admin', False))
```
`show_context_menu` replaces `parent_widget = self.parent(); is_admin = getattr(parent_widget, 'is_admin', False)` with `is_admin = self._is_admin_user()`. The bulk-action handlers (`bulk_mark_deprecated`, `bulk_delete`) retain their own `check_admin_permission` calls, so enablement and execution both consult `MainWindow`.

### 4.2 M4 — advanced-search signal + MainWindow handler
`AdvancedSearchDialog` gains a class-level signal and emits it instead of walking parents:
```python
class AdvancedSearchDialog(QtWidgets.QDialog):
    result_activated = QtCore.Signal(int)  # element_id
    ...
    def on_result_double_clicked(self, item):
        element_id = self.results_table.item(item.row(), 0).data(QtCore.Qt.UserRole)
        if element_id:
            self.result_activated.emit(int(element_id))
```
`MainWindow` gains:
```python
def on_advanced_search_result(self, element_id):
    """Handle activation of an advanced-search result: insert it (same path
    as a gallery double-click)."""
    self.on_element_double_clicked(element_id)
```
and connects the signal exactly once in `show_advanced_search`:
```python
def show_advanced_search(self):
    if not hasattr(self, "advanced_search_dialog") or self.advanced_search_dialog is None:
        self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.result_activated.connect(self.on_advanced_search_result)
    self.advanced_search_dialog.show()
    self.advanced_search_dialog.raise_()
```
The connect lives inside the lazy-construct guard so it is wired once per dialog instance.

### 4.3 M5 — bounded caches + debounce

**(a) `gif_movies`** — add to `MediaDisplayWidget`:
```python
def _clear_gif_movies(self):
    """Stop, disconnect, and drop all cached GIF QMovies (memory bound)."""
    for movie in self.gif_movies.values():
        try:
            movie.stop()
            movie.frameChanged.disconnect()
        except (RuntimeError, TypeError):
            pass  # not connected / already deleted
    self.gif_movies.clear()
```
Called at the top of `_update_views_with_elements` (right after `stop_current_gif()`), so movies never survive a page/list change.

**(b) `IconLoader` cache** — `_icon_cache` becomes an LRU `OrderedDict`, bounded, with negative caching:
```python
from collections import OrderedDict

class IconLoader(object):
    _instance = None
    _icon_cache = OrderedDict()
    _MAX_CACHE_ENTRIES = 256
    _MISS = QtGui.QIcon()          # shared sentinel for "not found / failed"
```
`get_icon` moves a hit to the MRU end; on a miss (file absent or render error) it stores `_MISS` under the key and returns it; after any insert it evicts the LRU entry while over the bound. The `print` WARNING/ERROR lines are replaced with module `logging` (CLAUDE.md L4). `get_pixmap` is left unbounded (it is not cache-backed).

**(c) `on_size_changed` debounce** — in `__init__`:
```python
self._pending_icon_size = None
self._size_debounce = QtCore.QTimer(self)
self._size_debounce.setSingleShot(True)
self._size_debounce.timeout.connect(lambda: self._apply_pending_size())
```
`on_size_changed` sets the icon size immediately (cheap, keeps the grid responsive), records `_pending_icon_size`, and (re)starts the 150 ms timer; `_apply_pending_size` performs the actual page reload. The `timeout` uses a `lambda` wrapper so `_apply_pending_size` is resolved by attribute lookup at fire time (keeps the slot monkeypatchable in tests).

### 4.4 M6 — Config-backed external player
`_get_config_player` reads and writes through the `Config` API and drops all `isinstance(dict)` gating and the `json.dump` branch:
```python
def _get_config_player(self):
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
                self.config.set('external_player', player_path)  # Config.set persists
            except Exception:
                log.exception("Failed to persist external_player to config")
            return player_path
    return None
```
`Config.set` writes to disk itself (`src/config.py:173-176`), so persistence is automatic. A module logger (`log = logging.getLogger(__name__)`) is added.

### 4.5 M7 — popup video/sequence detection by extension
`show_element` replaces the `type == 'video'/'sequence'` test with an extension check against the ingestion taxonomy (element `format` is `os.path.splitext(...)[1]`, i.e. dot-prefixed, e.g. `.mp4`/`.exr`; `type` is `2D`/`3D`/`Toolset`):
```python
VIDEO_EXTS    = ('.mov', '.mp4', '.avi', '.mxf')
SEQUENCE_EXTS = ('.exr', '.dpx', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.tga', '.bmp')

fmt = (element_data.get('format') or '').lower()
if fmt and not fmt.startswith('.'):
    fmt = '.' + fmt
frame_range = element_data.get('frame_range')
self.is_video    = fmt in VIDEO_EXTS
self.is_sequence = bool(frame_range) and fmt in SEQUENCE_EXTS
```
A single-frame still (`.png`, no `frame_range`) is correctly neither video nor sequence, mirroring `video_player_widget._is_sequence_element` (which also requires a `frame_range`). The extension lists are defined as module constants at the top of `media_info_popup.py`.

### 4.6 M13 — clean layout teardown on reset
`reset_settings` reparents the existing layout onto a throwaway `QWidget` (which adopts and later garbage-collects it and its child widgets) before rebuilding, so `setup_ui`'s `QVBoxLayout(self)` runs against a layout-free `self`:
```python
if reply == QtWidgets.QMessageBox.Yes:
    self.config.reset_to_defaults()
    old_layout = self.layout()
    if old_layout is not None:
        # Detach the old layout (and its child widgets) from self so setup_ui
        # can install a fresh QVBoxLayout(self) without the Qt "already has a
        # layout" warning. The throwaway widget owns and disposes them.
        QtWidgets.QWidget().setLayout(old_layout)
    self.setup_ui()
    QtWidgets.QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
    self.settings_changed.emit()
```

### 4.7 L2 — wire `BatchEditDialog` into the bulk menu
Add to `MediaDisplayWidget`:
```python
def open_batch_edit(self, selected_ids=None):
    """Open the batch metadata editor for the current multi-selection."""
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
The bulk branch of `show_context_menu` gains one action and its dispatch:
```python
bulk_edit_action = menu.addAction(get_icon('edit', size=16), "Batch Edit Metadata...")
...
elif action == bulk_edit_action:
    self.open_batch_edit(selected_ids)
```
**Interface assumption (SP1):** `BatchEditDialog._write_element` calls `self.db.update_element_metadata(element_id, **kwargs)`, which the live `DatabaseManager` does **not** yet expose (only `update_element` / `get_element_by_id` exist). SP1 (DB consolidation) merges `update_element_metadata`. SP6 therefore:
- wires the dialog open path (fully testable now), and
- marks the **apply-path** test `@pytest.mark.xfail(reason="L2 depends on SP1 db.update_element_metadata", strict=True)` so CI is green today and SP1 flips it to a real pass (strict xfail flags an accidental early xpass).

The dialog-open and menu-wiring behaviour does **not** depend on SP1 and is asserted as a hard pass.

---

## 5. Testing Strategy

All SP6 tests are **Tier 2 (`tests/gui`)**, run under `pytest-qt` with `QT_QPA_PLATFORM=offscreen`, and use the SP0 fixtures (`stax_db`, `stax_config`, `mock_nuke`, `qtbot`). Real widgets are constructed and behaviour asserted; mocks are used only to neutralise modal event loops (`QMenu.exec_`, `QDialog.exec_`, `QFileDialog.exec_`, `QMessageBox.question/information`) and to spy on debounced slots.

| Issue | Test (file) | Assertion |
|---|---|---|
| M3 | `test_admin_menu.py` | `MediaDisplayWidget._is_admin_user()` mirrors `main_window.is_admin` (True→True, False→False), proving the flag no longer comes from `self.parent()`. |
| M4 | `test_advanced_search.py` | `AdvancedSearchDialog` emits `result_activated(element_id)` on `on_result_double_clicked`; `MainWindow` has a callable `on_advanced_search_result` that runs without `AttributeError`. |
| M5 | `test_media_memory.py` | after `_update_views_with_elements([])`, `gif_movies == {}`; `IconLoader._icon_cache` stays `<= _MAX_CACHE_ENTRIES` after > bound distinct requests; a missing icon is cached (key present, returns the shared miss sentinel); `on_size_changed` does not call the reload synchronously (`_size_debounce.isActive()`), and fires it exactly once after the interval. |
| M6 | `test_external_player.py` | with `external_player` in `Config`, `_get_config_player()` returns it (read path un-gated); with the file dialog monkeypatched to pick a path, the choice persists via `Config.set` and survives reloading `Config` from the same path. |
| M7 | `test_media_info_popup.py` | `show_element` sets `is_video` for a `.mp4`/`2D` element, `is_sequence` for a `.exr`/`2D` element with a `frame_range`, and neither for a `.abc`/`3D` element or a lone `.png` still. |
| M13 | `test_settings_reset.py` | `reset_settings` (with `QMessageBox` monkeypatched to Yes/None) installs a fresh layout and emits **no** Qt message containing "already has a layout" (captured via `qInstallMessageHandler`). |
| L2 | `test_batch_edit_wiring.py` | `open_batch_edit([id1, id2])` (with `BatchEditDialog.exec_` monkeypatched) constructs and returns a `BatchEditDialog`; `open_batch_edit([id1])` returns `None`. **xfail(strict):** `stax_db` exposes `update_element_metadata` (the SP1 apply-path dependency). |

**Fixtures/helpers.** A local `fake_main_window` (a `QMainWindow` with `is_admin` and a `check_admin_permission` stub) is used where a widget needs a `main_window` without constructing the full app. `MediaDisplayWidget` is built as `MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=fake_main_window)`. The `MainWindow` tests reuse the SP0 pattern (`monkeypatch.setenv("STOCK_DB", ...)`, `mock_nuke`, `stax_config`).

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Constructing `MediaDisplayWidget`/`MainWindow` headlessly pulls heavy deps (ffmpeg, preview worker). | SP0 already proves `MainWindow` constructs offscreen with `mock_nuke`; SP6 tests construct the leaf widgets directly where possible and only build `MainWindow` for M4's method-presence check. |
| `movie.frameChanged.disconnect()` raises when nothing is connected. | Wrapped in `except (RuntimeError, TypeError)` — the normal Qt outcome for a disconnect-with-no-slots. |
| Negative icon caching hides an icon that appears on disk later in the session. | Acceptable: StaX ships a fixed icon set under `resources/icons`; a cache miss means a genuinely absent name. `clear_cache()` remains available. |
| Debounce interval (150 ms) feels laggy or races the test. | Interval is a module-visible constant; tests assert *deferral + single fire* via `qtbot.waitUntil`, not wall-clock timing. |
| The L2 apply path can't be exercised until SP1. | Dialog-open path is asserted now; the DB dependency is `xfail(strict=True)` and named, so SP1 flips it green and an accidental early merge xpasses loudly. |
| `AdvancedSearchDialog` double-imported as both `src.ui.dialogs` and `ui.dialogs` (two module objects). | SP6 tests import UI widgets via `src.ui.*` — the same path `main.py`/the widgets use — so the signal identity matches production. |

---

## 7. Deliverables Checklist
- [ ] M3: `MediaDisplayWidget._is_admin_user()`; `show_context_menu` reads admin from `main_window`.
- [ ] M4: `AdvancedSearchDialog.result_activated` signal; `MainWindow.on_advanced_search_result`; connected in `show_advanced_search`.
- [ ] M5: `_clear_gif_movies()` on refresh; LRU-bounded, miss-caching `IconLoader`; debounced `on_size_changed`.
- [ ] M6: `_get_config_player` uses `Config.get/set`.
- [ ] M7: popup detects video/sequence by format/extension.
- [ ] M13: `reset_settings` reparents the old layout before rebuild.
- [ ] L2: `open_batch_edit` + bulk-menu action; SP1 apply-path test `xfail(strict)`.
- [ ] `tests/gui` coverage for every item; `pytest -m "not manual"` is green (0 failed/errored; the one documented xfail).

---

## 8. Follow-on
SP7 (packaging) and SP8 (code-quality / god-module split) are unaffected by SP6's behaviour changes. When **SP1** merges `DatabaseManager.update_element_metadata`, the L2 apply-path `xfail(strict)` in `test_batch_edit_wiring.py` flips to a pass with no SP6 code change required.
