<p align="center"><img src="resources/logo.png" alt="StaX"></p>

# StaX — Codebase Analysis, Audit & Competitive Review

**Prepared:** 2026-07-22
**Scope:** Full-repository deep analysis of StaX (`d:\Scripts\modern-stock-browser`) — ~20,000 lines of Python across backend, GUI, Nuke integration, media processing, and build tooling.
**Contents:** (1) What StaX is and how it's built, (2) complete feature inventory, (3) ranked audit of discovered issues with fixes, (4) enhancement recommendations, (5) competitor feature-gap analysis, (6) open-source building blocks to adopt, (7) prioritized action plan.

---

## 1. Executive Summary

StaX is an ambitious, feature-rich **stock-footage & VFX asset manager purpose-built for Foundry Nuke**. It organizes media into a Stacks → Lists → Elements hierarchy, ingests image sequences/video/geometry/toolsets with automatic sequence detection and preview generation, and drags assets directly into the Nuke node graph. On paper the feature set rivals commercial tools. The engineering foundation is genuinely capable in places (network-aware locking, an ffmpeg pipeline, a mock/real Nuke bridge, a WebGL 3D viewer, a REST API, an extensibility hook system).

**The headline problem is integration debt, not missing capability.** A significant share of the "completed" features are **half-wired or dead**:

- **Two mutually incompatible database layers** ship side by side. Live UI and API code call methods that only exist in never-applied "patch"/"additions" files, guaranteeing `AttributeError` crashes today (Batch Edit, several API endpoints, analytics).
- The **async preview worker is started but never fed a single job** — ingestion still blocks the GUI thread, the exact problem that worker was written to solve.
- The **virtualized lazy gallery is never instantiated**; the real gallery decodes a full page of thumbnails synchronously on the UI thread.
- **Duplicate detection, batch-edit dialog, and several patch modules are orphaned** dead code.

Layered on top are real **security concerns** (unsandboxed `exec()` of processor scripts, unsalted SHA-256 + default `admin/admin`, archive path-traversal and unverified binary downloads in the installer, arbitrary-file read via the 3D viewer's local HTTP server) and **cross-platform breakage** (the ffmpeg wrapper is hard-coded to `.exe` names, so all media processing is dead on Linux/macOS despite `requires-python` being cross-platform).

**Bottom line:** StaX is roughly 70% of a compelling product with 30% of its advertised features non-functional and a handful of serious safety issues. The highest-leverage work is *consolidation and wiring-up*, not new features — reconcile the two DB layers, actually connect the async worker and lazy gallery, close the security holes, then differentiate with AI tagging/visual search (where every competitor is now investing).

---

## 2. What StaX Is & How It's Built

### 2.1 Purpose
A desktop media browser + asset-management tool for VFX pipelines, integrating tightly with Nuke. It manages large collections of stock footage, image sequences, 3D geometry, and Nuke toolsets, with dual-path storage (physical "hard copy" repository vs. reference "soft copy" links), rich auto-generated previews, and drag-and-drop deployment into Nuke.

### 2.2 Technology Stack
| Layer | Technology |
|---|---|
| Language | Python 3.9+ (headers still claim dual 2.7/3.x — see issues) |
| GUI | PySide2 (Qt5), Fusion style + custom dark palette + QSS |
| Database | SQLite with WAL, external advisory file-locking for network shares |
| Media | FFmpeg/FFprobe/FFplay (bundled), ffpyplayer for embedded playback |
| 3D | GLB via `js-3d-model-viewer` in a `QWebEngineView`; Blender headless / trimesh / pygltflib conversion |
| API | Flask + werkzeug (stdlib `wsgiref` fallback), REST on localhost |
| Packaging | Three parallel systems: cx_Freeze, PyInstaller, Inno Setup; UV-based dependency install |
| Host integration | Nuke (standalone `QApplication` mode + in-Nuke dockable panel) |

### 2.3 Module Map
```
main.py                 App shell, 3-pane window, docks, auth, service startup
menu.py / init.py       In-Nuke menu + plugin bootstrap
nuke_launcher.py        Standalone + embedded StaXPanel (dual-mode)
src/
  db_manager.py         DatabaseManager — schema, CRUD, migrations, auth, tags
  file_lock.py          Cross-platform advisory file locking
  ingestion_core.py     Ingest pipeline: sequence detect, copy, convert, preview
  duplicate_detection.py  Perceptual-hash dedup (ORPHANED)
  preview_worker.py     Async QThread preview generator (WIRED BUT UNFED)
  preview_cache.py      In-memory LRU QPixmap cache
  api_server.py         REST API (QThread WSGI server)
  extensibility_hooks.py  Pre/Post-ingest & Post-import Python processors (exec)
  config.py             Config merge + env overrides + DB-backed settings
  ffmpeg_wrapper.py     Thumbnails/GIFs/videos/probing (WINDOWS-ONLY names)
  nuke_bridge.py        NukeBridge (mock/real) + NukeIntegration (insert/toolset)
  geometry_viewer.py    Localhost HTTP server + QWebEngine GLB viewer
  glb_converter.py / convert_to_glb.py   Multi-backend GLB conversion
  video_player_widget.py  ffpyplayer-based embedded player
  ui/                   ~15 panels/dialogs (gallery, settings, analytics, ...)
  db_manager_additions.py / db_migrations.py / *_patch.py   ORPHANED patch files
tools/                  Installers, ffmpeg downloader, CLI, build scripts
tests/                  Mostly manual scripts; low automated coverage
```

---

## 3. Complete Feature Inventory

### 3.1 Organization & Data Model
- **Hierarchical structure**: Stacks → Lists → nested Sub-Lists (self-referential `parent_list_fk`, cascade deletes) → Elements. Elements typed `2D` / `3D` / `Toolset`.
- **Dual-path storage**: soft copy (reference in place) or hard copy (files copied into `stack/list/name/` in the repository).
- **Tagging**: comma-joined tag strings with add/append/replace/remove, aggregate tag list, and multi-tag filtering.
- **Favorites**: per machine + user, uniquely constrained.
- **Playlists**: shared, ordered, collaborative collections with creator tracking and reordering.
- **Settings**: key/value config persisted both to `config.json` and a DB `settings` table; `STOCK_DB` env override for the DB location.

### 3.2 Ingestion Pipeline
- **Automatic image-sequence detection**: four configurable frame patterns (`.####.`, `_####.`, ` ####.`, `-####.`), directory sibling scan, frame-range discovery, padding detection, ffmpeg `%0Nd` pattern generation.
- **Metadata extraction**: extension→type mapping, file/sequence size, ffmpeg-probed dimensions/codec/fps/duration, video-vs-image heuristic.
- **Copy policies**: soft/hard, per-ingest.
- **3D conversion to GLB**: copy existing glb/gltf, or Blender headless CLI (with idle-timeout watchdog), or trimesh/pygltflib fallback.
- **Batch ingest**: `ingest_multiple`, `ingest_folder` (recursive) with sequence-member deduplication.
- **Library ingest dialog**: recursive folder scan → auto-builds a Stacks/Lists/Sub-Lists preview tree → bulk ingest with sequence collapsing.

### 3.3 Preview Generation & Caching
- **FFmpeg-based previews**: 512px still thumbnails, mid-frame sequence thumbnails, two-pass palette-optimized animated GIFs, low-res MP4 proxies (libx264, faststart) for sequences/video.
- **In-memory LRU pixmap cache** with hit/miss/eviction stats and preloading.
- **Async preview worker** (`PreviewWorker` QThread + priority queue) — *implemented but not fed jobs; see issue C4*.

### 3.4 GUI & Browsing
- **3-pane main window**: left Stacks/Lists/Tags nav, center media display, right video/3D preview pane, plus dockable History / Settings / Analytics panels.
- **Dual view modes**: icon gallery (`QListWidget`) and 6-column table, in a `QStackedWidget` with an empty-state page.
- **Thumbnail grid** with favorite/deprecated status badges, type-icon fallbacks, live size slider (64–512px).
- **Animated GIF hover preview** (`QMovie`) and **Alt+hover info popup** with metadata.
- **Search**: inline tag syntax (`#tag`, `tag:value`) in the browse bar + a full Advanced Search dialog (property/match/value).
- **Pagination** (first/prev/next/last, items-per-page, range label), server-side pagination in the DB layer.
- **Context menus**: single-item and multi-select bulk ops (favorite, add-to-playlist, insert, edit, deprecate, delete).
- **Focus mode** collapsing all chrome to maximize the browser.
- **Theming**: Fusion + dark QPalette + `style.qss` with icon-URL rewriting; singleton SVG icon loader.

### 3.5 Media Preview
- **Embedded video player** (ffpyplayer): timeline scrubber, play/pause/stop, frame stepping, external-player launch, metadata panel.
- **Image-sequence playback** via generated MP4 preview.
- **Interactive 3D preview**: GLB streamed from a localhost `HTTPServer` into a `QWebEngineView` WebGL viewer.

### 3.6 Nuke Integration
- **Dual mode**: standalone `QApplication` app, or an in-Nuke dockable `PythonPanel` registered via `registerWidgetAsPanel`.
- **Drag-and-drop to DAG**: 2D→`Read` (with parsed frame range + sequence printf pattern), 3D→`ReadGeo`/`ReadGeo2` (`.abc`), Toolset→node paste.
- **Toolset registration**: save current node selection as a `.nk` toolset into the repository with preview + DB catalog + hooks.
- **Mock/real bridge**: every op has a mock branch, enabling headless use and testing.
- **Guest auto-login** in-Nuke (read-only), full login dialog standalone; admin-gated settings/deletes.

### 3.7 Extensibility & Automation
- **Custom processor hooks**: Pre-Ingest (validate/cancel), Post-Ingest (after catalog), Post-Import (after node creation) — user Python scripts exec'd with a context dict and a `result` contract.
- **REST API** (localhost, token auth): health, stacks, lists, elements (get/patch/ingest), search, analytics-top.
- **CLI** (`stax_cli.py`): full REST client with token auth and table/JSON output.

### 3.8 Analytics, History, Users
- **Analytics panel**: insertion logging, custom bar charts, top-assets / over-time / by-user tabs, CSV export.
- **Ingestion history panel** with CSV export.
- **User/permission management**: admin/user roles, sessions, password change, user CRUD, soft-delete.

### 3.9 Infrastructure
- **Network-aware SQLite**: external file lock (`msvcrt`/`fcntl`), WAL, busy-timeout, retry with backoff+jitter.
- **Logging** (`StaXLogger`) + a global stdout/stderr **DebugManager** toggle.
- **Dependency bootstrap** for portable `lib/` + bundled ffpyplayer/ffmpeg on `PATH`.
- **Packaging**: cx_Freeze (two exes), PyInstaller spec, Inno Setup installer that patches `.nuke/init.py`, UV installer scripts, per-platform ffmpeg downloader.

---

## 4. Audit — Discovered Issues (Ranked)

Issues are grouped by severity. IDs: **C**=Critical, **H**=High, **M**=Medium, **L**=Low. File:line references point at the exact code.

### 🔴 CRITICAL

#### C1 — Two incompatible database layers; live code calls methods that don't exist
**Files:** `src/db_manager_additions.py` (whole), `src/db_migrations.py` (whole), callers below.
The live `DatabaseManager` uses lowercase tables (`elements`, `lists`, `ingestion_history`) and a per-call `get_connection()` context manager. A second set of files (`db_manager_additions.py`, `db_migrations.py`, `ingestion_core_patch.py`) assumes a *different* class shape — persistent `self.conn`, `self._lock`, and capitalized tables (`Elements`, `InsertionLog`, `Users`). The "additions" file is *apply-by-hand instructions that were never applied*, yet live code calls its methods:
- `src/api_server.py:124` `count_elements_by_list`, `:148` `update_element_metadata`, `:192` `get_top_inserted_elements`
- `src/ui/batch_edit_dialog.py:362` `update_element_metadata`
- `src/ui/analytics_panel.py:278-325` `get_top_inserted_elements` / `get_insertions_by_month` / `_by_user` / `get_total_insertions`

`db_migrations.run_migrations` (`db_migrations.py:163`) is documented as "wired into `__init__`" but is **never called**, so `SchemaVersion`, the `phash` column, and `InsertionLog` are never created.
**Failure:** `AttributeError` on Batch Edit and on the affected API endpoints; analytics silently show empty charts forever (the `try/except` in the panel swallows the error, and `InsertionLog` is never written anyway).
**Fix:** Choose one layer. Either merge the needed methods into `DatabaseManager` (rename to the real lowercase schema, replace `self.conn`/`self._lock` with `with self.get_connection() as conn:`, add an `ingestion_history`/insertion write path, actually call `run_migrations`), **or** delete the additions/migrations files and the callers' dependence on them. Add a smoke test that opens Batch Edit and hits every API endpoint.

#### C2 — Arbitrary code execution via unsandboxed `exec()` of processor scripts
**File:** `src/extensibility_hooks.py:44-55`.
`ProcessorHook.execute` reads a script path from config and `exec(script_code, hook_globals)` with `hook_globals['__builtins__'] = __builtins__` (full builtins: `open`, `__import__`, `os`), despite a comment claiming a "safe execution environment." Script paths come from `config.json`, which in a studio deployment typically lives on a **writable network share**.
**Failure:** Anyone who can write that config or the referenced script gains code execution in every artist's Nuke session on ingest.
**Fix:** Load processor scripts only from a locked-down, admin-owned directory; validate the resolved path is inside it (reject relative/`..`/network paths). For real isolation, run hooks in a restricted subprocess. Remove the misleading "safe execution environment" comment.

#### C3 — Installer: archive path-traversal + unverified binary download
**File:** `tools/ffmpeg_downloader.py:15-28, 43-62`.
FFmpeg is fetched from third-party hosts (`gyan.dev`, `johnvansickle.com`, `evermeet.cx`) with **no SHA-256, no signature, no version pinning** ("release-essentials" is a moving target), then `zipfile`/`tarfile` `.extractall()` is called with **no member sanitization / no extraction filter** (classic Zip-Slip / CVE-2007-4559), with a bare `except:` swallowing failures.
**Failure:** A MITM or upstream compromise ships arbitrary binaries that run on artists' machines and get bundled into the installer; a crafted archive writes files outside the temp dir.
**Fix:** Pin exact versioned URLs, ship+verify a SHA-256 per platform (fail closed on mismatch), and pass `filter="data"` to `extractall` (Py≥3.12) or validate each member path is within the destination. Remove the bare `except`.

#### C4 — Advertised async pipeline is dead: ingestion still blocks the GUI thread
**Files:** `main.py` (starts worker), `src/ingestion_core.py:710-849` (synchronous), `src/ui/media_display_widget.py:164/607-721` (lazy gallery unused), `main.py:714-743` / `src/ui/ingest_library_dialog.py:365-476` (ingest on UI thread).
Three separate "make it responsive" mechanisms exist but are not connected:
1. `PreviewWorker` is started (`main.py` `_start_preview_worker`) and its signals wired, but **nothing ever calls `submit()`** — the only `PreviewJob(...)` constructions live in the never-applied `ingestion_core_patch.py`. Live `ingest_file` still generates thumbnail/GIF/MP4/Blender-GLB **synchronously on the calling thread**.
2. `LazyGalleryView` (virtual scroll, LRU eviction) is **never imported**; `media_display_widget.py:164` instantiates a plain `DragGalleryView`, and `_update_views_with_elements` decodes a whole page of `QPixmap`s + per-element `is_favorite` DB round-trips synchronously on the UI thread.
3. Bulk ingestion runs directly in the handler behind a `QProgressDialog`, pumped only by `QApplication.processEvents()` (`dialogs.py:1277-1287`).
**Failure:** The window goes "Not Responding" during ingest (Blender conversion can block for its 900s idle timeout); selecting a list of 100–500 items freezes the UI for seconds.
**Fix:** Route `ingest_file`'s preview block through `get_preview_queue().submit(PreviewJob(...))`; move ingestion to a `QThread` driven by signals (never `processEvents()`); actually instantiate `LazyGalleryView` or offload pixmap decode to the worker via `on_preview_ready`. Then delete `ingestion_core_patch.py`.

### 🟠 HIGH

#### H1 — Unsound network lock + WAL on a network share
**Files:** `src/file_lock.py:151-155`, `src/db_manager.py:127`.
`FileLockManager.release()` `os.remove()`s the lock file — a classic delete-on-release race: after A unlinks the file, B (blocked on the old inode) and C (opening a fresh inode) can both believe they hold the lock. Separately, `get_connection` sets `PRAGMA journal_mode = WAL`, which SQLite explicitly **does not support on network filesystems** — the stated deployment target.
**Failure:** Two artists ingesting simultaneously lose writes or corrupt the DB; WAL `-shm/-wal` files on SMB cause "database is malformed" / disk-I/O errors.
**Fix:** Create the lock file once and keep it (only unlock the byte range + close the handle). Use `journal_mode = DELETE`/`TRUNCATE` on network shares. Rely on one consistent locking scheme rather than an ad-hoc lock file layered over SQLite's own.

#### H2 — Weak auth: unsalted SHA-256 + shipped default `admin`/`admin`
**File:** `src/db_manager.py:346-355, 426-431, 1505, 1533, 1640`.
Passwords are a single unsalted `sha256(password).hexdigest()`; both schema creation and Migration 3 auto-insert user `admin` / password `admin` with admin role, and nothing forces a change.
**Failure:** A readable DB on a share allows offline cracking of all passwords; default credentials grant full admin to anyone.
**Fix:** Use a salted slow KDF (`pbkdf2_hmac`/bcrypt/argon2) with per-user salt; generate a random initial admin password or force reset on first login; never ship known default creds.

#### H3 — Duplicated, signature-swapped favorite methods silently break favorites
**File:** `src/db_manager.py:898/1004 (add_favorite), 908/1034 (remove_favorite), 918/1075 (get_favorites)`.
Each method is defined twice; Python keeps the **last** definition. The argument order changed between copies (`(element_id, machine_name, user_name)` vs `(element_id, user_name, machine_name)`), and the surviving `get_favorites` requires exact `user_name = ?` where the discarded one was NULL-safe.
**Failure:** Positional callers store machine name into the user column and vice-versa; favorites are added under one identity and queried under another → they "disappear." (Compounds UI3's inconsistent call signatures.)
**Fix:** Delete the dead first copies, keep one canonical signature, and update all call sites to match.

#### H4 — Media processing is Windows-only, breaking the cross-platform promise
**File:** `src/ffmpeg_wrapper.py:35-45`.
Binary names are literal `ffmpeg.exe`/`ffprobe.exe`/`ffplay.exe`, so `get_ffmpeg()` raises `RuntimeError` on Linux/macOS — yet `pyproject.toml` sets `requires-python >=3.9`, the ffmpeg downloader installs non-`.exe` binaries on POSIX, and `run_standalone.ps1` probes for a Unix `ffmpeg` name. All previews/probing/playback are dead on non-Windows.
**Fix:** Select the binary name by `sys.platform` (append `.exe` only on Windows) or use `shutil.which`.

#### H5 — In-Nuke menu commands call methods on the wrong object
**File:** `menu.py:99-100, 115, 130`.
Commands do `panel = nuke_launcher.show_stax_panel(); panel.ingest_files()` etc. But in Nuke mode `show_stax_panel()` returns the `registerWidgetAsPanel(...).addToPane()` result, **not** a `StaXPanel`, which has no `ingest_files`/`register_toolset`/`show_advanced_search`. Each invocation also spawns a second panel.
**Failure:** Quick Ingest / Register Toolset / Advanced Search raise `AttributeError` inside Nuke.
**Fix:** Keep a module-level `StaXPanel` singleton and return the live widget from an accessor the menu uses.

#### H6 — GeometryViewer HTTP server reads arbitrary local files and never shuts down
**File:** `src/geometry_viewer.py:75-90 (translate_path), 96-143 (/model/)`.
The `/model/` handler base64-decodes a token into an **absolute path** and streams *any* file on disk; `translate_path` maps unknown URLs under `project_root` with `..`-traversal exposure. Binds `127.0.0.1` but has no auth/allow-list, and the `serve_forever` thread is a process-lifetime singleton never stopped.
**Failure:** Any local process (or embedded-browser content) can read arbitrary files via `http://127.0.0.1:<port>/model/<b64>`; the thread lingers after the pane closes.
**Fix:** Restrict `/model/` to a registered allow-list of GLB paths, reject anything outside a previews root, and add a shutdown hook.

#### H7 — Drop-ingest passes wrong config type + wrong key + fragile thread lifetime
**File:** `src/ui/media_display_widget.py:320-411`.
`IngestionCore(self.db, self.config)` passes the `Config` **object** while everywhere else it's `self.config.get_all()` (a dict); copy policy is read as `self.config.get('copy_policy', 'soft')` but the real key is `default_copy_policy`; the worker `thread` is a local only referenced by lambda slots, with `thread.wait(3000)` after `dialog.exec_()`.
**Failure:** `IngestionCore` may mishandle object-vs-dict; copy policy is silently wrong; ingest exceeding 3s after dialog close risks GC/teardown mid-run.
**Fix:** Pass `self.config.get_all()`, use `default_copy_policy`, and hold a member reference to the thread until `finished`.

#### H8 — Global stdout/stderr hijack suppresses unrelated output (incl. errors) inside Nuke
**File:** `src/debug_manager.py:37-43, 87-90`.
At import (triggered from `nuke_launcher.py` and `menu.py`) the DebugManager replaces `sys.stdout`/`sys.stderr` process-wide; when `debug_mode` is false, `_DebugStream.write` **drops all writes** — not just StaX's — silencing Nuke's own console and other tools' tracebacks for the whole session.
**Fix:** Scope suppression to StaX's own logger; never swallow `stderr`; don't replace interpreter streams inside a host app.

### 🟡 MEDIUM

#### M1 — SQL built with string-formatted column names (injection primitive)
**File:** `src/db_manager.py:886/889 (search_elements), 858 (update_element), 1615-1621 (update_user)`.
`search_elements` does `"... WHERE {} LIKE ?".format(property_name)` with **no whitelist** (the whitelisted version only exists in the orphaned additions file). `update_element` also `.format()`s caller-supplied keys into `SET`.
**Fix:** Whitelist `property_name` and `update_element` keys against the known column list before formatting.

#### M2 — API: non-constant-time token check + arbitrary-file ingest
**File:** `src/api_server.py:91, 229, 152-175`.
Token compared with `!=` (timing side channel); stored plaintext; `POST /elements/ingest` accepts any `filepath` from the body and ingests it after `os.path.isfile` (arbitrary-file ingestion / traversal).
**Fix:** Use `hmac.compare_digest`; hash the stored token; validate `filepath` against an allowlist of ingest roots.

#### M3 — Admin bulk actions permanently disabled (wrong parent lookup)
**File:** `src/ui/media_display_widget.py:1125-1126`.
`show_context_menu` reads `is_admin` from `self.parent()`, but the widget's parent is the `QSplitter` (main.py:233), so `getattr(splitter, 'is_admin', False)` is always `False`.
**Failure:** "Mark All as Deprecated" / "Delete All Selected" are greyed out even for admins.
**Fix:** Use `self.main_window.check_admin_permission`, matching the single-item path.

#### M4 — Advanced-search double-click calls a nonexistent method
**File:** `src/ui/dialogs.py:122-127`.
`on_result_double_clicked` calls `self.parent().on_advanced_search_result(...)`, which `MainWindow` doesn't define → `AttributeError` on every result double-click.
**Fix:** Add `on_advanced_search_result` to `MainWindow` or emit a signal the owner connects.

#### M5 — Unbounded `QMovie`/icon/preview caches leak memory across navigation
**Files:** `src/ui/media_display_widget.py:44/644-650` (gif_movies), `src/icon_loader.py:19/56` (icon cache), `src/preview_cache.py` (bounded — OK).
`self.gif_movies` is populated with `CacheAll` movies keyed by element id and **never cleared/evicted** when the list changes; `frameChanged` lambdas stay connected. The icon cache is unbounded and keyed by live slider size (64–512), so dragging mints hundreds of entries and misses aren't cached.
**Fix:** Clear/disconnect `gif_movies` at the start of `_update_views_with_elements` (or LRU-bound to visible items); bound the icon cache and cache negative results.

#### M6 — Video/config type confusion breaks the embedded player's persistence
**File:** `src/video_player_widget.py:722-757`.
All config access is gated behind `isinstance(self.config, dict)`, but `config` is a `Config` object, so the external-player path is never persisted (re-prompted every time) and a `json.dump(self.config, ...)` would fail if reached.
**Fix:** Use `self.config.get('external_player')` / `self.config.set(...)`.

#### M7 — MediaInfoPopup video controls are dead (type-taxonomy mismatch)
**File:** `src/ui/media_info_popup.py:308-317`.
`is_video = type == 'video'` / `is_sequence = type == 'sequence'`, but element types are `2D`/`3D`/`Toolset`, so the scrubber/play/stop UI never appears.
**Fix:** Detect by format/extension (as `video_player_widget._is_sequence_element` does).

#### M8 — GIF palette temp-file race
**File:** `src/ffmpeg_wrapper.py:365`.
A fixed shared `palette.png` in the temp dir is used for two-pass GIF generation; concurrent jobs clobber each other's palette and the `os.remove` cleanup races.
**Fix:** Use a per-call `NamedTemporaryFile`/`mkdtemp` removed in `finally`.

#### M9 — No timeouts on any ffmpeg subprocess call
**File:** `src/ffmpeg_wrapper.py:67,158,201,239,307,337,399,436,482,530`.
A hung/huge decode blocks the calling thread forever; some run on the UI thread (`get_media_info` from selection changes), so one bad file freezes the app.
**Fix:** Pass `timeout=` and handle `TimeoutExpired`.

#### M10 — ffplay deadlock via unread PIPEs
**File:** `src/ffmpeg_wrapper.py:275-279`.
Background `Popen` sets `stdout=PIPE, stderr=PIPE` but nothing reads them; ffplay blocks when its ~64KB stderr buffer fills.
**Fix:** `DEVNULL` the streams (or drain on a thread); add `CREATE_NO_WINDOW` on Windows.

#### M11 — Three divergent, individually-broken build definitions
**Files:** `StaX.spec:6-13,50` (absolute `D:/Scripts/...` paths), `tools/build_installer.py:76-157` (regenerates a *different* PyInstaller spec), `setup_freeze.py` (cx_Freeze — what `build.ps1` actually calls), plus `pyproject.toml` missing `cx-freeze` so `uv sync --all-extras` → build aborts ("cx_Freeze not found").
**Fix:** Pick one packager, delete the others, remove absolute paths (derive from `__file__`), and declare the build tool in `pyproject.toml`. Fix cx_Freeze icon to `.ico` (`setup_freeze.py:206` uses a PNG). Single-source the version (`pyproject.toml` `0.1.0` vs `build_installer.py` `1.0.0`).

#### M12 — PIL can't decode core VFX formats; hardcoded 4-digit padding in the worker
**File:** `src/preview_worker.py:244, 290, 328`.
`PIL.Image.open` can't read `.exr`/`.dpx`/`.mxf`; the MP4 pattern hardcodes `%04d` regardless of real padding.
**Fix:** Route decoding through `ffmpeg_wrapper` (as the sync path does) and derive padding from detected sequence info. (Prerequisite for wiring C4 correctly.) **Better:** adopt **OpenImageIO** for thumbnail decode — it natively reads EXR/DPX and every VFX format and is the industry standard (see §7, building blocks). Derive padding from **Fileseq** rather than a regex.

#### M13 — SettingsPanel.reset re-runs setup on a widget that already has a layout
**File:** `src/ui/settings_panel.py:954-965`.
`reset_settings` empties the layout's items then calls `setup_ui()`, which does `QVBoxLayout(self)` while `self` still owns the old layout → Qt "already has a layout" warning, orphaned widgets.
**Fix:** Delete the old layout (reparent to a throwaway widget) or rebuild values in place.

#### M14 — Logger writes into the (read-only) install dir; no rotation; new file per process
**File:** `stax_logger.py:26-37`.
Logs go to `logs/` next to the module; under `%ProgramFiles%\StaX` that's not user-writable, so logging silently degrades. A fresh timestamped file is created every process start (initialized from `init.py`, `menu.py`, `nuke_launcher.py`) with no rotation.
**Fix:** Write to `%LOCALAPPDATA%\StaX\logs`, add rotation, initialize once.

### 🟢 LOW

- **L1 — `init.py:38-48` adds CWD-relative Nuke plugin paths** (`./tools`, `./src/ui`); if Nuke's CWD isn't the StaX root, imports silently fail. `subdir.lstrip('./')` is a char-set strip, not a prefix strip. *Fix:* use `os.path.join(stax_root, subdir)`.
- **L2 — `batch_edit_dialog.py` is unwired** — the multi-select menu never opens it, and it calls `update_element_metadata` (missing method). *Fix:* wire it in or delete it.
- **L3 — `nuke_bridge_patch.py` is orphaned and stale** — references `self.nuke_bridge`/`paste_toolset` that don't exist; documents an analytics hook never called by real `insert_element`. *Fix:* delete.
- **L4 — Pervasive exception swallowing** — bare/blanket `except: pass` across `db_manager` cleanup, `config` load/save (only `print`s), `ingest_file` outer catch (masks the C1 `AttributeError`s as "Ingestion failed"), and many UI/video paths. *Fix:* narrow exceptions, log with `logging.exception`.
- **L5 — Duplicate detection linear O(N)/O(N²) scan; MD5 fallback corrupts distance semantics** (`duplicate_detection.py:105-112,135-157`). *Fix:* bucket phashes (BK-tree); in MD5 mode compare only for exact equality.
- **L6 — Reads serialized behind one global OS lock** (`db_manager.py`) — even read-only ops from API + GUI + worker contend, defeating WAL's concurrent readers. *Fix:* scope the external lock to writes; reuse a per-thread connection.
- **L7 — Contradictory Python 2.7 claims + dead compat shims** across many files while the app imports PySide2/Flask/numpy≥2/`secrets`/`shutil.which` (Py3-only). Under a Py2 Nuke these `ImportError` and are silently swallowed, so the API + preview worker vanish with no signal. *Fix:* pick one interpreter, drop the false claims/shims.
- **L8 — Fragile frame-range parsing** (`nuke_bridge.py:95-100`) — `split('-')` breaks on negative first frames; non-numeric raises uncaught. *Fix:* regex parse + guard — or better, delegate all frame-range/sequence parsing to **Fileseq** (see §7), which correctly handles negative frames, stepped ranges (`1-10x2`), and missing frames.
- **L9 — CLI plaintext HTTP + token in argv** (`tools/stax_cli.py:87,125`). *Fix:* support HTTPS; prefer `STAX_API_TOKEN` env var.
- **L10 — Code duplication / god classes** — `_resolve_path` duplicated in 4 files; dark palette duplicated in `main.py` vs `dark_palette.py`; file-size formatting in 3 files; bulk-menu built twice; `MediaDisplayWidget` (~1544 lines), `dialogs.py` (1302, 11 classes + stray `main()`), `video_player_widget.py` (1107) are god modules. *Fix:* extract shared utils, split responsibilities.
- **L11 — Silent playlist-migration data loss** (`db_manager.py:469-534`, Migration 6) — the `playlist_items` rebuild swallows copy failures then renames/drops the original. *Fix:* verify row counts and raise on mismatch so the transaction rolls back.

### Orphaned / dead-code summary
| File | Status |
|---|---|
| `db_manager_additions.py` | Never pasted into `DatabaseManager`; called by live code → `AttributeError` (C1) |
| `db_migrations.py` | `run_migrations` never called; incompatible schema (C1) |
| `ingestion_core_patch.py` | Apply-by-hand patch never applied; async previews/dup-check never integrated (C4) |
| `nuke_bridge_patch.py` | Stale skeleton referencing nonexistent methods (L3) |
| `duplicate_detection.py` | Loaded but never invoked in live ingest; depends on missing `phash` column (C4) |
| `preview_worker.py` | Thread started, zero job submitters (C4) |
| `lazy_gallery_view.py` | Never imported; real gallery is synchronous (C4) |
| `batch_edit_dialog.py` | Never opened by the UI (L2) |

### Test-quality assessment
Automated coverage of the risky surface is **essentially zero**. `pytest.ini` sets `testpaths = tests`, but `test_network_sqlite.py` has no `test_`-prefixed functions (collects nothing), `test_nuke_launcher.py` is a manual GUI harness (`sys.exit(app.exec_())`, asserts nothing), and `test_ingest_library_sequences.py` spins up a real `QApplication`. There are no unit tests for `NukeBridge`/`NukeIntegration`, `FFmpegWrapper` subprocess argv, `dependency_bootstrap`, the DB layer, or any build script. The `tests/` dir is polluted with non-tests, a 190KB `gui_main_backup.py`, a vendored `Ulaavi/` tree, and duplicate helpers. **Recommended:** unit-test `FFmpegWrapper` (mock subprocess, assert argv/timeouts/POSIX names), `NukeIntegration` against `NukeBridge(mock_mode=True)`, the DB CRUD/migrations, and a smoke test that instantiates `MainWindow` + hits every API endpoint (would have caught C1 immediately). Move manual GUI scripts out of `tests/`.

---

## 5. Enhancement Recommendations (Beyond Bug Fixes)

**Architecture & code health**
1. **Consolidate the DB layer** into a single `DatabaseManager` with a versioned migration runner; delete all `*_additions`/`*_patch` files. (Resolves C1, unblocks analytics/API/batch-edit.)
2. **Establish a threading contract**: all ingest, preview generation, ffmpeg probing, and video decode off the GUI thread via the existing `PreviewWorker`/`QThread` patterns. (Resolves C4, H7, M9.)
3. **Extract shared utilities** (`path_resolver`, `size_format`, `dark_palette`) and split the god modules; adopt `logging` everywhere instead of `print`.
4. **Introduce a real test suite + CI** (headless, mock-based) and a lint/type pass (`ruff`, `mypy`), gating merges.

**Product**
5. **Smart/dynamic collections** (saved searches that auto-populate) and **ratings/color labels**.
6. **Bulk metadata editing wired in** (finish `batch_edit_dialog`) and **inline rename**.
7. **Configurable columns + sort** in table view; **hover/spacebar quicklook** (Eagle-style) in addition to Alt-hover.
8. **OpenColorIO-aware thumbnails** so EXR/DPX previews are color-correct (VFX-critical; ties to M12).
9. **Proxy/optimized-media generation on ingest** for smooth network playback (CatDV-style).
10. **Onboarding & safety**: force default-admin password change on first run; per-user writable log/config locations.

> Many of these can be built on proven open-source libraries rather than from scratch — see **§7, Open-Source Building Blocks**, which maps concrete libraries (OpenImageIO, Fileseq, OpenColorIO, Assimp, OpenAssetIO, Pyblish, OpenRV, Qt.py, …) onto StaX's features, audit fixes, and competitor gaps.

---

## 6. Competitor Analysis & Feature-Gap List

StaX sits at the intersection of three markets: **local/network asset browsers for CG/VFX artists** (its closest analogs), **animation/VFX pipeline platforms**, and **media asset managers (MAM)**. Notably, **Prism Pipeline is already vendored in this repo's `examples/` folder** — a direct reference competitor.

### 6.1 Competitor landscape
| Tool | Category | Positioning |
|---|---|---|
| **Connecter** (DesignConnected) | Local-first "Hybrid DAM" for 3D/VFX | Closest analog — folder+tag org, 3D viewer, DCC drag-drop, free desktop app |
| **Eagle** | Design/media asset organizer | Best-in-class browsing, AI autotag, visual search |
| **Prism Pipeline** | Artist-friendly VFX/animation pipeline | Asset library + ingest + deliveries; plugs into Kitsu/ftrack/ShotGrid |
| **AYON / OpenPype** (Ynput) | Open-source pipeline platform | USD, versioning, reviews/approvals, broad DCC integration |
| **Autodesk Flow (ShotGrid)** / **ftrack** / **Kitsu** | Production tracking | Shots/tasks/reviews at studio scale |
| **CatDV** (Quantum) | Broadcast MAM | Proxy transcode, AI logging/transcription |
| **axle.ai** | On-prem AI MAM | Browser-based, AI tags/scene descriptions, transcripts |
| **Daminion** | Lightweight MAM | Cost-effective SMB media cataloging |

### 6.2 Features competitors have that StaX lacks
Ranked by strategic value for StaX's target user (VFX artist browsing local/network libraries):

| # | Feature | Who has it | Why it matters | Effort |
|---|---|---|---|---|
| 1 | **AI auto-tagging** (vision LLM writes tags/descriptions — OpenAI/Anthropic/Google/local Ollama) | Eagle, Connecter, CatDV, axle.ai | Eliminates the biggest manual chore; the industry's current center of gravity | Med |
| 2 | **Visual / similarity search** — search-by-image, "find similar," color search | Eagle | Finding the right plate/texture by look, not filename | Med–High |
| 3 | **Working duplicate finder** (StaX has the code but it's *orphaned* — C4) | Eagle | Storage savings + library hygiene; StaX is one wiring job away | Low (finish existing) |
| 4 | **Team sync of metadata & previews while heavy files stay local** ("Hybrid DAM") | Connecter | Multi-artist libraries without moving TBs to cloud | High |
| 5 | **Broader DCC integration** (Blender, Houdini, Maya, C4D, Unreal, Resolve, After Effects) | Connecter, AYON | Grows StaX beyond Nuke-only | Med (per host) |
| 6 | **Online free-library integration** (Poly Haven, AMD GPU Open) | Prism | Instant content without leaving the tool | Med |
| 7 | **Review / annotation / approval** (OpenRV-style playback + notes) | AYON, ShotGrid, ftrack | Ties asset browsing to the review loop | High |
| 8 | **USD support** (references, variants, resolver) | AYON | Increasingly the interchange standard | High |
| 9 | **Version control of assets** (versions, publishes, "Version Zero") | Anchorpoint (Git), AYON, Prism | Safe iteration, rollback | Med–High |
| 10 | **Production-tracking integration** (Kitsu/ftrack/ShotGrid plugins) | Prism, AYON | Connect assets to shots/tasks | Med |
| 11 | **Speech-to-text / transcription search** | CatDV, axle.ai | Searchable dialogue in footage | High (external AI) |
| 12 | **Smart folders / dynamic collections, ratings, color labels** | Eagle, Connecter | Faster organization at scale | Low–Med |
| 13 | **Hover / spacebar quicklook** for instant preview | Eagle | Faster triage than click-to-preview | Low |
| 14 | **Custom metadata fields / schemas** | axle.ai, CatDV | Studio-specific taxonomy | Med |
| 15 | **Web/browser-based access** | axle.ai | Remote/producer access without install | High |

### 6.3 Where StaX already competes well
- **Deep, native Nuke drag-to-DAG** with sequence-aware Read/ReadGeo/toolset creation — more DCC-native than Eagle/Daminion.
- **Automatic image-sequence detection & frame-range handling** — a VFX-specific strength MAMs handle poorly.
- **Dual hard/soft copy storage** — flexible repository model.
- **Extensible Python processor hooks + REST API + CLI** — pipeline-friendly (once security-hardened).
- **Built-in interactive 3D GLB viewer** — parity with Connecter's interactive viewer.
- **Free / self-hosted, no per-seat cloud fees** — a real advantage vs ShotGrid/ftrack/CatDV.

---

## 7. Open-Source Building Blocks to Adopt

Source: `examples/opensource_recources.md` (the "Awesome CG / VFX Pipeline" list). StaX currently re-implements several things the VFX industry has mature, battle-tested open-source libraries for — and several competitor gaps from §6 map onto standards StaX could simply adopt. This section catalogs the highest-value ones and ties each to a specific StaX feature, audit issue, or competitor gap.

### 7.1 High-priority adoptions (map directly onto current code & audit fixes)

| Library | What it is | Where it fits in StaX | Ties to |
|---|---|---|---|
| **OpenImageIO (OIIO)** | Industry-standard library for reading/writing EXR, DPX, TIFF and all VFX image formats | Replace PIL for thumbnail decode so **EXR/DPX previews actually render** — the core VFX formats StaX can't currently thumbnail | Fixes **M12**; enables enhancement #8 |
| **Fileseq** | Robust frame-range & file-sequence parsing (`1-10x2`, negative frames, missing frames, padding) | Replace/harden the homegrown 4-pattern `SequenceDetector` in `ingestion_core.py` and the fragile `split('-')` range parse in `nuke_bridge.py` | Fixes **L8**; hardens §3.2 sequence detection |
| **OpenColorIO (OCIO)** | AWSF unified color-management (ACES/…) | Color-correct EXR/DPX thumbnails and previews instead of raw linear data shown as sRGB | Enhancement #8; VFX credibility |
| **Assimp** (or **meshio**) | Portable importer for ~40 3D model formats | Collapse the three-backend GLB conversion mess (Blender headless + trimesh + pygltflib) toward a single dependency, or as a fast fallback | Simplifies `glb_converter.py`/`convert_to_glb.py` |
| **F3D** | Fast minimalist 3D viewer with **thumbnail generation** and broad format support | Generate 3D thumbnails for the gallery (StaX currently has no still thumbnail for geometry) and/or as an alternate/headless geometry preview | Fills a gap in §3.5 3D preview |
| **Qt.py** | Thin abstraction over PySide2/PySide6/PyQt | Future-proof the entire GUI: **Nuke 16 moved to PySide6**, but StaX is hard-locked to PySide2. Qt.py eases that migration incrementally | De-risks the biggest forward-compat threat |
| **Pyblish** | Test-driven validation/publishing framework for VFX | Formalize StaX's Pre/Post-Ingest processor hooks on a proven plugin framework (with a real sandboxed contract) instead of raw `exec()` | Relates to **C2**; hardens §3.7 hooks |
| **rclone / rsync** | Fast incremental/cloud file transfer | Robust, resumable hard-copy ingestion into the repository, and a foundation for team/cloud sync | Enables competitor gap #4 (hybrid team sync) |
| **Riffle** | PySide filesystem browser with sequence grouping | Reference implementation for the Ingest Library dialog's folder-scan/sequence-collapse tree | Improves §3.2 library ingest |

### 7.2 Strategic adoptions (unlock competitor-gap features from §6)

| Library / standard | What it unlocks | Competitor gap closed |
|---|---|---|
| **OpenAssetIO** | An interoperability standard between content-management systems (like StaX) and DCCs. Implementing the manager side lets **any** OpenAssetIO-aware DCC resolve StaX assets — a standardized alternative to writing per-host bridges | #5 broader DCC integration, #10 pipeline integration |
| **OpenRV** (AWSF) / **DJV** / **mrv2** / **xSTUDIO** | Professional review/flipbook players. Wire one in as the "external player" and as the basis for review/annotation | #7 review / annotation / approval |
| **OpenTimelineIO (OTIO)** | Editorial-timeline interchange | Export playlists as OTIO timelines; import cut lists to auto-build Lists — bridges StaX to editorial |
| **USD** + **usd-qtpy** / **UsdQt** / **USD Manager** | USD parsing and ready-made Qt USD widgets | #8 USD support (references, variants, thumbnails) |
| **Kitsu** / **Ramses** / **Stalker** (+ **ftrack-hooks**) | Open-source production trackers with documented APIs | #10 production-tracking integration (link assets↔shots/tasks) |
| **OpenColorIO** + **Colour** | Color science toolkits | Correct display transforms, color-search groundwork for gap #2 (visual/color search) |
| **Rez** / **bleeding-rez** | The VFX-standard package/environment manager | Cleaner, studio-friendly deployment than the current `lib/`-folder + `PATH` bootstrap (relates to L7 / packaging M11) |

### 7.3 Also worth tracking (lower priority / situational)
- **Clique**, **pyseq** — alternative sequence parsers if Fileseq doesn't fit.
- **Lucidity** — filepath-template system; could formalize the repository's `stack/list/name/` path convention and make it configurable.
- **NodeGraphQt** / **Nodz** — Qt node-graph widgets, if StaX ever adds a node-based relationship/dependency view.
- **RIFE for Nuke** — ML frame interpolation; a possible value-add processor for retimed footage.
- **OpenEXR / pfstools / ImageMagick** — additional HDR/format tooling behind OIIO.
- **Dailies** (ffmpeg/Nuke/RV wrapper) — reference for automated review-media generation; also demonstrates ShotGrid/ftrack/Kitsu integration patterns.

### 7.4 Net takeaway
The single most impactful adoption is **OpenImageIO** — it turns StaX's preview system from "works for JPEG/PNG/MP4" into "works for the EXR/DPX sequences that are the actual content of a VFX library," and it's the prerequisite for color-correct (OCIO) previews. Pair it with **Fileseq** (retire the homegrown detector) and **Qt.py** (survive the PySide6 transition), and StaX is on far more durable foundations. The strategic tier (**OpenAssetIO**, **OpenRV**, **USD**) is how StaX closes the biggest competitor gaps using standards instead of bespoke code.

---

## 8. Prioritized Action Plan

**Phase 0 — Stop the bleeding (days)**
- C1: Reconcile the two DB layers (unblocks Batch Edit, API, analytics). Add the MainWindow+API smoke test.
- C2: Sandbox/restrict processor-script `exec()`.
- C3: Pin + checksum the ffmpeg download; sanitize archive extraction.
- H2: Kill default `admin/admin`; salt+KDF passwords.
- H4: Fix ffmpeg binary names for cross-platform.

**Phase 1 — Make the advertised features real (weeks)**
- C4: Wire `PreviewWorker` + `LazyGalleryView`; move ingest to a QThread. Route worker decode through **OpenImageIO** (§7) so EXR/DPX finally thumbnail, and parse sequences with **Fileseq** (fixes M12 + L8 at the source).
- H1: Fix the lock-file race + WAL-on-share.
- H3/M3/M4/M6/M7/H7: Fix the functional UI bugs users hit daily.
- H5/H6/H8: Nuke menu targets, GeometryViewer file-read lockdown, DebugManager scope.
- Finish/rewire duplicate detection (gap #3 above — nearly free).

**Phase 2 — Harden & de-duplicate (weeks)**
- M1/M2: SQL whitelist + constant-time token + ingest-path allowlist.
- M8–M14, L-series: races, timeouts, caches, build consolidation, logging locations.
- Extract shared utils, split god modules, add real tests + CI + lint/type gates.

**Phase 3 — Differentiate (months)**
- AI auto-tagging (gap #1) and visual/similarity search (gap #2) — the highest-value modern features.
- Smart collections, ratings, quicklook (gaps #12–13) — cheap wins.
- Broader DCC integration via **OpenAssetIO** and/or a **Kitsu/ftrack** bridge (gaps #5, #10) — standards over bespoke code (§7).
- **OpenColorIO**-correct previews and proxy generation for VFX credibility; **OpenRV**/**DJV** for review, **OTIO** for editorial interchange, **USD** support for gap #8.
- Migrate the GUI onto **Qt.py** to be ready for Nuke 16's PySide6.

---

## Appendix — Sources (Competitor Research)
- Connecter — [connecterapp.com](https://connecterapp.com/), [designconnected.com/connecter](https://www.designconnected.com/connecter)
- Eagle — [en.eagle.cool](https://en.eagle.cool/), [AI Autotagger](https://community-en.eagle.cool/plugin/4B56113D-EB3E-4020-A82C-6214FA08CB14)
- Prism Pipeline — [prism-pipeline.com](https://prism-pipeline.com/), [Kitsu plugin docs](https://prism-pipeline.com/docs/latest/plugins/Kitsu/)
- AYON / OpenPype — [ayon.app](https://ayon.app/product/pipeline), [ynput.io/ayon](https://ynput.io/ayon/)
- CatDV — [quantum.com asset management](https://www.quantum.com/en/products/asset-management/)
- axle.ai — [axle.ai/axle-mam](https://www.axle.ai/axle-mam)
- Foundry Nuke ecosystem — [foundry.com/products/nuke](https://www.foundry.com/products/nuke-family/nuke)
- DAM tool roundups — [Digital Project Manager](https://thedigitalprojectmanager.com/tools/best-digital-media-asset-management-software-for-animation/), [Anchorpoint](https://www.anchorpoint.app/blog/video-asset-management-software)
