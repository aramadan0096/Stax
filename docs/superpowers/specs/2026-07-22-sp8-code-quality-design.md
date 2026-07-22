# SP8 — Code Quality & Consistency — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). This is the **final, cross-cutting cleanup** sub-project. It runs **after SP1–SP7** so it de-duplicates and hardens code whose functional bugs have already been fixed by the earlier SPs.

---

## 1. Background & Motivation

Two low-severity audit findings are pure code-health debt that every earlier SP had to work around but none owned:

- **L4 — Pervasive exception swallowing.** Bare `except:` / `except Exception: pass` and `print()`-only error paths are scattered across the codebase (10 bare `except:` sites; **135 `print(` calls** across 14 `src/` modules, worst offender `src/config.py` with 15). The `ingest_file` outer catch (`src/ingestion_core.py:902`) even *masks* real `AttributeError`s as a generic "Ingestion failed" string, which is exactly how C1 hid for so long. Errors are invisible to `caplog`, to log files, and to users.
- **L10 — Code duplication / god classes.** The same helpers are copy-pasted:
  - **`_resolve_path` / `_resolve_storage_path` in 4 files** — `src/ui/media_display_widget.py:1091`, `src/ui/media_info_popup.py:510`, `src/video_player_widget.py:618`, `src/ui/drag_gallery_view.py:26`.
  - **The dark palette twice** — `src/dark_palette.py:28` `apply_dark_palette` vs `main.py:793` `_apply_fallback_palette` (and the two copies have **already diverged**: the `main.py` copy is missing the `QPalette.LinkVisited` color — the exact class of bug DRY prevents).
  - **File-size formatting in 3 files** — `src/ui/media_display_widget.py:709`, `src/ui/media_info_popup.py:289`, `src/video_player_widget.py:676/923`.
  - **The bulk-operations menu built twice** in one file — `src/ui/media_display_widget.py:1128-1167` (`show_context_menu`) and `:1346-1370` (`show_bulk_menu`).
  - **God modules** — `MediaDisplayWidget` (~1544 lines), `dialogs.py` (1302), `video_player_widget.py` (1107).

SP0's harness (real-schema `stax_db`, headless Qt, `mock_nuke`, characterization tests) is now green and is the safety net that makes this refactor safe: **every extraction is proven behavior-preserving by a test.**

### Program context (decisions already locked)
- **Cleanup only.** No functional/behavior changes beyond error-handling/logging. The SP0 characterization tests must stay green.
- **Windows + Linux.** Hybrid 3-tier testing. Flat/`src.`-prefixed imports (match the file being edited). `logging`, not `print`. TDD + frequent conventional commits.
- **DRY / YAGNI.** Bounded scope, not a rewrite. The god-module split is *recommended* but deliberately *deferred* (see §4.6) to avoid colliding with SP2/SP6 and ballooning scope.

---

## 2. Goals / Non-Goals

### Goals
- One shared `resolve_path` (`src/utils/paths.py`) replacing the 4 copies, behavior-identical per call site.
- One shared `human_size` (`src/utils/formatting.py`) replacing the 3 file-size formatters.
- The dark palette consolidated to **only** `src/dark_palette.py`; `main.py._apply_fallback_palette` deleted.
- A **single bulk-menu builder** on `MediaDisplayWidget`, reused by both `show_context_menu` and `show_bulk_menu`.
- An established **error-handling pattern** (narrowed exception → `logging`) applied to a concrete, bounded set of the highest-value L4 offenders.
- Unit tests for the extracted utilities (resolve_path hard/soft/relative; human-size B/KB/MB/GB boundaries); `caplog` tests proving the converted error paths **log and return the safe fallback** instead of swallowing silently; characterization tests proving each consolidated helper reproduces the prior behavior of every removed copy.

### Non-Goals (explicitly deferred)
- **Splitting the god modules** (`MediaDisplayWidget`, `dialogs.py`, `video_player_widget.py`). Recommended in §4.6, deferred to a follow-up — see the rationale there.
- Converting **all** 135 `print(` calls / all 10 bare excepts. SP8 establishes the pattern and applies it to a bounded, enumerated set; the long tail is mechanical follow-up.
- Touching `nuke_bridge.py._resolve_storage_path` (a 5th, identical copy). It lives in a file SP5 owns; it is listed as a one-line follow-up, not done here, to avoid cross-SP churn.
- Any functional fix (M3 admin-gating, M5 gif-cache leak, H7 drop-ingest bugs). Those belong to SP6; SP8 must *preserve* their code paths untouched.
- Logger relocation/rotation (M14) — that is its own concern.

---

## 3. Approach

**Extract-and-migrate, test-first, one concern per commit.** For each duplication: write the shared helper + its unit tests (TDD, red→green), then migrate each call site and prove behavior is preserved with a characterization test, then delete the copy. For L4: establish the `logging.getLogger(__name__)` + narrowed-`except` pattern, apply it to the enumerated offenders, and lock the new "logs + safe fallback" behavior with `caplog` tests.

**Rejected alternatives:**
- *Split the god modules now.* High risk (weak GUI test coverage of those exact regions), and it would collide head-on with SP2 (async pipeline rewires ingest + gallery in `media_display_widget.py`) and SP6 (UI-correctness fixes M3/M5/H7 in the same file). Deferred.
- *Boil the ocean on L4* (convert all 135 prints). Unbounded, low marginal value per site, and noisy diffs. Establish the pattern + fix the worst offenders instead.
- *A single "always strip + always consult config" resolve_path.* Would change behavior for the 3 simple-variant sites (they never consulted `config`). Instead the unified helper takes optional `project_root` / `config` params so each call site reproduces its exact prior branch.

---

## 4. Detailed Design

### 4.1 `src/utils/` package

New package `src/utils/` (`__init__.py`, `paths.py`, `formatting.py`). `src/__init__.py` already exists, so `from src.utils.paths import resolve_path` resolves from any `src` module, and `from utils.paths import resolve_path` resolves in tests (both repo-root and `src` are on `sys.path` via `conftest.py`). Imports in edited files **match the file's existing style** (`media_display_widget.py`, `media_info_popup.py`, `video_player_widget.py`, `drag_gallery_view.py` all use `from src.xxx import ...`).

### 4.2 `paths.resolve_path`

The 4 copies are two shapes:

| Shape | Files | Behavior |
|---|---|---|
| **Simple** | `media_display_widget:1091`, `media_info_popup:510`, `video_player_widget:618` | `strip`; `None`/empty → `None`; `isabs` → `normpath`; else `normpath(join(self._project_root, path))`. Never consults `config`. |
| **Storage** | `drag_gallery_view:26` | `None`/empty → `None`; `isabs` → `normpath`; else `config.resolve_path(path)` if config, else `normpath(join(self._project_root, path))`. (No strip.) |

Unified single function covering both via optional params:

```python
# src/utils/paths.py
import os


def resolve_path(path, project_root=None, config=None):
    """Resolve a stored (possibly relative) asset path to an absolute filesystem path.

    Args:
        path (str | None): The stored path. Empty / whitespace-only returns None.
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

Call-site migration (behavior-preserving — all three `_project_root`s already resolve to the repo root):
- Simple sites → `resolve_path(path, project_root=self._project_root)`.
- Storage site → `resolve_path(path, project_root=self._project_root, config=self.config)`.

**One deliberate normalization:** the unified helper strips whitespace for *all* callers, whereas the storage variant previously did not. This only affects pathological whitespace-padded stored paths and is documented; it is not a functional change.

### 4.3 `formatting.human_size`

The 3 existing formatters diverge:

| Site | Current behavior |
|---|---|
| `media_display_widget:709` (table) | `MB` (`.1f`) if `< 1024 MB` else `GB` (`.2f`); `''` when no size. |
| `media_info_popup:289` | same as above; `'N/A'` when no size. |
| `video_player_widget:676/923` | always `MB` (`.2f`). |

Canonical formatter with full B/KB/MB/GB boundaries:

```python
# src/utils/formatting.py
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

Call sites keep their own **"no size" guard** (`''` / `'N/A'`) so that behavior is preserved; only the numeric formatting is delegated to `human_size`:
- `media_display_widget`: `size_str = human_size(element['file_size']) if element.get('file_size') else ''`
- `media_info_popup`: `size_str = human_size(file_size) if file_size else 'N/A'`
- `video_player_widget`: `human_size(size_bytes)` in the status/metadata strings.

**One deliberate display refinement** (flagged for reviewer veto): `human_size` reproduces the old output for every file **≥ 1 MB** (`5 MiB → "5.0 MB"`, `2 GiB → "2.0 GB"`), but for **sub-MB** files it now shows `KB`/`B` (e.g. `512 KiB → "512.0 KB"`) instead of the old `"0.5 MB"`, and normalizes the video player's `.2f` to `.1f`. This is a pure display-string refinement (no data/behavior change), it is exactly the B/KB/MB/GB behavior the SP8 test brief asks for, and it makes three divergent formatters consistent. Characterization tests assert **both** the reproduced ≥1MB outputs and the new sub-MB outputs.

### 4.4 Dark-palette consolidation

Delete `main.py:793 _apply_fallback_palette`. Hoist `from src.dark_palette import apply_dark_palette` to `main.py`'s top-level imports and call it directly. The current `try/except ImportError → fallback` (a stale transitional deploy net; `src/dark_palette.py` *is* shipped) becomes a single call wrapped in an L4-consistent guard that **logs** on failure rather than silently applying a divergent copy:

```python
try:
    apply_dark_palette(app)
except Exception:
    logging.getLogger(__name__).exception("Failed to apply dark palette; using default")
```

This also silently fixes the already-diverged `LinkVisited` omission (single source of truth). Behavior differs only in the never-hit failure branch.

### 4.5 Single bulk-menu builder

Extract two private methods on `MediaDisplayWidget`, reused by both `show_context_menu` (multi-select branch) and `show_bulk_menu`:

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
    if action == actions['fav']:
        self.bulk_add_to_favorites(selected_ids)
    elif action == actions['playlist']:
        self.bulk_add_to_playlist(selected_ids)
    elif action == actions['deprecate']:
        self.bulk_mark_deprecated(selected_ids)
    elif action == actions['delete']:
        self.bulk_delete(selected_ids)
```

Behavior preserved exactly by parameterizing the two differences:
- `show_context_menu` (multi-select): `with_header=True`, passes its existing `is_admin` value **unchanged** (M3's buggy parent lookup is SP6's fix — SP8 must not touch that line).
- `show_bulk_menu`: `with_header=False`, `is_admin=True` (it never gated deprecate/delete → equivalent to admin-enabled).

### 4.6 God-module split — recommended, **deferred**

The smallest high-value split of `media_display_widget.py` (1544 lines) would extract two self-contained controllers:
- a **GIF-hover controller** (the `self.gif_movies` cache at `:44`, the `QMovie` create/start/stop logic at `:642-648`, `:974-1018`), and
- a **drop-ingest controller** (`dragEnterEvent`/`dropEvent` at `:274-411`).

**SP8 recommends this but does not perform it**, because:
1. **Cross-SP collision.** SP2 (async pipeline) rewires ingestion + the gallery inside this exact file; SP6 fixes M5 (the `gif_movies` leak) and H7 (drop-ingest config/thread bugs) in these exact regions. Refactoring them in SP8 would create avoidable merge conflicts and re-touch code another SP just fixed.
2. **Weak safety net.** Behavior-preserving GUI extraction needs stronger characterization coverage of these event handlers than currently exists; building that is larger than SP8's cleanup remit.

Recommendation recorded here as a **follow-up** (after SP2/SP6 land): extract `GifHoverController` and `DropIngestController` from `MediaDisplayWidget`; leave `dialogs.py` (11 classes + stray `main()`) and `video_player_widget.py` as separate later follow-ups. This is the YAGNI-correct call: ship the low-risk, high-value dedup now; defer the risky structural split.

### 4.7 L4 — error-handling pattern + bounded application

**Pattern:** module-level `import logging` + `logger = logging.getLogger(__name__)`; replace bare/blanket swallows with a narrowed `except` that logs and returns the existing safe fallback:
- unexpected error that returns a fallback → `logger.exception(...)`;
- recoverable/expected miss → `logger.warning(...)`;
- benign cleanup (best-effort close/release) → `except Exception:` + `logger.debug(...)` (never bare `except:`).

**Bounded, enumerated target set** (the highest-value offenders named in the audit):

| # | File:line | Now | Change |
|---|---|---|---|
| 1 | `src/config.py:150-152,165-167` (+ `_load_from_database`/`_save_to_database`/`ensure_directories` prints) | `print("Failed to ...")` | `logger.exception(...)` / `logger.info(...)` — full print→logging pass on this one module (worst offender). |
| 2 | `src/db_manager.py:172-173,180-181` | bare `except:` in `get_connection` cleanup | `except Exception: logger.debug("...")` |
| 3 | `src/ingestion_core.py:902` | outer `except Exception` builds "Ingestion failed" string (masks C1) | add `logger.exception(...)` before the existing log + return |
| 4 | `src/ingestion_core.py:506-507` | `except Exception: pass` (Blender idle) | `logger.warning(...)` |
| 5 | `main.py:646-647` | analytics `except Exception: pass` | `logger.warning("Analytics logging failed: ...")` |
| 6 | `src/video_player_widget.py:674-675` | `except Exception: size_bytes = 0` (getsize) | `except OSError: logger.debug(...)` |

All keep their existing return/fallback value — **no control-flow change**, only visibility.

---

## 5. Testing Strategy

3-tier (SP0 harness), all headless.

**Unit (Tier 1) — extracted utilities:**
- `tests/unit/test_paths.py` — `resolve_path`: absolute→normpath; relative→join(project_root); `None`/`''`/whitespace→`None`; whitespace-padded relative→stripped+joined (reproduces the simple variant); `config` consulted first and its result normalized; `config` returning falsy → project_root fallback (reproduces the storage variant).
- `tests/unit/test_formatting.py` — `human_size` boundaries: `0→"0 B"`, `512→"512 B"`, `1024→"1.0 KB"`, `1536→"1.5 KB"`, `1048576→"1.0 MB"`, `5*1048576→"5.0 MB"` (reproduces old ≥1MB output), `2*1024**3→"2.0 GB"`, `512*1024→"512.0 KB"` (documented refinement), non-numeric→`"0 B"`.

**Unit (Tier 1) — L4 logging via `caplog`:**
- `tests/unit/test_config_logging.py` — malformed `config.json` → `Config` logs at `ERROR` and still exposes defaults (safe fallback); save into an unwritable target → logs at `ERROR`, no raise. Asserts a record is captured, proving the path no longer swallows silently.

**GUI (Tier 2):**
- `tests/gui/test_bulk_menu.py` — construct `MediaDisplayWidget` (fixtures `stax_db`, `stax_config`, `NukeBridge(mock_mode=True)`); `_populate_bulk_menu` returns 4 dispatchable actions with the expected texts; `with_header=True` adds a header action, `with_header=False` does not; `is_admin=False` disables deprecate+delete. This is the characterization lock proving the two former menus are equivalent.
- Dark palette: covered by the existing SP0 `test_mainwindow_smoke` (MainWindow still constructs after the fallback is removed).

**Characterization guard:** the full SP0 suite (`pytest -m "not manual"`) must stay green after every task — it is the proof that no behavior regressed.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| A migrated call site changes behavior for an edge case | Per-site params reproduce the exact prior branch; unit + characterization tests assert reproduced outputs before the copy is deleted. |
| The `human_size` sub-MB refinement is unwanted | Flagged prominently (§4.3) for reviewer veto; if vetoed, keep the old MB/GB rounding in `human_size` and drop the sub-MB assertions — one-line change. |
| Bulk-menu refactor collides with SP6's M3 fix | The buggy `is_admin` computation line is left **untouched**; only menu *construction* is extracted. |
| God-module split scope-creep | Deferred entirely (§4.6) with explicit cross-SP rationale; SP8 ships only the bounded dedup. |
| `caplog` misses records because a converted path uses `stax_logger` (print-based) not stdlib `logging` | The pattern uses stdlib `logging.getLogger(__name__)` precisely so `caplog` captures it. |

---

## 7. Deliverables Checklist
- [ ] `src/utils/` package with `paths.resolve_path` + `formatting.human_size`.
- [ ] 4 `_resolve_path`/`_resolve_storage_path` copies replaced by the shared helper.
- [ ] 3 file-size formatters replaced by `human_size`.
- [ ] Dark palette consolidated to `src/dark_palette.py`; `main.py._apply_fallback_palette` deleted.
- [ ] Single bulk-menu builder (`_populate_bulk_menu` / `_dispatch_bulk_action`) used by both menus.
- [ ] L4 error-handling pattern established + applied to the 6 enumerated offenders.
- [ ] Unit tests (paths, formatting), `caplog` logging tests (config), GUI characterization (bulk menu); full suite green.
- [ ] God-module split recorded as a post-SP2/SP6 follow-up (not implemented).

---

## 8. Follow-on
SP8 closes the audit-remediation program. Remaining mechanical debt (the long tail of `print`→`logging`, `nuke_bridge._resolve_storage_path`, and the recommended `GifHoverController`/`DropIngestController` split) is captured as follow-ups to be scheduled after SP2/SP6 have landed, so they refactor already-fixed, already-rewired code rather than racing it.
