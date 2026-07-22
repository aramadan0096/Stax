# EP6 — Ingestion Automation & Job Queue — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F031 (watch folders), F032 (ingest recipes), F033 (central job-queue dashboard), F034 (retry failed jobs), F035 (background transcode profiles), F036 (proxy quality presets), F037 (auto duplicate-handling policies), F038 (preflight validation checklist), F039 (ingest completion notifications), F040 (scriptable action chains).

---

## 1. Background & Motivation

StaX ingestion after **SP2** is asynchronous — a shared `IngestWorker(QThread)` runs `IngestionCore.ingest_file` per job off the GUI thread, and a long-lived `PreviewWorker(QThread)` renders thumbnail/GIF/MP4 previews from a `PriorityQueue`. But that pipeline is **fire-and-forget and invisible**: there is no durable record of what was ingested, no way to see pending/running/failed work, no retry, no unattended ingestion, and no per-job configuration. Studios expect a MAM/DAM ingest surface: point StaX at a **watch folder**, apply a saved **recipe** (copy policy + proxy profile + duplicate policy + tags + metadata template), watch a **job dashboard** show progress, **retry** the failures with one click, get a **completion notification**, and hang **scriptable actions** off the tail of ingest.

EP6 builds that surface **on top of SP2's workers — it does not build a second execution queue.** SP2 owns *execution* (the two QThreads). EP6 adds a **durable job ledger** (`ingest_jobs`), a **dashboard dock** that reads the ledger and controls SP2's workers (retry re-submits, cancel flags the worker), a **stdlib polling watch scanner** (no `watchdog` dependency), **recipes/profiles/policies** persisted as config overlays that feed SP2's existing config-driven `PreviewWorker`, a pure **preflight validator**, a **notification center**, and a **whitelisted action-chain executor** (deliberately *not* the `exec()`-based `extensibility_hooks` path — see C2).

### Locked design decisions
- **Watch folders via a stdlib POLLING scanner.** `WatchFolderScanner(QThread)` scans configured folders at a configurable interval using `os.scandir` — **no new dependency** (no `watchdog`). Watch config lives in a `watch_folders` table; the folder-diff logic is a pure, Qt-free function (`scan_folder`) so it is unit-testable without threading.
- **The dashboard wraps SP2's async worker/queue — no second queue.** `ingest_jobs` is a **state ledger/mirror**, not an executor. Rows are written before submission and updated from `IngestWorker`'s `progress`/`file_done`/`ingest_finished` signals. Retry reconstructs a failed row's `(source_path, target_list_id)` and hands it to a **new `IngestWorker`**; cancel sets the worker's existing `cancel()` flag and marks still-pending rows `cancelled`. **SP2's `IngestWorker`/`PreviewWorker` interface is stated as an assumption (§5); integration wiring is `xfail(strict=True)` tagged `SP2` where the worker is not present.**
- **Proxy/transcode profiles reuse SP2's config-driven `PreviewWorker`.** A profile is a named bundle of the preview-config keys `PreviewWorker._process` already reads (`preview_size`, `gif_size`, `gif_fps`, `sequence_preview_fps`, `generate_video_previews`), mapped through the SP3-hardened `ffmpeg_wrapper`. No `ffmpeg_wrapper` signature changes and **no new codec knobs are invented** — only the parameters `generate_video_preview`/`generate_sequence_video_preview` already expose (`max_size`, `fps`, `duration`).
- **Duplicate policies reuse SP2's wired `duplicate_detection`.** SP2 already computes a phash and returns `duplicate_skipped`. EP6 generalizes the binary skip into a policy enum (`allow`/`skip`/`version`/`ask`) resolved by a pure function.
- **Action chains are whitelisted, not `exec()`.** A chain is an ordered list of `{action, params}` steps dispatched to a **registry of built-in handlers** (`add_tag`, `set_field`, `move_to_list`, `generate_proxy`, `notify`). Arbitrary Python is never evaluated — EP6 does not reintroduce the C2 RCE.
- Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`; conventional commits.

### Dependencies
- **SP2** — `IngestWorker(db, config_dict, jobs, copy_policy)` with signals `progress(done,total,label)`, `file_done(dict)`, `ingest_finished(success,skipped,errors)`, `ingest_failed(str)`, and `cancel()`; the singleton `PreviewWorker` via `get_preview_queue()`; and `ingest_file` returning `{'success', 'reason'=='duplicate_skipped', ...}` with wired `duplicate_detection`. The dashboard wraps these. **Auto-tag / template application at ingest is coordinated with EP4** (recipe → `metadata_template_id`).
- **SP3** — cross-platform `ffmpeg_wrapper` (`get_ffmpeg()`, `generate_video_preview`, `generate_sequence_video_preview`) used by proxy profiles.
- **EP4** — a recipe may reference a `metadata_template_id`; an action-chain `set_field` step writes a custom field. These bits are EP4-gated and `xfail(strict=True)` tagged `EP4` until EP4 lands.
- **SP1** — consolidated `DatabaseManager`, `get_connection(write=…)`, migration runner, column whitelisting. If executing before SP1, drop the `write=` kwarg.
- **SP0** — fixtures `stax_db`, `stax_config`, `tiny_sequence`, `tiny_png`, headless Qt (`qtbot`, `QT_QPA_PLATFORM=offscreen`), 3-tier layout, flat imports.

### Delivery clusters
- **6A — Job queue, retry, notifications (F033, F034, F039):** the `ingest_jobs` ledger + CRUD, the `JobQueueDashboard` dock, the `notifications` center, and the wiring that feeds the ledger from `IngestWorker`. Independently shippable; the pure ledger/notification CRUD ships even before SP2's worker is wired.
- **6B — Watch folders, recipes, dup policies, preflight (F031, F032, F037, F038):** the polling scanner, recipe store + config overlay, the duplicate-policy resolver, the preflight validator + dialog. Independently shippable; the watch scanner and recipes are separable, preflight is a standalone trimmable add-on.
- **6C — Proxy/transcode profiles + action chains (F035, F036, F040):** `proxy_profiles` (seeded Low/Medium/High), the config-overlay mapper, the whitelisted action-chain executor + `action_chains` store, and the settings/automation UI that binds profiles + chains into recipes. Trimmable last: action chains (F040) can defer without affecting 6A/6B.

---

## 2. Goals / Non-Goals

### Goals
- A durable `ingest_jobs` ledger with `pending/running/done/failed/skipped/cancelled` states, fed from SP2's `IngestWorker` signals.
- A `JobQueueDashboard` dock showing jobs by status with per-item **Retry** and **Cancel**, and a **Clear finished** action.
- Retry re-submits a failed job's payload through a fresh `IngestWorker`; cancel flags the running worker.
- A stdlib `WatchFolderScanner(QThread)` polling configured folders at a configurable interval and enqueueing new files as jobs.
- Reusable `ingest_recipes` applied as a config overlay + tags + (EP4) metadata template at ingest.
- Duplicate-handling policies (`allow/skip/version/ask`) resolved from SP2's detected duplicates.
- A pure preflight validator surfaced as a checklist step in the ingest dialog.
- Named `proxy_profiles` (quality presets + transcode profiles) that overlay SP2's preview config.
- Ingest-completion notifications in a notification center.
- Whitelisted, scriptable action chains run after ingest.

### Non-Goals (deferred)
- A second execution engine / distributed queue — EP6 mirrors and controls SP2's threads only.
- `watchdog` or any OS filesystem-event dependency — polling only.
- Re-enabling arbitrary-code processors (`extensibility_hooks.exec()`, C2) — action chains are whitelisted handlers only.
- New `ffmpeg_wrapper` codec parameters (CRF/ProRes flags) — profiles use only existing knobs; richer transcode is a later EP.
- Interactive duplicate resolution UI for the `ask` policy — EP6 resolves to `ask` and defers the modal to SP6's GUI-triggered `DuplicateDialog` path; unattended ingest treats `ask` as `skip`.
- Cross-machine/shared job queue — the ledger is local to the DB (already network-share-locked by `file_lock`).

---

## 3. Detailed Design — Cluster 6A (Job queue, retry, notifications)

### 3.1 Tables

```sql
CREATE TABLE ingest_jobs (
    job_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL DEFAULT 'ingest',   -- ingest | proxy | action
    source_path    TEXT,
    target_list_id INTEGER,
    recipe_id      INTEGER,
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending|running|done|failed|skipped|cancelled
    message        TEXT,
    attempts       INTEGER NOT NULL DEFAULT 0,
    payload_json   TEXT,                              -- reconstruction payload for retry
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT NOT NULL DEFAULT 'info',          -- info|success|warning|error
    title      TEXT NOT NULL,
    body       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`ingest_jobs` is a ledger: rows are inserted `pending` before submission, flipped to `running` (attempts bumped) when the worker starts a file, and to `done`/`skipped`/`failed` from the worker's `file_done` result. It never runs anything itself.

### 3.2 DB API

```
create_job(kind, source_path, target_list_id=None, recipe_id=None, payload=None, status='pending') -> int
get_jobs(status=None, limit=200) -> list[dict]       # parsed 'payload' dict per row
get_job(job_id) -> dict
update_job_status(job_id, status, message=None)      # touches updated_at
bump_job_attempt(job_id)                             # attempts += 1, status='running'
count_jobs_by_status() -> {status: n}
clear_finished_jobs()                                # delete done|skipped|cancelled

add_notification(title, body=None, level='info') -> int
get_notifications(unread_only=False, limit=100) -> list[dict]
unread_notification_count() -> int
mark_notifications_read()
```

### 3.3 Dashboard + wiring

- `JobQueueDashboard(db, parent=None)` — a `QWidget` (hosted in a bottom `QDockWidget` like History): a status-grouped `QTableWidget` (Status / File / Attempts / Message), a **Retry** button (enabled for `failed` rows), **Cancel** (enabled for `pending`/`running`), and **Clear finished**. Signals `retry_requested(int job_id)`, `cancel_requested(int job_id)`. `refresh()` repopulates from `get_jobs()`.
- **Wiring (main.py, coordinated with SP2):** `perform_ingestion` / drop-ingest / library-ingest first `create_job(...)` a `pending` row per file (storing `payload={'source_path':…, 'target_list_id':…, 'recipe_id':…}`), then start the `IngestWorker`. `worker.progress` → `bump_job_attempt` + `update_job_status(running)`; `worker.file_done(result)` → `update_job_status(done|skipped|failed, message)`; `worker.ingest_finished(s,k,e)` → `add_notification("Ingest complete", "{s} ok / {k} skipped / {e} errors", level)` + `dashboard.refresh()`. **Retry:** look up the failed row, build a one-item `IngestWorker` from its payload, re-run. This is the SP2 seam — the signal connections are `xfail(strict)` `SP2` in tests where `IngestWorker` is absent.

---

## 4. Detailed Design — Cluster 6B (Watch folders, recipes, dup policies, preflight)

### 4.1 Tables

```sql
CREATE TABLE watch_folders (
    watch_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    path           TEXT NOT NULL,
    target_list_id INTEGER,
    recipe_id      INTEGER,
    interval_sec   INTEGER NOT NULL DEFAULT 30,
    enabled        INTEGER NOT NULL DEFAULT 1,
    last_scan      TIMESTAMP
);

CREATE TABLE ingest_recipes (
    recipe_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    values_json TEXT NOT NULL,   -- {copy_policy, generate_previews, generate_video_previews,
                                 --  dedup_enabled, dedup_threshold, duplicate_policy,
                                 --  proxy_profile_id, metadata_template_id, action_chain_id, tags}
    sort_order  INTEGER NOT NULL DEFAULT 0
);
```

### 4.2 Watch scanner (F031)

- Pure diff (`ingest_automation.scan_folder(path, seen, exts) -> (new_paths, updated_seen)`): `os.scandir` the folder (non-recursive), keep files whose extension is in `exts` and whose path is not already in `seen`; return newly-seen paths plus the updated seen-set. Qt-free → unit-testable.
- `WatchFolderScanner(folders, exts=None, parent=None)` (`QtCore.QThread`, `src/watch_scanner.py`): holds a per-folder `seen` set; `run()` loops `while not self._stopped`, calls `scan_folder` for each enabled folder, emits `files_detected(watch_id, new_paths)` and updates `last_scan`, then `msleep(interval_sec*1000)` in small cancellable slices. `scan_once()` runs one pass (used by tests, no threading). `stop()` sets the flag.
- Detected files are enqueued through 6A: for each new path, `create_job(...)` + feed a batched `IngestWorker` using the folder's recipe. The scanner is disabled by default and toggled per row.

### 4.3 Recipes (F032)

`apply_recipe_to_config(recipe_values, base_config) -> dict` (pure): returns a *new* dict = `base_config` overlaid with the recipe's keys, so a recipe can flip `copy_policy`, `generate_previews`, `duplicate_policy`, point at a `proxy_profile_id` / `metadata_template_id` / `action_chain_id`, and carry `tags`. The overlaid dict is what `IngestWorker` passes to `IngestionCore`. A recipe picker appears in the ingest dialog; a recipe manager lives in the Automation settings tab. **EP4 seam:** `metadata_template_id` application at ingest is `xfail(strict)` `EP4` until EP4's `apply_template` lands.

### 4.4 Duplicate policies (F037)

`resolve_duplicate_action(policy, duplicates) -> 'allow'|'skip'|'version'|'ask'` (pure): no duplicates → `allow`; otherwise return the configured policy (unknown → `allow`). `IngestionCore.ingest_file` calls it with SP2's `find_duplicates(...)` result and the recipe/config `duplicate_policy`: `skip` → return `duplicate_skipped` (SP2's existing path); `version` → ingest and add an EP4 `variant_of` relationship to the first duplicate (EP4-gated); `allow` → ingest normally; `ask` → in unattended/worker context, treat as `skip` and defer the modal to SP6. This wiring is the SP2 seam (`xfail(strict)` `SP2`).

### 4.5 Preflight (F038)

`run_preflight(paths, known_exts=None, min_free_bytes=0, duplicate_paths=None) -> list[dict]` (pure): per path returns `{level, code, path, message}` issues — `missing` (error), `empty` (zero-byte, error), `unknown_ext` (warning), `duplicate` (warning, when `duplicate_paths` supplied by the caller). A `PreflightDialog`/checklist widget renders the list (error rows block the **Ingest** button; warnings are acknowledgeable) as a summary step in the ingest dialog.

---

## 5. Detailed Design — Cluster 6C (Proxy/transcode profiles + action chains)

### 5.1 Tables

```sql
CREATE TABLE proxy_profiles (
    profile_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'mp4',    -- thumbnail | gif | mp4
    max_size    INTEGER NOT NULL DEFAULT 512,   -- longest edge px (quality tier, F036)
    fps         INTEGER NOT NULL DEFAULT 24,
    duration    INTEGER,                         -- seconds cap for movies; NULL = full
    is_default  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE action_chains (
    chain_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    steps_json TEXT NOT NULL,   -- [{"action": "add_tag", "params": {"tag": "review"}}, ...]
    sort_order INTEGER NOT NULL DEFAULT 0
);
```

`proxy_profiles` is seeded on migration with three quality presets (**Low** `max_size=256`, **Medium** `max_size=512` `is_default=1`, **High** `max_size=1024`) — F036 — plus the ability to add `kind='mp4'`/`gif` transcode profiles (F035).

### 5.2 Proxy config overlay (F035, F036)

`profile_to_config_overlay(profile) -> dict` (pure): maps a profile row to the SP2 preview-config keys `PreviewWorker._process` already reads — `max_size → preview_size`/`gif_size`, `fps → gif_fps`/`sequence_preview_fps`, `duration → gif_duration`, `kind → generate_video_previews` (`True` for `mp4`). Selecting a profile in a recipe overlays these onto the config the `PreviewJob` carries, so **no `PreviewWorker` or `ffmpeg_wrapper` change is needed** — the SP3-hardened wrapper renders at the profile's resolution/fps.

### 5.3 Action chains (F040)

`run_action_chain(steps, context, handlers=None) -> list[dict]` (pure dispatcher): for each `{action, params}` step, look up `action` in `handlers` (default `BUILTIN_ACTIONS`); unknown actions return `{action, ok: False, message: 'unknown action'}` and never execute; known handlers run in order over a `context` (`{'db', 'element_id', 'config'}`) and report `{action, ok, message}`. `BUILTIN_ACTIONS` = `add_tag`, `set_field` (EP4), `move_to_list`, `generate_proxy`, `notify` — each a small function calling existing DB/queue APIs. Arbitrary code is never evaluated (no C2 RCE). `IngestionCore.ingest_file` runs the recipe's `action_chain_id` after a successful insert (SP2 seam). An Automation panel edits chains; a recipe references one.

---

## 6. Architecture & File Impact

| File | Change |
|---|---|
| `src/db_manager.py` | 5 tables + migrations (`ingest_jobs`, `notifications`, `watch_folders`, `ingest_recipes`, `proxy_profiles`, `action_chains`); all job/notification/watch/recipe/profile/chain CRUD; seed proxy presets |
| `src/ingest_automation.py` (new) | Pure, Qt-free helpers: `scan_folder`, `apply_recipe_to_config`, `resolve_duplicate_action`, `run_preflight`, `profile_to_config_overlay`, `run_action_chain` + `BUILTIN_ACTIONS` |
| `src/watch_scanner.py` (new) | `WatchFolderScanner(QThread)` polling loop wrapping `scan_folder` |
| `src/ui/job_queue_dashboard.py` (new) | `JobQueueDashboard` dock widget (status table + retry/cancel/clear) |
| `src/ui/preflight_dialog.py` (new) | `PreflightDialog` checklist step |
| `src/ui/settings_panel.py` | Automation tab: watch-folder, recipe, proxy-profile, action-chain managers (admin-gated) |
| `src/ui/ingest_library_dialog.py` / ingest dialog | Recipe picker + preflight step |
| `src/ingestion_core.py` | `ingest_file` consults `resolve_duplicate_action`, applies the recipe overlay, runs the action chain (SP2/EP4 seams) |
| `main.py` | Job dashboard dock, notification center, watch scanner lifecycle, and the `IngestWorker`→ledger signal wiring |

Pure logic (`ingest_automation.py`) is separated from Qt/DB so scan/recipe/policy/preflight/profile/chain logic is unit-testable in isolation — mirroring EP4's `metadata_rules.py`.

---

## 7. Testing Strategy

- **Unit (`tests/unit/`, no Qt):**
  - `ingest_jobs` CRUD: create → `pending`; `update_job_status`/`bump_job_attempt` transitions; `get_jobs(status=…)` filtering; `count_jobs_by_status`; `clear_finished_jobs`.
  - `notifications` CRUD: add, `unread_notification_count`, `get_notifications(unread_only=True)`, `mark_notifications_read`.
  - `watch_folders` CRUD; `scan_folder` detects new files, ignores seen + wrong extension, second pass finds nothing, added file is found.
  - `ingest_recipes` CRUD (parsed `values`); `apply_recipe_to_config` overlays and preserves unrelated base keys, returns a new dict.
  - `resolve_duplicate_action`: no dupes → `allow` for every policy; dupes → the policy; unknown → `allow`.
  - `run_preflight`: missing → error, zero-byte → error, unknown ext → warning, duplicate → warning, all-good → `[]`.
  - `proxy_profiles` CRUD + seeded presets; `profile_to_config_overlay` maps every key.
  - `action_chains` CRUD; `run_action_chain` runs known handlers in order, marks unknown actions failed without executing, threads `context`.
- **GUI (`tests/gui/`, headless):** `JobQueueDashboard` lists jobs and enables Retry only for failed / Cancel only for active, emits `retry_requested`/`cancel_requested`; `PreflightDialog` blocks on errors, allows on warnings; Automation settings managers gate add/delete on admin; `WatchFolderScanner.scan_once` (constructed, not started) returns new files.
- **Integration (`xfail(strict=True)`):** `IngestWorker`→ledger wiring tagged `SP2`; recipe `metadata_template_id` application and action-chain `set_field` tagged `EP4`; proxy overlay reaching `PreviewWorker` tagged `SP2`.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Building a second queue by accident | `ingest_jobs` is a ledger with no execution; execution stays on SP2's `IngestWorker`/`PreviewWorker`. Retry re-submits to a fresh worker; cancel flags the running one. |
| SP2 worker not landed in a worktree | Ledger/notification/recipe/profile/chain CRUD + all pure helpers are Qt/worker-free and fully tested; the `IngestWorker` signal wiring is `xfail(strict)` `SP2`. |
| Polling scanner is heavy on large trees | Non-recursive `os.scandir`, extension filter, per-folder `seen` set, configurable interval (default 30 s), disabled by default. Recursive watching is opt-in future work. |
| Watch scanner re-ingests the same file / partial writes | `seen` set + `last_scan`; a size-stable check (skip a file whose size changed since the previous pass) avoids grabbing half-copied media. |
| Duplicate `version` policy needs EP4 relationships | `version` degrades to `allow` + a warning notification until EP4's `add_relationship` lands (`xfail(strict)` `EP4`). |
| Action chains reintroducing C2 RCE | Only whitelisted `BUILTIN_ACTIONS` run; no `exec`/`eval`; params are data. Unknown actions are reported, not executed. |
| Proxy profiles tempting new ffmpeg flags | Overlay maps to existing SP2 config keys / existing `ffmpeg_wrapper` params only; CRF/ProRes deferred. |
| 6 tables + multiple seams is large | Clusters ship independently: 6A (ledger + dashboard) is useful alone; 6B and 6C are separable; action chains (F040) and preflight (F038) are trimmable. |

---

## 9. Deliverables Checklist
- [ ] `ingest_jobs` + CRUD + `count_jobs_by_status` + `clear_finished_jobs`.
- [ ] `notifications` + CRUD + unread count; completion notification on `ingest_finished`.
- [ ] `JobQueueDashboard` dock (retry/cancel/clear) wired to `IngestWorker` signals (SP2 seam).
- [ ] `watch_folders` + CRUD; `scan_folder` pure diff; `WatchFolderScanner(QThread)` polling.
- [ ] `ingest_recipes` + CRUD; `apply_recipe_to_config` overlay; ingest-dialog recipe picker.
- [ ] `resolve_duplicate_action` policy resolver wired into `ingest_file` (SP2 seam).
- [ ] `run_preflight` + `PreflightDialog` checklist step.
- [ ] `proxy_profiles` + seeded presets; `profile_to_config_overlay` mapping.
- [ ] `action_chains` + CRUD; `run_action_chain` + `BUILTIN_ACTIONS` (whitelisted).
- [ ] Automation settings tab (watch/recipe/profile/chain managers, admin-gated).
- [ ] Unit + headless GUI tests green; SP2/EP4 integration seams `xfail(strict)`.

---

## 10. Follow-on
EP4 upgrades the `version` duplicate policy (relationships) and recipe metadata templates from `xfail` to real. SP6's interactive `DuplicateDialog` fulfils the `ask` policy in the GUI path. A later EP can add recursive/event-based watching (opt-in `watchdog`), richer transcode codecs (CRF/ProRes via new `ffmpeg_wrapper` params), and cross-machine job federation. EP9 analytics can chart `ingest_jobs` throughput/failure rates (report F061).
