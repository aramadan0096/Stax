# SP1 — Database Consolidation & Concurrency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow superpowers:test-driven-development: write the failing test first, watch it fail, then implement.

**Goal:** Resolve audit issues **C1, H1, H3, M1, L6, L11** by consolidating StaX's two incompatible database layers into the single live `DatabaseManager` (lowercase schema), adding a real versioned migration runner, an actually-written insertion-log path, SQL column whitelists, a network-safe lock/journal mode, and read/write lock scoping — flipping SP0's C1 strict-`xfail` smoke tests to PASS.

**Architecture:** Merge the orphaned `db_manager_additions.py` methods into `src/db_manager.py` rewritten against the lowercase schema (`stacks`/`lists`/`elements`/`favorites`/`playlists`/`playlist_items`/`ingestion_history`/`users`/`insertion_log`) and the `with self.get_connection() as conn:` idiom. Rewrite `src/db_migrations.py` into a lowercase, `schema_version`-tracked runner (adds `elements.phash` + `insertion_log`) and call it from `__init__`. Fix the lock-file delete race and WAL-on-share in `src/file_lock.py` / `src/db_manager.py`. Wire `analytics_panel.log_insertion` to the lowercase table.

**Tech Stack:** Python 3.9, SQLite (`sqlite3`), pytest, pytest-mock, pytest-qt, Flask (API smoke), PySide2 (offscreen), uv, GitHub Actions.

## Global Constraints

- **Depends on SP0.** The `stax_db`, `stax_config`, `mock_nuke`, and media fixtures (`tests/conftest.py`), the 3-tier `tests/unit|gui|nuke` layout, `pytest.ini` markers, and the gating CI must already exist. If a task references a fixture or an SP0 test file that is absent, **stop** — SP0 is not merged yet.
- **Platforms:** Windows + Linux only. `journal_mode = DELETE` (network-share safe), never `WAL`.
- **Lowercase schema only.** Every merged query targets `elements`/`lists`/`stacks`/`insertion_log`/… — NEVER the capitalized `Elements`/`InsertionLog` of the orphaned layer. Never use `self.conn` / `self._lock`; always `with self.get_connection([write=...]) as conn:`.
- **Import convention:** flat (`from db_migrations import run_migrations`), because `src/` is on `sys.path`.
- **Logging, not print,** in new code (`log = logging.getLogger(__name__)`).
- **Out of scope (do not touch):** password hashing / default admin (H2 → SP4), async worker / lazy gallery / off-thread ingest (C4 → SP2), API token timing / ingest allowlist (M2 → SP4), deleting `db_manager_additions.py` / `nuke_bridge_patch.py` (→ SP8), wiring BatchEdit/Analytics into the UI (→ SP6).
- **Conventional commits**; commit after each green task. Do not commit red.

---

## Key signatures (verified against the codebase)

- `DatabaseManager(db_path, enable_logging=False, use_file_lock=True)` — `_create_schema()` on a missing file, else `_apply_migrations()` (`src/db_manager.py:22,70-74`). Connections via `@contextmanager get_connection(self)` (`:81`), row factory `sqlite3.Row`.
- Live lowercase columns of `elements`: `element_id, list_fk, name, type, filepath_soft, filepath_hard, is_hard_copy, frame_range, format, comment, tags, preview_path, gif_preview_path, video_preview_path, geometry_preview_path, is_deprecated, file_size, created_at` (`src/db_manager.py:215-237`). No `phash`.
- `search_elements(self, search_text, property_name='name', match_type='loose')` (`src/db_manager.py:870`) — currently `.format(property_name)`, no whitelist.
- `update_element(self, element_id, **kwargs)` (`src/db_manager.py:837`) — `.format`s kwargs keys, no whitelist.
- `get_elements_by_list(self, list_id, include_deprecated=False, limit=None, offset=0)` (`src/db_manager.py:777`) — already satisfies the API's `limit=/offset=` call; **keep as-is**.
- Favorites: canonical (surviving) copies `add_favorite(self, element_id, user_name=None, machine_name=None)` (`:1004`), `remove_favorite(... user_name=None, machine_name=None)` (`:1034`), `is_favorite(... user_name=None, machine_name=None)` (`:1055`), `get_favorites(self, user_name=None, machine_name=None)` (`:1075`). Dead first copies to delete: `:898-928`.
- Call sites (already match canonical order): `src/ui/media_display_widget.py:1237-1242` `is_favorite/remove_favorite/add_favorite(element_id, user, machine)`; `:1506` `get_favorites(user, machine)`.
- `FileLockManager(lock_file_path, timeout=30.0, retry_delay=0.1, max_retries=100)`; `.acquire()` / `.release()` / `.is_locked` (`src/file_lock.py:34`). `release()` currently `os.remove`s the file (`:151-155`).
- `get_connection` sets `PRAGMA journal_mode = WAL` at `src/db_manager.py:127`.
- API callers: `db.count_elements_by_list` (`src/api_server.py:124`), `db.update_element_metadata` (`:148`), `db.get_top_inserted_elements` (`:192`), `_build_flask_app(db, config)` (`:76`).
- Batch-edit caller: `db.update_element_metadata(element_id, **kwargs)` (`src/ui/batch_edit_dialog.py:362`); ctor `BatchEditDialog(element_ids, db, parent=None)` (`:96`).
- Analytics callers: `db.get_top_inserted_elements(n)` (`:279`), `db.get_insertions_by_month()` (`:300`), `db.get_insertions_by_user()` (`:310`), `db.get_total_insertions()` (`:323`); `log_insertion(db, element_id, user_id=None, project="", host="")` does `db.execute("INSERT INTO InsertionLog ...")` (`src/ui/analytics_panel.py:51,64`).
- Insert path that will now record rows: `main.py:641` `log_insertion(db=self.db, element_id=..., user_id=uid, project=..., host=...)` — **no edit needed**.

---

## Task 1: Rewrite `db_migrations.py` into a lowercase versioned runner + wire it into `__init__`

**Files:**
- Replace: `src/db_migrations.py`
- Modify: `src/db_manager.py` (`__init__` + new `_run_versioned_migrations`)
- Test: `tests/unit/test_db_migrations.py` (new)

**Interfaces:**
- Produces: `elements.phash` column, `insertion_log` table, `schema_version` ledger on every `DatabaseManager` (consumed by Tasks 2–3 and SP2).

- [ ] **Step 1: Write the failing migration test**

Create `tests/unit/test_db_migrations.py`:

```python
import pytest


@pytest.mark.unit
def test_versioned_artifacts_exist_on_fresh_db(stax_db):
    with stax_db.get_connection(write=False) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        elem_cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)")}
    assert "schema_version" in tables
    assert "insertion_log" in tables
    assert "phash" in elem_cols
    # lowercase only — the orphaned capitalized artifacts must NOT appear
    assert "InsertionLog" not in tables


@pytest.mark.unit
def test_run_migrations_is_idempotent(stax_db):
    from db_migrations import run_migrations, CURRENT_SCHEMA_VERSION
    with stax_db.get_connection() as conn:
        run_migrations(conn)  # second run
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == CURRENT_SCHEMA_VERSION
```

- [ ] **Step 2: Run it — confirm it fails**

Run: `pytest tests/unit/test_db_migrations.py -v`
Expected: FAIL/ERROR — `get_connection()` has no `write` kwarg yet (TypeError) and/or `schema_version`/`insertion_log`/`phash` absent. (The `write` kwarg lands in Task 6; until then this test drives the migration artifacts. If it errors purely on `write=`, temporarily read via `stax_db.get_connection()` — but implement `write` in Task 6 and restore. Simplest: proceed to Step 3, then re-run after Task 6. Record the expected failure now.)

> Note: to keep this task self-contained, the test above uses `write=False`, added in Task 6. Run Task 1's assertions with a plain `get_connection()` if executing tasks strictly in order:
> replace `get_connection(write=False)` with `get_connection()` in Step 1, and re-add `write=False` in Task 6 Step 5.

- [ ] **Step 3: Replace `src/db_migrations.py`**

Replace the entire file with:

```python
# -*- coding: utf-8 -*-
"""
StaX — Database migration system (lowercase live schema)
========================================================
A small, version-tracked migration runner that upgrades an existing StaX
database in place. It targets the LIVE lowercase schema created by
DatabaseManager._create_schema (elements/lists/stacks/...), NOT the orphaned
capitalized layer.

Wired into DatabaseManager.__init__ via DatabaseManager._run_versioned_migrations().
Each _migrate_vN(conn) applies exactly one change and is idempotent.
"""

import logging

log = logging.getLogger(__name__)

# Bump this every time a new _migrate_vN is appended below.
CURRENT_SCHEMA_VERSION = 2


def _bootstrap_schema_version(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER NOT NULL DEFAULT 0)"
    )
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    conn.commit()


def _get_version(conn):
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0


def _set_version(conn, v):
    conn.execute("UPDATE schema_version SET version = ?", (v,))
    conn.commit()


# ---------------------------------------------------------------------------
# Individual migrations (lowercase schema)
# ---------------------------------------------------------------------------

def _migrate_v1(conn):
    """v0 -> v1: add elements.phash for perceptual-hash duplicate detection."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)")}
    if "phash" not in cols:
        conn.execute("ALTER TABLE elements ADD COLUMN phash TEXT")
        log.info("Migration v1: added elements.phash")
    conn.commit()


def _migrate_v2(conn):
    """v1 -> v2: create insertion_log for usage analytics."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS insertion_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            element_fk  INTEGER NOT NULL,
            user_fk     INTEGER,
            inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
            project     TEXT,
            host        TEXT,
            context     TEXT,
            FOREIGN KEY (element_fk) REFERENCES elements(element_id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inslog_element ON insertion_log(element_fk)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inslog_date ON insertion_log(inserted_at)"
    )
    log.info("Migration v2: created insertion_log table")
    conn.commit()


# Index N upgrades schema version N-1 -> N.
_MIGRATIONS = [
    None,          # index 0 — unused placeholder
    _migrate_v1,   # 0 -> 1
    _migrate_v2,   # 1 -> 2
]


def run_migrations(conn):
    """
    Apply all pending migrations against *conn* (sqlite3.Connection).
    Safe to call repeatedly; already-applied migrations are skipped.
    """
    _bootstrap_schema_version(conn)
    current = _get_version(conn)
    log.debug("DB schema version: %d, target: %d", current, CURRENT_SCHEMA_VERSION)

    if current >= CURRENT_SCHEMA_VERSION:
        return

    for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        if version < len(_MIGRATIONS) and _MIGRATIONS[version] is not None:
            log.info("Applying migration v%d ...", version)
            try:
                _MIGRATIONS[version](conn)
                _set_version(conn, version)
                log.info("Migration v%d applied.", version)
            except Exception as exc:
                log.error("Migration v%d FAILED: %s", version, exc)
                raise
```

- [ ] **Step 4: Wire `run_migrations` into `DatabaseManager.__init__`**

In `src/db_manager.py`, find the end of `__init__` (`:70-74`):

```python
        # Initialize schema if database doesn't exist
        if not os.path.exists(self.db_path):
            self._create_schema()
        else:
            # Apply migrations for existing databases
            self._apply_migrations()
```

Replace with:

```python
        # Initialize schema if database doesn't exist
        if not os.path.exists(self.db_path):
            self._create_schema()
        else:
            # Apply migrations for existing databases
            self._apply_migrations()

        # Versioned migrations (phash column, insertion_log table).
        # Idempotent; runs on every start so fresh and existing DBs converge.
        self._run_versioned_migrations()
```

- [ ] **Step 5: Add the `_run_versioned_migrations` method**

In `src/db_manager.py`, immediately after the `_apply_migrations` method (ends `:553`, `self._log("All migrations applied successfully")`), add:

```python
    def _run_versioned_migrations(self):
        """Run the versioned migration runner (elements.phash, insertion_log)."""
        from db_migrations import run_migrations
        with self.get_connection() as conn:
            run_migrations(conn)
```

- [ ] **Step 6: Run the test — confirm green**

Run: `pytest tests/unit/test_db_migrations.py -v`
Expected: 2 passed. (If executing tasks strictly in order and `write=False` errors, use the plain `get_connection()` form noted in Step 2; restore in Task 6.)

- [ ] **Step 7: Commit**

```bash
git add src/db_migrations.py src/db_manager.py tests/unit/test_db_migrations.py
git commit -m "fix(db): add lowercase versioned migration runner (schema_version, elements.phash, insertion_log) [C1]"
```

---

## Task 2: Insertion-log write path + analytics read methods

**Files:**
- Modify: `src/db_manager.py` (add `execute`, analytics reads)
- Modify: `src/ui/analytics_panel.py` (lowercase `log_insertion` SQL)
- Test: `tests/unit/test_db_insertion_log.py` (new)

**Interfaces:**
- Consumes: `insertion_log` (Task 1). Produces: the methods `analytics_panel` and `api_server` call.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_db_insertion_log.py`:

```python
import pytest

from analytics_panel import log_insertion


def _seed_element(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    return stax_db.create_element(lid, "elemA", "2D", format="exr")


@pytest.mark.unit
def test_log_insertion_writes_and_reads_back(stax_db):
    eid = _seed_element(stax_db)
    log_insertion(stax_db, eid, user_id=None, project="proj", host="ws01")
    log_insertion(stax_db, eid, user_id=None, project="proj", host="ws01")

    assert stax_db.get_total_insertions() == 2

    top = stax_db.get_top_inserted_elements(5)
    assert len(top) == 1
    assert top[0]["element_id"] == eid
    assert top[0]["name"] == "elemA"
    assert top[0]["count"] == 2

    by_month = stax_db.get_insertions_by_month()
    assert sum(r["count"] for r in by_month) == 2

    by_user = stax_db.get_insertions_by_user()
    assert by_user[0]["username"] == "Guest"
    assert by_user[0]["count"] == 2


@pytest.mark.unit
def test_analytics_empty_db_returns_empty(stax_db):
    assert stax_db.get_total_insertions() == 0
    assert stax_db.get_top_inserted_elements(5) == []
    assert stax_db.get_insertions_by_month() == []
    assert stax_db.get_insertions_by_user() == []
```

> `from analytics_panel import log_insertion` resolves flat because `src/ui` is not on `sys.path` — SP0's conftest adds repo root + `src`. If `analytics_panel` is not importable flat, import via `from ui.analytics_panel import log_insertion`. Verify with `python -c "import sys; sys.path.insert(0,'src'); from ui.analytics_panel import log_insertion; print('ok')"` and use whichever resolves; `ui.analytics_panel` is the reliable form.

- [ ] **Step 2: Fix the import form, then run to confirm failure**

Run: `python -c "import sys; sys.path.insert(0,'src'); from ui.analytics_panel import log_insertion; print('ok')"`
Expected: `ok`. If so, change the test's import to `from ui.analytics_panel import log_insertion`.
Run: `pytest tests/unit/test_db_insertion_log.py -v`
Expected: FAIL — `db.execute` / `get_total_insertions` missing, and `log_insertion` still targets `InsertionLog`.

- [ ] **Step 3: Add `execute` + analytics reads to `DatabaseManager`**

In `src/db_manager.py`, at the end of the class (after `get_all_settings`, `:1784`), add:

```python
    # ============================================================
    # Consolidated methods merged from db_manager_additions (C1)
    # ============================================================

    def execute(self, sql, params=()):
        """Execute a write statement (INSERT/UPDATE/DELETE) and return the cursor.

        Used by analytics_panel.log_insertion. The context manager commits.
        """
        with self.get_connection() as conn:
            return conn.execute(sql, params)

    def get_top_inserted_elements(self, n=20):
        """Top N most-inserted elements with insertion counts.

        Returns list[dict] keys: element_id, name, list_name, format, type, count.
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.element_id,
                       e.name,
                       l.name   AS list_name,
                       e.format,
                       e.type,
                       COUNT(i.log_id) AS count
                FROM insertion_log i
                JOIN elements e ON e.element_id = i.element_fk
                LEFT JOIN lists l ON l.list_id = e.list_fk
                GROUP BY i.element_fk
                ORDER BY count DESC
                LIMIT ?
                """,
                (n,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_insertions_by_month(self):
        """Insertion counts by calendar month. Returns list[dict] keys: month, count."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT strftime('%Y-%m', inserted_at) AS month,
                       COUNT(*)                        AS count
                FROM insertion_log
                GROUP BY month
                ORDER BY month ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_insertions_by_user(self):
        """Insertion counts per user. Returns list[dict] keys: username, count, last_active."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(u.username, 'Guest') AS username,
                       COUNT(i.log_id)               AS count,
                       MAX(i.inserted_at)            AS last_active
                FROM insertion_log i
                LEFT JOIN users u ON u.user_id = i.user_fk
                GROUP BY i.user_fk
                ORDER BY count DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_total_insertions(self):
        """Total number of rows in insertion_log."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM insertion_log")
            row = cursor.fetchone()
            return row[0] if row else 0
```

> `get_connection(write=False)` is added in Task 6. If running strictly in order, write these four reads with plain `get_connection()` now and change to `write=False` in Task 6 Step 5 (which lists them). Either way the queries are identical.

- [ ] **Step 4: Point `log_insertion` at the lowercase table**

In `src/ui/analytics_panel.py`, in `log_insertion` (`:64-68`), change the SQL:

```python
        db.execute(
            "INSERT INTO insertion_log (element_fk, user_fk, project, host) "
            "VALUES (?, ?, ?, ?)",
            (element_id, user_id, project or None, host or None),
        )
```

(Only the table name `InsertionLog` -> `insertion_log` changes.)

- [ ] **Step 5: Run the test — confirm green**

Run: `pytest tests/unit/test_db_insertion_log.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/db_manager.py src/ui/analytics_panel.py tests/unit/test_db_insertion_log.py
git commit -m "fix(db): write insertion_log and add analytics read methods [C1]"
```

---

## Task 3: Batch-edit / pagination / phash methods

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_db_element_methods.py` (new)

**Interfaces:**
- Consumes: `elements`, `elements.phash` (Task 1). Produces: `count_elements_by_list`, `update_element_metadata`, `update_element_phash`, `get_elements_with_phash` (used by `api_server`, `batch_edit_dialog`, SP2 dedup).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_db_element_methods.py`:

```python
import pytest


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    eid = stax_db.create_element(lid, "e1", "2D", format="exr", tags="a")
    return lid, eid


@pytest.mark.unit
def test_count_elements_by_list(stax_db):
    lid, eid = _seed(stax_db)
    assert stax_db.count_elements_by_list(lid) == 1
    stax_db.update_element(eid, is_deprecated=1)
    assert stax_db.count_elements_by_list(lid) == 0  # deprecated excluded


@pytest.mark.unit
def test_update_element_metadata_whitelist(stax_db):
    lid, eid = _seed(stax_db)
    stax_db.update_element_metadata(
        eid, name="renamed", comment="c", bogus="ignored"
    )
    elem = stax_db.get_element_by_id(eid)
    assert elem["name"] == "renamed"
    assert elem["comment"] == "c"
    assert "bogus" not in elem


@pytest.mark.unit
def test_phash_roundtrip(stax_db):
    lid, eid = _seed(stax_db)
    assert stax_db.get_elements_with_phash() == []
    stax_db.update_element_phash(eid, "abcd1234")
    rows = stax_db.get_elements_with_phash()
    assert len(rows) == 1
    assert rows[0]["element_id"] == eid
    assert rows[0]["phash"] == "abcd1234"
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/unit/test_db_element_methods.py -v`
Expected: FAIL — methods missing.

- [ ] **Step 3: Add the methods**

In `src/db_manager.py`, append after the methods added in Task 2:

```python
    def count_elements_by_list(self, list_id):
        """Count of non-deprecated elements in a list."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM elements "
                "WHERE list_fk = ? AND is_deprecated = 0",
                (list_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    # Fields the batch editor / API PATCH may set.
    METADATA_ELEMENT_COLUMNS = {
        "name", "tags", "comment", "type", "is_deprecated", "list_fk",
    }

    def update_element_metadata(self, element_id, **kwargs):
        """Update whitelisted metadata fields on an element (batch edit / API PATCH).

        Unknown keys are ignored. Routes through the whitelisted update_element.
        """
        updates = {
            k: v for k, v in kwargs.items() if k in self.METADATA_ELEMENT_COLUMNS
        }
        if not updates:
            return False
        return self.update_element(element_id, **updates)

    def update_element_phash(self, element_id, phash):
        """Store the perceptual hash for an element (SP2 duplicate detection)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE elements SET phash = ? WHERE element_id = ?",
                (phash, element_id),
            )
            return cursor.rowcount > 0

    def get_elements_with_phash(self):
        """All elements that have a stored phash (SP2 duplicate detection)."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT element_id, name, list_fk, format, phash, preview_path "
                "FROM elements WHERE phash IS NOT NULL AND phash != ''"
            )
            return [dict(row) for row in cursor.fetchall()]
```

- [ ] **Step 4: Run to confirm green**

Run: `pytest tests/unit/test_db_element_methods.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_db_element_methods.py
git commit -m "fix(db): add count/metadata/phash element methods [C1]"
```

---

## Task 4: M1 — Whitelist SQL column names

**Files:**
- Modify: `src/db_manager.py` (`search_elements`, `update_element`)
- Test: `tests/unit/test_db_sql_injection.py` (new)

**Interfaces:**
- Hardens the `.format()`-into-SQL primitive in `search_elements`/`update_element` (and therefore `update_element_metadata`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_db_sql_injection.py`:

```python
import pytest


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    return lid, stax_db.create_element(lid, "keep", "2D", format="exr")


@pytest.mark.unit
def test_search_elements_bad_property_is_coerced_not_injected(stax_db):
    lid, eid = _seed(stax_db)
    # A hostile property name must not drop the table or raise a SQL error.
    results = stax_db.search_elements(
        "keep", property_name="name = 'x' OR 1=1; DROP TABLE elements; --"
    )
    # coerced to 'name': the loose search for 'keep' still matches the seeded row
    assert any(r["element_id"] == eid for r in results)
    # table survived
    assert stax_db.get_element_by_id(eid) is not None


@pytest.mark.unit
def test_update_element_ignores_non_whitelisted_keys(stax_db):
    lid, eid = _seed(stax_db)
    # A hostile "column" key must be filtered out, leaving a no-op (False).
    changed = stax_db.update_element(
        eid, **{"name = name || (SELECT 'x')": "boom"}
    )
    assert changed is False
    assert stax_db.get_element_by_id(eid)["name"] == "keep"
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/unit/test_db_sql_injection.py -v`
Expected: FAIL — the hostile property/key is interpolated and raises `sqlite3.OperationalError`.

- [ ] **Step 3: Add whitelist constants**

In `src/db_manager.py`, immediately inside `class DatabaseManager(object):` (right after the docstring, before `def __init__`), add class attributes:

```python
    # Column whitelists — guard against .format()-into-SQL injection (M1).
    SEARCHABLE_ELEMENT_COLUMNS = {"name", "format", "type", "comment", "tags"}
    UPDATABLE_ELEMENT_COLUMNS = {
        "list_fk", "name", "type", "filepath_soft", "filepath_hard",
        "is_hard_copy", "frame_range", "format", "comment", "tags",
        "preview_path", "gif_preview_path", "video_preview_path",
        "geometry_preview_path", "is_deprecated", "file_size", "phash",
    }
```

- [ ] **Step 4: Whitelist `search_elements`**

In `search_elements` (`:882`), replace the body's start:

```python
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if match_type == 'loose':
                query = "SELECT * FROM elements WHERE {} LIKE ? ORDER BY name".format(property_name)
```

with:

```python
        if property_name not in self.SEARCHABLE_ELEMENT_COLUMNS:
            self._log("search_elements: rejected column '{}', using 'name'".format(property_name))
            property_name = "name"

        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()

            if match_type == 'loose':
                query = "SELECT * FROM elements WHERE {} LIKE ? ORDER BY name".format(property_name)
```

(`property_name` is now guaranteed to be one of five literal column names before `.format`.)

- [ ] **Step 5: Whitelist `update_element`**

In `update_element` (`:837`), replace:

```python
        if not kwargs:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()

            set_clause = ', '.join(["{} = ?".format(k) for k in kwargs.keys()])
            values = list(kwargs.values()) + [element_id]
```

with:

```python
        updates = {
            k: v for k, v in kwargs.items() if k in self.UPDATABLE_ELEMENT_COLUMNS
        }
        if not updates:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()

            set_clause = ', '.join(["{} = ?".format(k) for k in updates.keys()])
            values = list(updates.values()) + [element_id]
```

- [ ] **Step 6: Run to confirm green**

Run: `pytest tests/unit/test_db_sql_injection.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/db_manager.py tests/unit/test_db_sql_injection.py
git commit -m "fix(db): whitelist column names in search_elements/update_element [M1]"
```

---

## Task 5: H3 — Remove duplicated favorite methods

**Files:**
- Modify: `src/db_manager.py` (delete dead first copies)
- Test: `tests/unit/test_db_favorites.py` (new)

**Interfaces:**
- Keeps the single canonical `(element_id, user_name=None, machine_name=None)` signature that `media_display_widget.py` already calls.

- [ ] **Step 1: Write the characterization test (favorites round-trip)**

Create `tests/unit/test_db_favorites.py`:

```python
import pytest


def _seed(stax_db):
    sid = stax_db.create_stack("S", "/tmp/S")
    lid = stax_db.create_list(sid, "L")
    return stax_db.create_element(lid, "fav", "2D")


@pytest.mark.unit
def test_favorite_roundtrip_user_machine_order(stax_db):
    eid = _seed(stax_db)
    # Call sites pass (element_id, user, machine) — this is the canonical order.
    assert stax_db.is_favorite(eid, "alice", "ws01") is False
    stax_db.add_favorite(eid, "alice", "ws01")
    assert stax_db.is_favorite(eid, "alice", "ws01") is True

    favs = stax_db.get_favorites("alice", "ws01")
    assert any(r["element_id"] == eid for r in favs)

    # A different identity must NOT see alice's favorite.
    assert stax_db.is_favorite(eid, "bob", "ws02") is False

    stax_db.remove_favorite(eid, "alice", "ws01")
    assert stax_db.is_favorite(eid, "alice", "ws01") is False
```

- [ ] **Step 2: Run — it PASSES today (last-definition wins), but proves the canonical signature**

Run: `pytest tests/unit/test_db_favorites.py -v`
Expected: PASS (the surviving second copies already implement this). This test now *locks* the behavior so deleting the dead copies cannot regress it.

- [ ] **Step 3: Delete the dead first copies**

In `src/db_manager.py`, delete the **first** definitions in the `FAVORITES OPERATIONS` block — `add_favorite` (`:898-906`), `remove_favorite` (`:908-916`), and `get_favorites` (`:918-928`) — i.e. remove exactly these three methods:

```python
    def add_favorite(self, element_id, machine_name, user_name=None):
        """Add element to favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO favorites (element_fk, machine_name, user_name) VALUES (?, ?, ?)",
                (element_id, machine_name, user_name)
            )
            return cursor.lastrowid

    def remove_favorite(self, element_id, machine_name, user_name=None):
        """Remove element from favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM favorites WHERE element_fk = ? AND machine_name = ? AND user_name IS ?",
                (element_id, machine_name, user_name)
            )
            return cursor.rowcount > 0

    def get_favorites(self, machine_name, user_name=None):
        """Get all favorite elements for user/machine."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.* FROM elements e
                JOIN favorites f ON e.element_id = f.element_fk
                WHERE f.machine_name = ? AND f.user_name IS ?
                ORDER BY e.name
            """, (machine_name, user_name))
            return [dict(row) for row in cursor.fetchall()]
```

Leave the `HISTORY OPERATIONS` section and the second copies (`add_favorite`/`remove_favorite`/`is_favorite`/`get_favorites` under `# Favorites management`, `:1004+`) untouched.

- [ ] **Step 4: Confirm the canonical copies are now the only definitions**

Run:
```bash
grep -n "def add_favorite\|def remove_favorite\|def get_favorites\|def is_favorite" src/db_manager.py
```
Expected: exactly one line each — `add_favorite` (was `:1004`), `remove_favorite`, `is_favorite`, `get_favorites`.

- [ ] **Step 5: Run the test again — still green**

Run: `pytest tests/unit/test_db_favorites.py -v`
Expected: PASS (behavior unchanged; now there is only one definition).

- [ ] **Step 6: Commit**

```bash
git add src/db_manager.py tests/unit/test_db_favorites.py
git commit -m "fix(db): remove duplicated signature-swapped favorite methods [H3]"
```

---

## Task 6: H1 + L6 — Lock-file race, journal mode, read/write lock scoping

**Files:**
- Modify: `src/file_lock.py` (`release` keeps the file)
- Modify: `src/db_manager.py` (`get_connection` `write` param + `journal_mode = DELETE`; flip read methods)
- Test: `tests/unit/test_file_lock_release.py`, `tests/unit/test_db_journal_mode.py`, `tests/unit/test_db_read_no_lock.py` (new)

**Interfaces:**
- Produces: `get_connection(self, write=True)`; read-only callers pass `write=False`.

- [ ] **Step 1: Write the H1 lock-file test**

Create `tests/unit/test_file_lock_release.py`:

```python
import os
import pytest

from file_lock import FileLockManager


@pytest.mark.unit
def test_release_keeps_lock_file_and_allows_reacquire(tmp_path):
    lock_path = str(tmp_path / "res.lock")
    lock = FileLockManager(lock_path)
    assert lock.acquire() is True
    assert os.path.exists(lock_path)
    lock.release()
    # H1: the file must persist (no delete-on-release inode race).
    assert os.path.exists(lock_path)
    assert lock.is_locked is False
    # And a fresh manager can re-lock the same file.
    lock2 = FileLockManager(lock_path)
    assert lock2.acquire() is True
    lock2.release()
```

- [ ] **Step 2: Run — confirm failure**

Run: `pytest tests/unit/test_file_lock_release.py -v`
Expected: FAIL — `release()` `os.remove`s the file, so `os.path.exists(lock_path)` is `False`.

- [ ] **Step 3: Stop deleting the lock file on release**

In `src/file_lock.py::release` (`:145-157`), replace:

```python
            # Close and clean up lock file
            if self.lock_file:
                self.lock_file.close()
                self.lock_file = None
            
            # Remove lock file
            try:
                if os.path.exists(self.lock_file_path):
                    os.remove(self.lock_file_path)
            except OSError:
                pass  # Lock file may be in use by another process
            
            self.is_locked = False
            return True
```

with:

```python
            # Close the handle but KEEP the lock file on disk.
            # Deleting it here caused a delete-on-release inode race (H1):
            # a blocked process and a fresh opener could both believe they
            # held the lock. The persisted, unlocked file is harmless.
            if self.lock_file:
                self.lock_file.close()
                self.lock_file = None

            self.is_locked = False
            return True
```

- [ ] **Step 4: Run — confirm green**

Run: `pytest tests/unit/test_file_lock_release.py -v`
Expected: 1 passed.

- [ ] **Step 5: Add `write` param + `journal_mode = DELETE` to `get_connection`**

In `src/db_manager.py::get_connection` (`:81-107`), change the signature and the lock guard. Replace:

```python
    @contextmanager
    def get_connection(self):
```

with:

```python
    @contextmanager
    def get_connection(self, write=True):
```

Then in the body, replace:

```python
            # Acquire external file lock if enabled (for network shares)
            if self.use_file_lock:
```

with:

```python
            # Acquire the external file lock only for writes (L6): concurrent
            # read connections no longer serialize behind one global OS lock.
            if self.use_file_lock and write:
```

And replace the WAL pragma (`:127`):

```python
                    conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
```

with:

```python
                    conn.execute("PRAGMA journal_mode = DELETE")  # network-share safe (H1); no -wal/-shm sidecars
```

- [ ] **Step 6: Flip read-only methods to `write=False`**

In `src/db_manager.py`, change `with self.get_connection() as conn:` to `with self.get_connection(write=False) as conn:` in exactly these read-only methods: `get_all_stacks`, `get_stack_by_id`, `get_lists_by_stack`, `get_sub_lists`, `get_list_by_id`, `get_list_hierarchy`, `get_elements_by_list`, `get_elements_count`, `get_element_by_id`, `search_elements` (already done in Task 4 Step 4), `get_ingestion_history`, `get_all_playlists`, `get_playlist_by_id`, `get_playlist_elements`, `is_element_in_playlist`, `get_all_tags`, `search_elements_by_tags`, `get_user_by_id`, `get_user_by_username`, `get_all_users`, `get_active_session`, `get_setting`, `get_all_settings`, `is_favorite`, `get_favorites` (canonical), and (added in Tasks 2–3) `get_top_inserted_elements`, `get_insertions_by_month`, `get_insertions_by_user`, `get_total_insertions`, `count_elements_by_list`, `get_elements_with_phash`.

Do NOT change writers (`create_*`, `update_*`, `delete_*`, `add_*`, `remove_*`, `set_setting`, `log_ingestion`, `reorder_*`, `execute`, `_create_schema`, `_apply_migrations`, `_run_versioned_migrations`) — they keep the default `write=True`.

- [ ] **Step 7: Write the journal-mode test**

Create `tests/unit/test_db_journal_mode.py`:

```python
import pytest


@pytest.mark.unit
def test_journal_mode_is_delete_not_wal(stax_db):
    with stax_db.get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "delete"
```

- [ ] **Step 8: Write the L6 read-no-lock test**

Create `tests/unit/test_db_read_no_lock.py`:

```python
import pytest

from db_manager import DatabaseManager


@pytest.mark.unit
def test_reads_do_not_acquire_file_lock(tmp_path, mocker):
    # Use a real lock-enabled manager so the write path DOES acquire.
    db_path = str(tmp_path / "lock_test.db")
    db = DatabaseManager(db_path, enable_logging=False, use_file_lock=True)

    import file_lock
    spy = mocker.spy(file_lock.FileLockManager, "acquire")

    # Read path: must NOT acquire the external lock.
    db.get_all_stacks()
    assert spy.call_count == 0

    # Write path: must acquire it.
    db.create_stack("S", "/tmp/S")
    assert spy.call_count >= 1
```

- [ ] **Step 9: Run all three — confirm green**

Run: `pytest tests/unit/test_db_journal_mode.py tests/unit/test_db_read_no_lock.py tests/unit/test_file_lock_release.py -v`
Expected: 3 passed. Also re-run Tasks 1–3 tests to confirm the `write=False` calls resolve:
Run: `pytest tests/unit/test_db_migrations.py tests/unit/test_db_insertion_log.py tests/unit/test_db_element_methods.py -v`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add src/file_lock.py src/db_manager.py tests/unit/test_file_lock_release.py tests/unit/test_db_journal_mode.py tests/unit/test_db_read_no_lock.py
git commit -m "fix(db): keep lock file on release, journal_mode=DELETE, scope lock to writes [H1][L6]"
```

---

## Task 7: L11 — Migration 6 row-count guard

**Files:**
- Modify: `src/db_manager.py` (`_apply_migrations` Migration 6)
- Test: `tests/unit/test_db_migration6_guard.py` (new)

**Interfaces:**
- Makes the `playlist_items` rebuild fail loudly (rollback) instead of silently dropping rows.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_db_migration6_guard.py`:

```python
import sqlite3
import pytest

from db_manager import DatabaseManager


def _seed_valid_db(tmp_path, n_elements):
    """Build a normal DB, return (path, list_id, [element_ids...], playlist_id)."""
    path = str(tmp_path / "mig6.db")
    db = DatabaseManager(path, enable_logging=False, use_file_lock=False)
    sid = db.create_stack("S", "/tmp/S")
    lid = db.create_list(sid, "L")
    eids = [db.create_element(lid, "e{}".format(i), "2D") for i in range(n_elements)]
    pid = db.create_playlist("P")
    return path, lid, eids, pid


def _install_legacy_playlist_items(path, rows):
    """Drop playlist_items and recreate it in the OLD (no item_id) shape with *rows*."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DROP TABLE playlist_items")
    conn.execute(
        "CREATE TABLE playlist_items ("
        " playlist_fk INTEGER NOT NULL,"
        " element_fk INTEGER NOT NULL,"
        " order_index INTEGER DEFAULT 0,"
        " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.executemany(
        "INSERT INTO playlist_items (playlist_fk, element_fk, order_index) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


@pytest.mark.unit
def test_migration6_preserves_distinct_rows(tmp_path):
    path, lid, eids, pid = _seed_valid_db(tmp_path, 3)
    _install_legacy_playlist_items(
        path, [(pid, eids[0], 0), (pid, eids[1], 1), (pid, eids[2], 2)]
    )
    # Re-open: _apply_migrations runs Migration 6.
    db2 = DatabaseManager(path, enable_logging=False, use_file_lock=False)
    with db2.get_connection(write=False) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(playlist_items)")}
        count = conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0]
    assert "item_id" in cols       # migrated to new shape
    assert count == 3              # no data loss


@pytest.mark.unit
def test_migration6_raises_on_row_count_mismatch(tmp_path):
    path, lid, eids, pid = _seed_valid_db(tmp_path, 1)
    # Two identical (playlist_fk, element_fk) rows collapse under the new
    # UNIQUE(playlist_fk, element_fk) constraint -> copied count < source count.
    _install_legacy_playlist_items(path, [(pid, eids[0], 0), (pid, eids[0], 1)])
    with pytest.raises(RuntimeError):
        DatabaseManager(path, enable_logging=False, use_file_lock=False)
    # Original legacy table must be intact (rolled back, not swapped/dropped).
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    src = conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0]
    conn.close()
    assert "playlist_items_old" not in tables
    assert src == 2
```

- [ ] **Step 2: Run — confirm failure**

Run: `pytest tests/unit/test_db_migration6_guard.py -v`
Expected: `test_migration6_raises_on_row_count_mismatch` FAILS — the current code swallows the copy failure and silently swaps the table (no `RuntimeError`).

- [ ] **Step 3: Add the row-count guard**

In `src/db_manager.py::_apply_migrations`, Migration 6 (`:469-534`), replace the copy-and-swap block. Replace from:

```python
                    # Try to copy existing data mapping older column names if present
                    try:
                        cursor.execute("PRAGMA table_info(playlist_items)")
                        cols = [r[1] for r in cursor.fetchall()]
                        select_cols = []
                        if 'playlist_fk' in cols:
                            select_cols.append('playlist_fk')
                        else:
                            select_cols.append('playlist')
                        if 'element_fk' in cols:
                            select_cols.append('element_fk')
                        else:
                            select_cols.append('element')
                        if 'order_index' in cols:
                            select_cols.append('order_index')
                        elif 'sort_order' in cols:
                            select_cols.append('sort_order')
                        else:
                            select_cols.append('0')

                        # Build copy statement defensively
                        copy_sql = "INSERT INTO playlist_items_new (playlist_fk, element_fk, order_index, added_at) SELECT {cols}, COALESCE(created_at, CURRENT_TIMESTAMP) FROM playlist_items".format(cols=','.join(select_cols))
                        try:
                            cursor.execute(copy_sql)
                        except Exception:
                            # Fallback: naive copy of playlist_fk, element_fk
                            try:
                                cursor.execute("INSERT INTO playlist_items_new (playlist_fk, element_fk) SELECT playlist_fk, element_fk FROM playlist_items")
                            except Exception:
                                pass

                    except Exception as e:
                        self._log("Migration 6: Data copy failed: {}".format(str(e)))

                    # Replace old table
                    try:
                        cursor.execute("ALTER TABLE playlist_items RENAME TO playlist_items_old")
                        cursor.execute("ALTER TABLE playlist_items_new RENAME TO playlist_items")
                        cursor.execute("DROP TABLE IF EXISTS playlist_items_old")
                    except Exception as e:
                        self._log("Migration 6: Table swap failed: {}".format(str(e)))
                    self._log("Migration 6: Complete")
```

to:

```python
                    # Count the source rows so we can verify nothing is lost.
                    src_count = cursor.execute(
                        "SELECT COUNT(*) FROM playlist_items"
                    ).fetchone()[0]

                    # Map older column names if present.
                    cursor.execute("PRAGMA table_info(playlist_items)")
                    cols = [r[1] for r in cursor.fetchall()]
                    select_cols = []
                    select_cols.append('playlist_fk' if 'playlist_fk' in cols else 'playlist')
                    select_cols.append('element_fk' if 'element_fk' in cols else 'element')
                    if 'order_index' in cols:
                        select_cols.append('order_index')
                    elif 'sort_order' in cols:
                        select_cols.append('sort_order')
                    else:
                        select_cols.append('0')

                    # INSERT OR IGNORE so a UNIQUE clash drops a row instead of
                    # aborting mid-statement — the count guard below then catches it.
                    copy_sql = (
                        "INSERT OR IGNORE INTO playlist_items_new "
                        "(playlist_fk, element_fk, order_index, added_at) "
                        "SELECT {cols}, COALESCE(created_at, CURRENT_TIMESTAMP) "
                        "FROM playlist_items".format(cols=','.join(select_cols))
                    )
                    cursor.execute(copy_sql)

                    # L11: verify row counts BEFORE the destructive swap. On
                    # mismatch, raise so the get_connection context rolls back
                    # (no commit) and the original playlist_items is preserved.
                    new_count = cursor.execute(
                        "SELECT COUNT(*) FROM playlist_items_new"
                    ).fetchone()[0]
                    if new_count != src_count:
                        raise RuntimeError(
                            "Migration 6: playlist_items copy lost rows "
                            "(source={}, copied={}); aborting to avoid data loss".format(
                                src_count, new_count
                            )
                        )

                    # Counts match — safe to swap.
                    cursor.execute("ALTER TABLE playlist_items RENAME TO playlist_items_old")
                    cursor.execute("ALTER TABLE playlist_items_new RENAME TO playlist_items")
                    cursor.execute("DROP TABLE IF EXISTS playlist_items_old")
                    self._log("Migration 6: Complete ({} rows preserved)".format(src_count))
```

- [ ] **Step 4: Run — confirm green**

Run: `pytest tests/unit/test_db_migration6_guard.py -v`
Expected: 2 passed. If `test_migration6_preserves_distinct_rows` fails on a foreign-key error during the copy, confirm the seeded `elements`/`playlists` parents exist (they do via `_seed_valid_db`) — do not weaken the guard.

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_db_migration6_guard.py
git commit -m "fix(db): verify playlist_items migration row counts, raise on mismatch [L11]"
```

---

## Task 8: Flip SP0's C1 strict-`xfail` smoke tests to PASS

**Files:**
- Modify: `tests/gui/test_api_smoke.py`, `tests/gui/test_batch_edit_smoke.py` (remove `xfail` markers created by SP0)

**Interfaces:**
- Consumes: everything from Tasks 1–7. Depends on SP0 having created these two files.

- [ ] **Step 1: Confirm the SP0 smoke files exist**

Run:
```bash
ls tests/gui/test_api_smoke.py tests/gui/test_batch_edit_smoke.py
```
Expected: both listed. If missing, **stop** — SP0 is not merged; SP1 cannot flip tests that don't exist.

- [ ] **Step 2: Observe the current strict-xfail state (should now XPASS-fail)**

Run: `pytest tests/gui/test_api_smoke.py tests/gui/test_batch_edit_smoke.py -v`
Expected: the two C1 tests report **XPASS** and, because SP0 marked them `strict=True`, the run **FAILS** (an xpass under strict is a failure). That failure is the signal that C1 is fixed and the markers must come off.

- [ ] **Step 3: Remove the xfail in `test_api_smoke.py`**

In `tests/gui/test_api_smoke.py`, delete the decorator above `test_analytics_top_endpoint_no_server_error`:

```python
@pytest.mark.xfail(reason="C1: analytics endpoint calls DB methods missing until SP1",
                   strict=True)
```

so the test is a plain `@pytest.mark.gui` test. Leave the assertion (`resp.status_code != 500`) unchanged.

- [ ] **Step 4: Remove the xfail in `test_batch_edit_smoke.py`**

In `tests/gui/test_batch_edit_smoke.py`, delete the decorator above `test_batch_edit_apply_resolves_db_method`:

```python
@pytest.mark.xfail(reason="C1: batch edit calls update_element_metadata, missing until SP1",
                   strict=True)
```

The surviving assertion `assert hasattr(stax_db, "update_element_metadata")` now holds.

- [ ] **Step 5: Run the two smoke files — confirm real PASS**

Run: `pytest tests/gui/test_api_smoke.py tests/gui/test_batch_edit_smoke.py -v`
Expected: all PASS (no xfail, no xpass). If `test_analytics_top_endpoint_no_server_error` still 500s, the analytics method/`insertion_log` wiring from Tasks 1–2 is incomplete — fix the root cause, do not re-add the marker.

- [ ] **Step 6: Commit**

```bash
git add tests/gui/test_api_smoke.py tests/gui/test_batch_edit_smoke.py
git commit -m "test: flip C1 smoke tests to passing after DB consolidation [C1]"
```

---

## Task 9: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire collected suite**

Run: `pytest -m "not manual"`
Expected: **0 failed, 0 errored, 0 unexpected xpass.** Note the passed/xfail counts. Every SP1 unit test (Tasks 1–7) passes; the two SP0 C1 smoke tests now pass; no other SP0 test regressed.

- [ ] **Step 2: Confirm no lingering reliance on the orphaned additions module**

Run:
```bash
grep -rn "db_manager_additions\|import db_migrations" src/ main.py nuke_launcher.py menu.py
```
Expected: no `import db_manager_additions` anywhere in live code; the only `db_migrations` reference is `from db_migrations import run_migrations` inside `DatabaseManager._run_versioned_migrations`. (`src/db_manager_additions.py` and `src/nuke_bridge_patch.py` remain on disk — their deletion is SP8, not SP1.)

- [ ] **Step 3: Push and confirm CI is green on both OSes**

```bash
git push
gh run watch
```
Expected: `test (ubuntu-latest)` and `test (windows-latest)` both conclude `success`. If a job fails, read `gh run view --log-failed` and fix the root cause — never weaken a test or re-add an xfail to go green.

---

## Self-Review

**1. Issue coverage (every SP1 issue maps to a task):**
- **C1** — merge orphaned methods onto lowercase schema → Tasks 2, 3; versioned migration runner + `run_migrations` wired into `__init__` → Task 1; `phash` column → Task 1; insertion-log path actually written → Task 2 (`execute` + lowercase `log_insertion`); analytics/API/batch-edit wired to real methods → Tasks 2, 3 (no caller edits needed beyond `analytics_panel` SQL); flips SP0 C1 smoke tests → Task 8. ✓
- **H1** — lock-file delete-on-release race removed (create once, keep, unlock+close) → Task 6 Steps 1-4; `journal_mode` WAL → DELETE → Task 6 Step 5. ✓
- **H3** — duplicated signature-swapped favorite methods removed, one canonical signature kept, call sites verified unchanged → Task 5. ✓
- **M1** — `search_elements` / `update_element` column whitelists → Task 4 (and `update_element_metadata` routes through the whitelisted `update_element` → Task 3). ✓
- **L6** — external lock scoped to writes; read connections concurrent via `get_connection(write=False)` → Task 6 Steps 5-6, 8. ✓
- **L11** — Migration 6 verifies copied row counts and raises on mismatch (rollback, no data loss) → Task 7. ✓

**2. SP0 dependencies noted:** `stax_db`/`stax_config`/`mock_nuke` fixtures and the 3-tier layout (all tasks); the two C1 smoke files must pre-exist (Task 8 Step 1 guards this); `pytest -m "not manual"` and the gating CI (Task 9). The `write=False` kwarg is introduced in Task 6 but referenced by earlier tasks' tests — Task 1 Step 2 and Task 2 Step 3 give the exact fallback (plain `get_connection()`) if executing strictly in order, with the flip listed explicitly in Task 6 Step 6.

**3. Placeholder scan:** No "TBD/TODO/handle appropriately". Every step shows complete code and an exact command with expected output. One action per step. Fallbacks (import form in Task 2 Step 1-2; FK note in Task 7 Step 4) specify the concrete alternative and forbid weakening the fix.

**4. Type/signature consistency:** All merged methods use `with self.get_connection([write=...]) as conn:` and lowercase tables (`elements`, `lists`, `insertion_log`, `users`) — never `self.conn`/`self._lock`/capitalized tables. `update_element_metadata` whitelist ⊆ `UPDATABLE_ELEMENT_COLUMNS`. Analytics read-method keys (`element_id, name, list_name, format, type, count` / `month, count` / `username, count, last_active`) match what `analytics_panel.py` and `api_server.py` consume. Favorite canonical signature `(element_id, user_name=None, machine_name=None)` matches `media_display_widget.py` call sites. `_build_flask_app(db, config)`, `BatchEditDialog(element_ids, db, parent=None)`, `DatabaseManager(db_path, enable_logging=False, use_file_lock=True)` match the verified signatures.

---

## Notes for the executor
- **Never weaken a test or re-add an `xfail` to go green.** If a C1 smoke test still fails after Tasks 1-7, the DB wiring is incomplete — fix the root cause (systematic-debugging).
- Run `pytest -m "not manual"` before every commit; commit only on green.
- Do **not** edit `src/api_server.py` or `src/ui/batch_edit_dialog.py` — their calls resolve once the methods exist. If you feel the urge to edit them, a merged method's name or signature is wrong; fix the method instead.
- Do **not** touch password hashing, the async pipeline, the API token check, or delete the orphaned `*_additions`/`*_patch` files — those are SP4/SP2/SP8.
- Keep `src/db_manager_additions.py` on disk but unreferenced; nothing in live code should `import db_manager_additions` after SP1.
