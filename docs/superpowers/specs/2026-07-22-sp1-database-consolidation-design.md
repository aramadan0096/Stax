# SP1 — Database Consolidation & Concurrency — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). This is the second sub-project. It depends on **SP0** (test harness, `stax_db`/`stax_config`/`mock_nuke` fixtures, 3-tier layout, gating CI) and is the sub-project that makes SP0's C1 strict-`xfail` smoke tests turn green.

---

## 1. Background & Motivation

The StaX audit (`STAX_AUDIT_REPORT.md`) ranks **C1 — two incompatible database layers** as the single highest-severity defect. Two class shapes ship side by side:

- The **live** `DatabaseManager` (`src/db_manager.py`) uses **lowercase** tables (`stacks`, `lists`, `elements`, `favorites`, `playlists`, `playlist_items`, `ingestion_history`, `users`, `user_sessions`, `settings`) and a per-call `with self.get_connection() as conn:` context manager. It has **no** `phash` column, **no** insertion log, and **no** versioned migration runner.
- An **orphaned** layer (`src/db_manager_additions.py`, `src/db_migrations.py`) assumes a *different* class shape — a persistent `self.conn`, a `self._lock`, and **capitalized** tables (`Elements`, `InsertionLog`, `Users`, `Lists`, `Stacks`). `db_manager_additions.py` is literally paste-by-hand instructions that were never applied; `db_migrations.run_migrations` is documented as "wired into `__init__`" but is **never called**.

Yet **live code calls the orphaned methods**, so those paths raise `AttributeError` today:

| Caller | Missing method (file:line) |
|---|---|
| `src/api_server.py:124` | `db.count_elements_by_list` |
| `src/api_server.py:148` | `db.update_element_metadata` |
| `src/api_server.py:192` | `db.get_top_inserted_elements` |
| `src/ui/batch_edit_dialog.py:362` | `db.update_element_metadata` |
| `src/ui/analytics_panel.py:279/300/310/323` | `db.get_top_inserted_elements` / `get_insertions_by_month` / `get_insertions_by_user` / `get_total_insertions` |
| `src/ui/analytics_panel.py:64` | `db.execute` (used by `log_insertion`) |

Because `InsertionLog` is never created and `log_insertion` targets a table that does not exist, analytics charts are **permanently empty** and the failure is swallowed by the panel's `try/except`.

Layered onto C1 are four concurrency/safety defects in the same subsystem that SP1 owns:

- **H1** — `FileLockManager.release()` `os.remove()`s the lock file (delete-on-release inode race), and `get_connection` sets `PRAGMA journal_mode = WAL`, which SQLite does not support on the network-share deployment target.
- **H3** — `add_favorite` / `remove_favorite` / `get_favorites` are each **defined twice** with swapped argument order; Python keeps the last definition, so positional callers can store/query under mismatched identities.
- **M1** — `search_elements` and `update_element` `.format()` caller-supplied column names into SQL with no whitelist (injection primitive).
- **L6** — every read serializes behind one global OS file lock, defeating concurrent readers.
- **L11** — Migration 6 (`playlist_items` rebuild) swallows copy failures then renames/drops the original → silent data loss.

### Program context (decisions already locked)
- **Wire, don't remove:** consolidate the two DB layers by **merging** the needed methods into the live `DatabaseManager` on the **lowercase** schema — not by deleting callers. The orphaned `db_manager_additions.py` becomes redundant once its methods live (correctly) on the real class.
- **Windows + Linux** only.
- **Hybrid 3-tier testing** on the SP0 harness; the `stax_db` fixture builds the real `DatabaseManager`.
- **Flat imports** (`from db_migrations import run_migrations`); **`logging`** not `print` in new code.

---

## 2. Goals / Non-Goals

### Goals
- **Merge** the orphaned methods into the live `DatabaseManager`, rewritten against the **lowercase** schema and the `with self.get_connection() as conn:` idiom: `execute`, `count_elements_by_list`, `update_element_metadata`, `get_top_inserted_elements`, `get_insertions_by_month`, `get_insertions_by_user`, `get_total_insertions`, `update_element_phash`, `get_elements_with_phash`.
- Add a **real versioned migration runner** by reconciling `src/db_migrations.py` to the lowercase schema (a `schema_version` table, the `elements.phash` column, and a lowercase `insertion_log` table) and **actually calling it** from `DatabaseManager.__init__`.
- Provide an **insertion-log write path that is actually written**: wire `analytics_panel.log_insertion` to the new lowercase `insertion_log` table via `db.execute`, so the existing `main.py` insert path records rows.
- Wire **analytics / API / batch-edit** to the now-real methods (no code change needed at most call sites once the methods exist; `analytics_panel.log_insertion`'s SQL is the one edit).
- **H1:** stop deleting the lock file on release (create once, keep it; only unlock the byte range + close the handle); switch `journal_mode` to `DELETE` for network-share safety.
- **H3:** delete the dead first copies of the favorite methods, keep the single canonical `(element_id, user_name=None, machine_name=None)` signature that call sites already use.
- **M1:** whitelist column names in `search_elements` and `update_element` (and therefore `update_element_metadata`).
- **L6:** scope the external file lock to writes; allow concurrent read connections via a `write` flag on `get_connection`.
- **L11:** verify copied row counts in Migration 6 and raise on mismatch so the transaction rolls back.
- **Flip SP0's C1 strict-`xfail` smoke tests** (`tests/gui/test_api_smoke.py`, `tests/gui/test_batch_edit_smoke.py`) to real PASS.

### Non-Goals (explicitly deferred)
- **H2** (salted KDF passwords / default `admin/admin`) — SP4 (security). SP1 leaves the hashing untouched.
- **C4** (async preview worker / lazy gallery / off-thread ingest) — SP2.
- **M2** (constant-time API token, ingest-path allowlist) — SP4.
- Wiring the **duplicate detector** into ingest (needs the async pipeline) — SP2. SP1 only *creates the `phash` column + accessors* it depends on.
- Wiring the **BatchEditDialog** into the context menu (L2) and **AnalyticsPanel** into a dock — SP6 (UI). SP1 only makes their DB calls resolve.
- Deleting the now-redundant `db_manager_additions.py` / `nuke_bridge_patch.py` — SP8 (code-quality cleanup). SP1 leaves them in place but no longer relied upon (nothing imports `db_manager_additions`).

---

## 3. Approach

Chosen approach: **Merge onto the live lowercase schema + a genuine versioned migration runner.**

The audit offers two options for C1 ("merge the needed methods into `DatabaseManager`" **or** "delete the additions/migrations files and the callers' dependence on them"). The locked "wire, don't remove" decision selects **merge**: the analytics, API, and batch-edit features are real product value that is one consolidation away from working. Deleting the callers would throw away shipped features.

Reconciliation strategy for the two migration systems:
- The existing `_create_schema` (fresh DB) and `_apply_migrations` (ad-hoc, idempotent column/table checks for existing DBs) **stay** — they already build the correct lowercase baseline and are relied on by existing databases in the field.
- `src/db_migrations.py` is **rewritten** from the capitalized/`self.conn` shape to a small, lowercase, version-tracked runner (`schema_version` table + ordered `_migrate_vN(conn)` functions) that adds only the **new** artifacts C1 needs: `elements.phash` and the `insertion_log` table. It is idempotent.
- `DatabaseManager.__init__` calls `run_migrations` **once on every start** (after the create/migrate branch), so both fresh and existing databases converge to the same target version. This is the "actually call `run_migrations`" the audit demands, without duplicating the baseline logic.

Rejected alternatives:
- *Delete the orphaned callers* — discards working-once-wired features; violates the program decision.
- *Fold everything into `_apply_migrations`* — keeps migrations un-versioned (no `schema_version` ledger), which the audit explicitly flags as missing ("a real versioned migration runner").
- *Adopt the capitalized schema instead* — would require rewriting the entire live `DatabaseManager` and every working lowercase query; enormous blast radius for zero user benefit.

---

## 4. Detailed Design

### 4.1 Versioned migration runner (`src/db_migrations.py`, rewritten)

Replace the capitalized/`self.conn` module with a lowercase, connection-based runner:

- A `schema_version` table: `CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL DEFAULT 0)`.
- `CURRENT_SCHEMA_VERSION = 2`.
- `_migrate_v1(conn)` — add `elements.phash TEXT` (guarded by a `PRAGMA table_info(elements)` check; idempotent).
- `_migrate_v2(conn)` — create the lowercase `insertion_log` table plus indexes:

```sql
CREATE TABLE IF NOT EXISTS insertion_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    element_fk  INTEGER NOT NULL,
    user_fk     INTEGER,
    inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
    project     TEXT,
    host        TEXT,
    context     TEXT,
    FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_inslog_element ON insertion_log(element_fk);
CREATE INDEX IF NOT EXISTS idx_inslog_date    ON insertion_log(inserted_at);
```

- `run_migrations(conn)` bootstraps `schema_version`, reads the current version, and applies pending `_migrate_vN` in order, bumping the ledger after each. Safe to call repeatedly.

`DatabaseManager.__init__` (after the existing `if not exists: _create_schema() else: _apply_migrations()` branch) gains:

```python
# Versioned migrations (phash column, insertion_log table) — idempotent, every start.
self._run_versioned_migrations()
```

with

```python
def _run_versioned_migrations(self):
    from db_migrations import run_migrations
    with self.get_connection() as conn:
        run_migrations(conn)
```

The `insertion_log` FK targets `elements(element_id)` — the real lowercase PK.

### 4.2 Merged methods on `DatabaseManager` (lowercase schema)

All new methods use `with self.get_connection([write=...]) as conn:` — never `self.conn` / `self._lock`.

- `execute(self, sql, params=())` — write helper (INSERT/UPDATE/DELETE). Opens a **write** connection, executes, returns the cursor; the context manager commits. Used by `analytics_panel.log_insertion`.
- `count_elements_by_list(self, list_id)` — `SELECT COUNT(*) FROM elements WHERE list_fk = ? AND is_deprecated = 0` (read).
- `update_element_metadata(self, element_id, **kwargs)` — whitelists to `{name, tags, comment, type, is_deprecated, list_fk}`, then delegates to the (now-whitelisted) `update_element`.
- `update_element_phash(self, element_id, phash)` — `UPDATE elements SET phash = ? WHERE element_id = ?` (write).
- `get_elements_with_phash(self)` — `SELECT element_id, name, list_fk, format, phash, preview_path FROM elements WHERE phash IS NOT NULL AND phash != ''` (read).
- `get_top_inserted_elements(self, n=20)` — `insertion_log` ⋈ `elements` ⋈ `lists`, grouped by `element_fk`, keys `element_id, name, list_name, format, type, count` (read).
- `get_insertions_by_month(self)` — `strftime('%Y-%m', inserted_at)` over `insertion_log`, keys `month, count` (read).
- `get_insertions_by_user(self)` — `insertion_log` ⋈ `users`, `COALESCE(u.username,'Guest')`, keys `username, count, last_active` (read).
- `get_total_insertions(self)` — `SELECT COUNT(*) FROM insertion_log` (read).

`get_elements_by_list(list_id, include_deprecated=False, limit=None, offset=0)` already exists and satisfies the API's `get_elements_by_list(list_id, limit=..., offset=...)` call — **no change needed** (the orphaned override in `db_manager_additions.py` is discarded).

### 4.3 Insertion-log write path

`src/ui/analytics_panel.py::log_insertion` currently does `db.execute("INSERT INTO InsertionLog ...")`. Two edits make it real:
1. `DatabaseManager.execute` now exists (§4.2).
2. The SQL is lowercased to `INSERT INTO insertion_log (element_fk, user_fk, project, host) VALUES (?, ?, ?, ?)`.

The existing insert path in `main.py:641` (`log_insertion(db=self.db, element_id=..., user_id=..., project=..., host=...)`) then records a row on every asset insertion — closing the loop that leaves analytics empty today. No change to `main.py`.

### 4.4 H1 — Lock-file race + WAL on a share

- **`src/file_lock.py::release`**: remove the `os.remove(self.lock_file_path)` block. Release now only unlocks the byte range (`_unlock_windows`/`_unlock_posix`), closes the handle, and clears `is_locked`. The lock file persists on disk, eliminating the delete-on-release inode race (two processes can no longer disagree about which inode is "the" lock).
- **`src/db_manager.py::get_connection`** line 127: change `PRAGMA journal_mode = WAL` → `PRAGMA journal_mode = DELETE`. `DELETE` is safe on SMB/NFS shares (no `-wal`/`-shm` sidecar files), permits multiple readers + a single writer, and matches the stated deployment target.

### 4.5 H3 — Duplicate favorite methods

`add_favorite`, `remove_favorite`, and `get_favorites` are each defined twice. The **surviving** (last) definitions already use the `(element_id, user_name=None, machine_name=None)` signature — which is exactly what the call sites pass (`media_display_widget.py`: `is_favorite/remove_favorite/add_favorite(element_id, user, machine)`, `get_favorites(user, machine)`). Fix:
- **Delete the dead first copies** (`db_manager.py:898-928`: the `(element_id, machine_name, user_name=None)` variants).
- Keep the second copies (`:1004`, `:1034`, `:1075`) and the single `is_favorite` (`:1055`) as the canonical API.
- No call-site edits are needed — they already match the canonical order — but SP1 adds a favorites round-trip test to lock it.

### 4.6 M1 — SQL column-name whitelist

Add class-level constants on `DatabaseManager`:

```python
SEARCHABLE_ELEMENT_COLUMNS = {"name", "format", "type", "comment", "tags"}
UPDATABLE_ELEMENT_COLUMNS = {
    "list_fk", "name", "type", "filepath_soft", "filepath_hard", "is_hard_copy",
    "frame_range", "format", "comment", "tags", "preview_path", "gif_preview_path",
    "video_preview_path", "geometry_preview_path", "is_deprecated", "file_size", "phash",
}
```

- `search_elements`: if `property_name not in SEARCHABLE_ELEMENT_COLUMNS`, coerce to `"name"` and `log.warning` (matches the intended behavior from the orphaned file and the Advanced-Search combo, which only ever emits whitelisted values). This removes the injection primitive without 500-ing on hostile API input.
- `update_element`: filter `kwargs` to `UPDATABLE_ELEMENT_COLUMNS` before building the `SET` clause (same house style as the existing `update_user`); return `False` if nothing valid remains.
- `update_element_metadata` (§4.2) filters to its own narrower allow-set, then routes through the now-safe `update_element`.

### 4.7 L6 — Reads don't take the external lock

`get_connection` gains a keyword-only `write=True` parameter. The external `FileLockManager` is acquired **only** when `self.use_file_lock and write`. Read-only accessors pass `write=False`, so concurrent readers (API + GUI + preview worker) no longer serialize behind the single OS lock. With `journal_mode=DELETE` SQLite already provides multi-reader / single-writer safety; the external lock now guards only the writer.

Read-only methods flipped to `get_connection(write=False)`: `get_all_stacks`, `get_stack_by_id`, `get_lists_by_stack`, `get_sub_lists`, `get_list_by_id`, `get_list_hierarchy`, `get_elements_by_list`, `get_elements_count`, `get_element_by_id`, `search_elements`, `count_elements_by_list`, `is_favorite`, `get_favorites`, `get_ingestion_history`, `get_all_playlists`, `get_playlist_by_id`, `get_playlist_elements`, `is_element_in_playlist`, `get_all_tags`, `search_elements_by_tags`, `get_user_by_id`, `get_user_by_username`, `get_all_users`, `get_active_session`, `get_setting`, `get_all_settings`, `get_top_inserted_elements`, `get_insertions_by_month`, `get_insertions_by_user`, `get_total_insertions`, `get_elements_with_phash`. All writers keep the default `write=True`.

### 4.8 L11 — Migration 6 row-count guard

In `db_manager.py::_apply_migrations` Migration 6 (`playlist_items` rebuild):
1. Count the source rows before copying: `src = SELECT COUNT(*) FROM playlist_items`.
2. Change the copy to `INSERT OR IGNORE` so a constraint clash drops rows rather than aborting mid-statement.
3. After copying, count `playlist_items_new`; if `new != src`, `raise RuntimeError(...)` **before** the table swap. The exception propagates out of the `get_connection` context, which rolls back (no `commit`), leaving the original `playlist_items` intact — no silent data loss.

### 4.9 Wiring / callers touched

| Issue | File edited | Nature of edit |
|---|---|---|
| C1 | `src/db_manager.py` | add merged methods, `_run_versioned_migrations`, whitelists, `write` param |
| C1 | `src/db_migrations.py` | rewrite lowercase + versioned |
| C1 | `src/ui/analytics_panel.py` | lowercase `insertion_log` SQL in `log_insertion` |
| H1 | `src/file_lock.py` | `release()` no longer deletes the file |
| H1 | `src/db_manager.py` | `journal_mode = DELETE` |
| H3 | `src/db_manager.py` | delete dead first favorite copies |
| M1 | `src/db_manager.py` | whitelist `search_elements` / `update_element` |
| L6 | `src/db_manager.py` | `write` flag + read methods |
| L11 | `src/db_manager.py` | Migration 6 guard |

`src/api_server.py` and `src/ui/batch_edit_dialog.py` need **no** edits — their calls resolve once the methods exist.

---

## 5. Testing Strategy

All tests run on the SP0 harness (`pytest -m "not manual"`, headless, `stax_db` fixture). New SP1 tests are TDD-first (red → green) per task.

**Unit tier (`tests/unit/`):**
- `test_db_migrations.py` — fresh `stax_db` has `schema_version`, `elements.phash`, and `insertion_log`; `run_migrations` is idempotent (second call is a no-op and does not bump past `CURRENT_SCHEMA_VERSION`).
- `test_db_insertion_log.py` — `log_insertion` writes a row; `get_top_inserted_elements` / `get_insertions_by_month` / `get_insertions_by_user` / `get_total_insertions` return it with the documented keys.
- `test_db_element_methods.py` — `count_elements_by_list`, `update_element_metadata` (whitelist honored, disallowed keys ignored), `update_element_phash` / `get_elements_with_phash`.
- `test_db_sql_injection.py` — a hostile `property_name` / hostile `update_element` key does not drop or mutate unintended data (M1).
- `test_db_favorites.py` — add/query/remove round-trips with `(element_id, user, machine)` (H3).
- `test_file_lock.py` (extends SP0's) — after `release()`, the lock file **still exists**, `is_locked` is `False`, and re-`acquire()` succeeds (H1).
- `test_db_journal_mode.py` — a live connection reports `PRAGMA journal_mode == 'delete'` (H1).
- `test_db_read_no_lock.py` — `get_connection(write=False)` does not instantiate/acquire a `FileLockManager` while `write=True` does (L6), verified with `mocker.spy`.
- `test_db_migration6_guard.py` — a legacy `playlist_items` (no `item_id`) with distinct rows migrates with the count preserved; a legacy table whose rows collapse under the new `UNIQUE` constraint raises `RuntimeError` and leaves the original intact (L11).

**GUI tier (`tests/gui/`):** SP0's C1 smoke tests flip from `xfail(strict=True)` to PASS:
- `test_api_smoke.py::test_analytics_top_endpoint_no_server_error` — remove the `xfail`; `/api/v1/analytics/top` now returns non-500.
- `test_batch_edit_smoke.py::test_batch_edit_apply_resolves_db_method` — remove the `xfail`; `hasattr(stax_db, "update_element_metadata")` is now `True`.

**Regression gate:** the full SP0 suite (`pytest -m "not manual"`) must end **0 failed, 0 errored, 0 unexpected xpass** on Windows + Linux CI.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `strict=True` xfail turns into an **xpass FAIL** the moment the method exists, before the marker is removed. | The task that adds the method and the task that removes the marker are sequenced; the marker removal runs and the suite is re-run in the same task before commit. |
| `journal_mode = DELETE` slows highly-concurrent local writes vs WAL. | Accepted: correctness on the network-share target outweighs local throughput; the external write lock already serializes writers. |
| Keeping the lock file on disk leaves a stale `.lock` after a crash. | A persisted, unlocked file is harmless — the next `acquire` re-locks the byte range; no process treats file *existence* as "held". |
| `run_migrations` opening its own `get_connection` during `__init__` re-enters locking. | Calls are sequential (create/migrate finishes and releases before `_run_versioned_migrations`); `get_connection` acquires/releases per call. |
| Flipping read methods to `write=False` accidentally includes a method that writes. | The flipped list in §4.7 is SELECT-only; each is verified by name; writers are untouched and default to `write=True`. |
| FK enforcement breaks the Migration 6 `INSERT OR IGNORE` copy when parents are absent. | The guard test seeds real `elements`/`playlists` parents; production legacy DBs already satisfy the FKs they came from. |

---

## 7. Deliverables Checklist
- [ ] `src/db_migrations.py` rewritten: lowercase `schema_version`, `_migrate_v1` (`elements.phash`), `_migrate_v2` (`insertion_log`), idempotent `run_migrations`.
- [ ] `DatabaseManager.__init__` calls `_run_versioned_migrations()`.
- [ ] Merged methods added to `DatabaseManager` (`execute`, `count_elements_by_list`, `update_element_metadata`, analytics reads, phash accessors).
- [ ] `analytics_panel.log_insertion` writes to lowercase `insertion_log`.
- [ ] H1: `FileLockManager.release()` keeps the file; `journal_mode = DELETE`.
- [ ] H3: dead first favorite copies deleted; canonical signature verified against call sites.
- [ ] M1: `search_elements` / `update_element` column whitelists.
- [ ] L6: `get_connection(write=...)`; read methods flipped.
- [ ] L11: Migration 6 row-count guard raises on mismatch.
- [ ] SP0 C1 `xfail` smoke tests (`test_api_smoke.py`, `test_batch_edit_smoke.py`) flipped to PASS.
- [ ] New SP1 unit tests green; full suite `0 failed, 0 errored` on Win + Linux CI.

---

## 8. Follow-on
- **SP2** (async pipeline) consumes the `phash` column + `get_elements_with_phash` to finally wire duplicate detection, and uses `insertion_log`-backed analytics off-thread.
- **SP4** (security) re-hardens the auth this SP intentionally left alone (H2, M2).
- **SP6** (UI) wires `BatchEditDialog` into the context menu and `AnalyticsPanel` into a dock — both now backed by working DB methods.
- **SP8** (code quality) deletes the now-unreferenced `db_manager_additions.py` and `nuke_bridge_patch.py`.
