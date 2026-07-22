# EP6 — Ingestion Automation & Job Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give StaX a real ingest-automation surface on top of SP2's async workers — a durable `ingest_jobs` ledger + a `JobQueueDashboard` dock with retry/cancel, a stdlib polling `WatchFolderScanner`, reusable `ingest_recipes`, duplicate-handling policies, a preflight validator, named proxy/transcode profiles that overlay SP2's preview config, ingest-completion notifications, and a whitelisted action-chain executor.

**Architecture:** EP6 does **not** build a second execution queue. Execution stays on SP2's `IngestWorker`/`PreviewWorker`. EP6 adds (a) DB tables + CRUD in `DatabaseManager` (ledger, notifications, watch folders, recipes, proxy profiles, action chains); (b) one pure, Qt-free helper module `src/ingest_automation.py` (`scan_folder`, `apply_recipe_to_config`, `resolve_duplicate_action`, `run_preflight`, `profile_to_config_overlay`, `run_action_chain`); (c) new widgets (`JobQueueDashboard`, `PreflightDialog`) and a `WatchFolderScanner(QThread)`; (d) wiring in `main.py`/`ingestion_core.py` that feeds the ledger from `IngestWorker` signals and consults recipes/policies/chains at ingest. SP2's worker and EP4's template/relationship APIs are stated as interfaces; where absent, integration tests are `xfail(strict=True)` with the dependency id.

**Tech Stack:** Python 3.9, SQLite (via `DatabaseManager`), PySide2 (headless offscreen), pytest / pytest-qt, stdlib `os`/`json`/`fnmatch`. No new dependencies (no `watchdog`).

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat in *tests* (`from ingest_automation import ...`); *source* edits preserve each file's existing convention (`main.py`, `ingestion_core.py`, `ui/*` use `from src.<module> import ...`). **Logging:** `logging`, not `print`. **Commits:** conventional.
- **No new dependencies.** Watch folders use a stdlib `os.scandir` polling scanner (no `watchdog`).
- **No second queue.** `ingest_jobs` is a state ledger; execution stays on SP2's `IngestWorker`/`PreviewWorker`. Retry re-submits a payload to a fresh `IngestWorker`; cancel flags the running one.
- **Proxy profiles reuse SP2's config-driven `PreviewWorker`** — they overlay existing config keys (`preview_size`, `gif_size`, `gif_fps`, `sequence_preview_fps`, `generate_video_previews`); no `ffmpeg_wrapper` signature changes, no invented codec knobs.
- **Duplicate policies reuse SP2's wired `duplicate_detection`.**
- **Action chains are whitelisted handlers, never `exec()`** (do not reintroduce C2 RCE).
- **All dynamic SQL uses fixed, code-literal column names and parameterized values** (SP1 whitelisting pattern).
- **Dependency — SP2:** `IngestWorker(db, config_dict, jobs, copy_policy)` with signals `progress(int,int,str)`, `file_done(dict)`, `ingest_finished(int,int,int)`, `ingest_failed(str)`, `cancel()`; `get_preview_queue()`; `ingest_file(...) -> {'success', 'reason'=='duplicate_skipped', ...}` with wired `find_duplicates`. Wiring that needs the worker is `xfail(strict=True)` tagged `SP2` when it is absent.
- **Dependency — SP3:** cross-platform `ffmpeg_wrapper` (`get_ffmpeg`, `generate_video_preview`, `generate_sequence_video_preview`).
- **Dependency — EP4:** recipe `metadata_template_id` (`apply_template`) and action-chain `set_field`/`version` relationships (`add_relationship`) are `xfail(strict=True)` tagged `EP4` until EP4 lands.
- **Dependency — SP1:** `get_connection(write=True|False)` + migration runner. If executing before SP1, drop the `write=` kwarg.
- New widgets, the scanner, and the pure helpers live in their own files (single responsibility).

---

## Key facts (verified against the codebase)

- Table CRUD + idempotent migrations live in `DatabaseManager` (`src/db_manager.py`); the EP2/EP4 pattern is `CREATE TABLE IF NOT EXISTS ...` in `_create_schema` + a migration block, methods using `with self.get_connection(write=True) as conn: cur = conn.cursor(); ...`.
- `ingestion_history` schema: `history_id, element_fk, action, source_path, target_list, status, message, ingested_at` (`src/db_manager.py:282`); `log_ingestion(action, source_path, target_list, status, message=None, element_id=None)` (`:934`); `get_ingestion_history(limit=100)` (`:959`).
- `create_element(list_id, name, element_type, **kwargs)` (`:741`); `create_stack(name, path)` (`:559`); `create_list(stack_id, name, parent_list_id=None)` (`:609`); `get_setting/set_setting` (`:1735/:1752`).
- `IngestionCore(db_manager, config)` — `config` is a **dict**; `self.preview_dir`; `ingest_file(source_path, target_list_id, copy_policy='soft', comment=None, tags=None, pre_hook=None, post_hook=None)` returns `{'success','element_id','message', ...}` (`src/ingestion_core.py:369,552`).
- SP2 `IngestWorker(db, config, jobs, copy_policy="soft", parent=None)` with `progress`/`file_done`/`ingest_finished`/`ingest_failed`/`cancel()` (`src/ingest_worker.py`, from the SP2 plan). SP2 `PreviewWorker._process` reads config keys `preview_size`, `gif_size`, `gif_fps`, `gif_duration`, `sequence_preview_fps`, `generate_previews`, `generate_video_previews` (`src/preview_worker.py`).
- `Config`: `.get(key, default=None)`, `.get_all()` (dict copy); key is `default_copy_policy` (`src/config.py:57`); preview config defaults in `DEFAULT_CONFIG` (`preview_size=512`, `gif_size=256`, `gif_fps=10`, `sequence_preview_fps=24`).
- `ffmpeg_wrapper` via `get_ffmpeg()`: `generate_video_preview(input_path, output_path, max_size=512, duration=10, threads=4)`, `generate_sequence_video_preview(sequence_pattern, output_path, max_size=512, fps=24, start_frame=1, max_frames=None)` — **no CRF/codec kwargs** (`src/ffmpeg_wrapper.py:210,491`).
- `main.py` dock pattern: `self.history_dock = QtWidgets.QDockWidget("History", self); self.history_dock.setWidget(HistoryPanel(self.db)); self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)` (`:252`); `self.ingestion = IngestionCore(self.db, self.config.get_all())` (`:96`); `perform_ingestion(self, files, target_list_id)` (`:714`); `check_admin_permission(self, action_name=...)` (`:527`).
- `SettingsPanel(config, db_manager, main_window=None, parent=None)`; `self.tab_widget` with `addTab(...)`; admin gate via `self.main_window.check_admin_permission()` (`src/ui/settings_panel.py:20,38`).
- SP0 fixtures: `stax_db` (real `DatabaseManager` on temp DB), `stax_config`, `tiny_png`, `tiny_sequence`, headless `qtbot`.

---

# Cluster 6A — Job queue, retry, notifications

## Task 1: `ingest_jobs` ledger + CRUD

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep6_job_ledger.py`

**Interfaces:**
- Produces table `ingest_jobs` and: `create_job(kind, source_path, target_list_id=None, recipe_id=None, payload=None, status='pending') -> int`, `get_jobs(status=None, limit=200) -> list[dict]` (parsed `payload`), `get_job(job_id) -> dict`, `update_job_status(job_id, status, message=None)`, `bump_job_attempt(job_id)`, `count_jobs_by_status() -> dict`, `clear_finished_jobs()`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_job_ledger.py`:

```python
import pytest


@pytest.mark.unit
def test_create_job_defaults_to_pending(stax_db):
    jid = stax_db.create_job("ingest", "/a/shot.exr", target_list_id=3,
                             payload={"source_path": "/a/shot.exr", "target_list_id": 3})
    job = stax_db.get_job(jid)
    assert job["status"] == "pending"
    assert job["attempts"] == 0
    assert job["payload"]["target_list_id"] == 3


@pytest.mark.unit
def test_status_transitions_and_attempt_bump(stax_db):
    jid = stax_db.create_job("ingest", "/a/x.mov")
    stax_db.bump_job_attempt(jid)
    stax_db.update_job_status(jid, "failed", message="boom")
    job = stax_db.get_job(jid)
    assert job["status"] == "failed"
    assert job["attempts"] == 1
    assert job["message"] == "boom"


@pytest.mark.unit
def test_get_jobs_filters_by_status(stax_db):
    stax_db.create_job("ingest", "/a/1")
    j2 = stax_db.create_job("ingest", "/a/2")
    stax_db.update_job_status(j2, "done")
    pending = stax_db.get_jobs(status="pending")
    assert [j["source_path"] for j in pending] == ["/a/1"]


@pytest.mark.unit
def test_count_and_clear_finished(stax_db):
    a = stax_db.create_job("ingest", "/a/a")
    b = stax_db.create_job("ingest", "/a/b")
    stax_db.update_job_status(a, "done")
    stax_db.update_job_status(b, "failed")
    counts = stax_db.count_jobs_by_status()
    assert counts["done"] == 1 and counts["failed"] == 1
    stax_db.clear_finished_jobs()
    assert stax_db.count_jobs_by_status().get("done") is None
    assert stax_db.count_jobs_by_status().get("failed") == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_job_ledger.py -v`
Expected: FAIL — `create_job` not defined.

- [ ] **Step 3: Implement schema + migration + CRUD**

Add the table to `_create_schema` and the idempotent migration block:

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingest_jobs (
                job_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                kind           TEXT NOT NULL DEFAULT 'ingest',
                source_path    TEXT,
                target_list_id INTEGER,
                recipe_id      INTEGER,
                status         TEXT NOT NULL DEFAULT 'pending',
                message        TEXT,
                attempts       INTEGER NOT NULL DEFAULT 0,
                payload_json   TEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

Add methods (import `json` at module top if not present):

```python
    _FINISHED_JOB_STATES = ("done", "skipped", "cancelled")

    def create_job(self, kind, source_path, target_list_id=None, recipe_id=None,
                   payload=None, status="pending"):
        import json
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ingest_jobs (kind, source_path, target_list_id, recipe_id, "
                "status, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (kind, source_path, target_list_id, recipe_id, status,
                 json.dumps(payload) if payload is not None else None))
            return cur.lastrowid

    def _row_to_job(self, row):
        import json
        d = dict(row)
        d["payload"] = json.loads(d["payload_json"]) if d.get("payload_json") else None
        return d

    def get_job(self, job_id):
        with self.get_connection(write=False) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE job_id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None

    def get_jobs(self, status=None, limit=200):
        with self.get_connection(write=False) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM ingest_jobs WHERE status = ? ORDER BY job_id LIMIT ?",
                    (status, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ingest_jobs ORDER BY job_id LIMIT ?", (limit,)).fetchall()
            return [self._row_to_job(r) for r in rows]

    def update_job_status(self, job_id, status, message=None):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE ingest_jobs SET status = ?, message = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (status, message, job_id))

    def bump_job_attempt(self, job_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE ingest_jobs SET attempts = attempts + 1, status = 'running', "
                "updated_at = CURRENT_TIMESTAMP WHERE job_id = ?", (job_id,))

    def count_jobs_by_status(self):
        with self.get_connection(write=False) as conn:
            return {r[0]: r[1] for r in conn.execute(
                "SELECT status, COUNT(*) FROM ingest_jobs GROUP BY status").fetchall()}

    def clear_finished_jobs(self):
        placeholders = ",".join("?" for _ in self._FINISHED_JOB_STATES)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM ingest_jobs WHERE status IN ({})".format(placeholders),
                list(self._FINISHED_JOB_STATES))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep6_job_ledger.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep6_job_ledger.py
git commit -m "feat(ep6): add ingest_jobs ledger table and CRUD"
```

---

## Task 2: `notifications` center + CRUD

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep6_notifications.py`

**Interfaces:**
- Produces table `notifications` and: `add_notification(title, body=None, level='info') -> int`, `get_notifications(unread_only=False, limit=100) -> list[dict]`, `unread_notification_count() -> int`, `mark_notifications_read()`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_notifications.py`:

```python
import pytest


@pytest.mark.unit
def test_add_and_unread_count(stax_db):
    stax_db.add_notification("Ingest complete", "5 ok / 0 skipped", level="success")
    stax_db.add_notification("Watch error", "path missing", level="error")
    assert stax_db.unread_notification_count() == 2
    unread = stax_db.get_notifications(unread_only=True)
    assert unread[0]["title"] == "Watch error"   # most recent first


@pytest.mark.unit
def test_mark_read_clears_unread(stax_db):
    stax_db.add_notification("x")
    stax_db.mark_notifications_read()
    assert stax_db.unread_notification_count() == 0
    assert len(stax_db.get_notifications()) == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_notifications.py -v`
Expected: FAIL — `add_notification` not defined.

- [ ] **Step 3: Implement schema + migration + CRUD**

Add the table (to `_create_schema` + migration):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                level      TEXT NOT NULL DEFAULT 'info',
                title      TEXT NOT NULL,
                body       TEXT,
                is_read    INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

Methods:

```python
    def add_notification(self, title, body=None, level="info"):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO notifications (level, title, body) VALUES (?, ?, ?)",
                (level, title, body))
            return cur.lastrowid

    def get_notifications(self, unread_only=False, limit=100):
        sql = "SELECT * FROM notifications"
        if unread_only:
            sql += " WHERE is_read = 0"
        sql += " ORDER BY notification_id DESC LIMIT ?"
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]

    def unread_notification_count(self):
        with self.get_connection(write=False) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE is_read = 0").fetchone()[0]

    def mark_notifications_read(self):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep6_notifications.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep6_notifications.py
git commit -m "feat(ep6): add notifications table and CRUD"
```

---

## Task 3: `JobQueueDashboard` widget

**Files:**
- Create: `src/ui/job_queue_dashboard.py`
- Test: `tests/gui/test_ep6_job_dashboard.py`

**Interfaces:**
- Consumes: `get_jobs`, `clear_finished_jobs`.
- Produces: `JobQueueDashboard(db, parent=None)` with `refresh()`, signals `retry_requested(int)` and `cancel_requested(int)`; a `jobs_table` (Status / File / Attempts / Message), buttons `retry_button` (enabled only for `failed` rows), `cancel_button` (enabled only for `pending`/`running`), `clear_button`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep6_job_dashboard.py`:

```python
import pytest
from ui.job_queue_dashboard import JobQueueDashboard


@pytest.mark.gui
def test_dashboard_lists_jobs(qtbot, stax_db):
    stax_db.create_job("ingest", "/a/a.exr")
    j = stax_db.create_job("ingest", "/a/b.exr")
    stax_db.update_job_status(j, "failed", message="bad")
    dash = JobQueueDashboard(stax_db)
    qtbot.addWidget(dash)
    dash.refresh()
    assert dash.jobs_table.rowCount() == 2


@pytest.mark.gui
def test_retry_enabled_only_for_failed(qtbot, stax_db):
    j = stax_db.create_job("ingest", "/a/b.exr")
    stax_db.update_job_status(j, "failed", message="bad")
    dash = JobQueueDashboard(stax_db)
    qtbot.addWidget(dash)
    dash.refresh()
    dash.jobs_table.selectRow(0)
    dash._sync_buttons()
    assert dash.retry_button.isEnabled() is True
    with qtbot.waitSignal(dash.retry_requested, timeout=1000) as blk:
        dash.retry_button.click()
    assert blk.args == [j]
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep6_job_dashboard.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/job_queue_dashboard.py`:

```python
# -*- coding: utf-8 -*-
"""Central job-queue dashboard (EP6, F033/F034).

Reads the ingest_jobs ledger and controls SP2's IngestWorker via signals.
It does NOT execute jobs itself — retry/cancel are emitted to the host, which
re-submits to a fresh IngestWorker / flags the running one.
"""

import logging

from PySide2 import QtWidgets, QtCore

log = logging.getLogger(__name__)

_ACTIVE_STATES = ("pending", "running")


class JobQueueDashboard(QtWidgets.QWidget):
    retry_requested  = QtCore.Signal(int)
    cancel_requested = QtCore.Signal(int)

    def __init__(self, db, parent=None):
        super(JobQueueDashboard, self).__init__(parent)
        self.db = db
        self._row_jobs = []      # row index -> (job_id, status)
        layout = QtWidgets.QVBoxLayout(self)

        self.jobs_table = QtWidgets.QTableWidget(0, 4)
        self.jobs_table.setHorizontalHeaderLabels(["Status", "File", "Attempts", "Message"])
        self.jobs_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.jobs_table.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self.jobs_table)

        row = QtWidgets.QHBoxLayout()
        self.retry_button = QtWidgets.QPushButton("Retry")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.clear_button = QtWidgets.QPushButton("Clear finished")
        self.retry_button.clicked.connect(self._on_retry)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.clear_button.clicked.connect(self._on_clear)
        for b in (self.retry_button, self.cancel_button, self.clear_button):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        self._sync_buttons()

    def refresh(self):
        import os
        jobs = self.db.get_jobs()
        self._row_jobs = []
        self.jobs_table.setRowCount(len(jobs))
        for r, job in enumerate(jobs):
            src = job.get("source_path") or ""
            self.jobs_table.setItem(r, 0, QtWidgets.QTableWidgetItem(job.get("status", "")))
            self.jobs_table.setItem(r, 1, QtWidgets.QTableWidgetItem(os.path.basename(src)))
            self.jobs_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(job.get("attempts", 0))))
            self.jobs_table.setItem(r, 3, QtWidgets.QTableWidgetItem(job.get("message") or ""))
            self._row_jobs.append((job["job_id"], job.get("status")))
        self._sync_buttons()

    def _selected(self):
        r = self.jobs_table.currentRow()
        if 0 <= r < len(self._row_jobs):
            return self._row_jobs[r]
        return (None, None)

    def _sync_buttons(self):
        job_id, status = self._selected()
        self.retry_button.setEnabled(status == "failed")
        self.cancel_button.setEnabled(status in _ACTIVE_STATES)

    def _on_retry(self):
        job_id, status = self._selected()
        if job_id is not None and status == "failed":
            self.retry_requested.emit(job_id)

    def _on_cancel(self):
        job_id, status = self._selected()
        if job_id is not None and status in _ACTIVE_STATES:
            self.cancel_requested.emit(job_id)

    def _on_clear(self):
        self.db.clear_finished_jobs()
        self.refresh()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep6_job_dashboard.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/job_queue_dashboard.py tests/gui/test_ep6_job_dashboard.py
git commit -m "feat(ep6): add JobQueueDashboard widget with retry/cancel"
```

---

## Task 4: Wire the ledger + dashboard to SP2's IngestWorker (main.py)

**Files:**
- Modify: `main.py`
- Test: `tests/gui/test_ep6_dashboard_wiring.py`

**Interfaces:**
- Consumes: `IngestWorker` (SP2), `create_job`, `bump_job_attempt`, `update_job_status`, `add_notification`, `JobQueueDashboard`.
- Produces: a `job_dashboard` bottom dock; `_record_ingest_jobs(files, target_list_id, recipe_id=None) -> list[int]`; `_on_job_file_done(result)`; `_on_ingest_finished_notify(s, k, e)`; `_retry_job(job_id)`.

- [ ] **Step 1: Write the failing test (job-ledger recording, worker-independent)**

Create `tests/gui/test_ep6_dashboard_wiring.py`:

```python
import pytest


@pytest.mark.gui
def test_record_ingest_jobs_creates_pending_rows(qtbot, stax_db, stax_config, mock_nuke):
    from main import MainWindow
    win = MainWindow(stax_config, stax_db)
    qtbot.addWidget(win)
    ids = win._record_ingest_jobs(["/a/x.exr", "/a/y.exr"], target_list_id=2)
    assert len(ids) == 2
    pending = stax_db.get_jobs(status="pending")
    assert {j["source_path"] for j in pending} == {"/a/x.exr", "/a/y.exr"}
    assert pending[0]["payload"]["target_list_id"] == 2


@pytest.mark.gui
def test_ingest_finished_emits_notification(qtbot, stax_db, stax_config, mock_nuke):
    from main import MainWindow
    win = MainWindow(stax_config, stax_db)
    qtbot.addWidget(win)
    win._on_ingest_finished_notify(3, 1, 0)
    notes = stax_db.get_notifications()
    assert notes and "3" in notes[0]["body"]


@pytest.mark.xfail(strict=True, reason="SP2: IngestWorker retry path")
@pytest.mark.gui
def test_retry_job_starts_worker(qtbot, stax_db, stax_config, mock_nuke):
    from main import MainWindow
    win = MainWindow(stax_config, stax_db)
    qtbot.addWidget(win)
    jid = stax_db.create_job("ingest", "/a/x.exr", target_list_id=2,
                             payload={"source_path": "/a/x.exr", "target_list_id": 2})
    stax_db.update_job_status(jid, "failed", message="boom")
    win._retry_job(jid)
    assert stax_db.get_job(jid)["status"] in ("pending", "running")
    assert win._ingest_worker is not None
```

> Match `MainWindow.__init__`'s real signature (read `main.py` — it is `MainWindow(config, db, ...)`; adjust the constructor call and pass `mock_nuke` where the real app injects the bridge). The first two tests must pass; the retry test is `xfail(strict)` `SP2` until `IngestWorker` is importable and startable in this harness.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep6_dashboard_wiring.py -v`
Expected: FAIL — `_record_ingest_jobs` / `_on_ingest_finished_notify` missing (and the retry test `xfail`).

- [ ] **Step 3: Implement the dock + wiring**

In `main.py` `setup_ui`, after the History dock block (`:257`), add a Job Queue dock:

```python
        # Job Queue dock (EP6)
        from src.ui.job_queue_dashboard import JobQueueDashboard
        self.job_dashboard = JobQueueDashboard(self.db)
        self._force_panel_palette(self.job_dashboard, "#191a1a")
        self.job_queue_dock = QtWidgets.QDockWidget("Job Queue", self)
        self.job_queue_dock.setWidget(self.job_dashboard)
        self.job_queue_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.job_queue_dock)
        self.job_dashboard.retry_requested.connect(self._retry_job)
        self.job_dashboard.cancel_requested.connect(self._cancel_job)
```

Add the helper methods (near `perform_ingestion`, `:714`):

```python
    def _record_ingest_jobs(self, files, target_list_id, recipe_id=None):
        """Insert one pending ingest_jobs row per file; return the job ids."""
        ids = []
        for f in files:
            ids.append(self.db.create_job(
                "ingest", f, target_list_id=target_list_id, recipe_id=recipe_id,
                payload={"source_path": f, "target_list_id": target_list_id,
                         "recipe_id": recipe_id}))
        return ids

    def _on_job_file_done(self, result):
        """Update the matching pending/running ledger row from an IngestWorker result."""
        if not isinstance(result, dict):
            return
        src = result.get("source_path")
        job = None
        for j in self.db.get_jobs(status="running") + self.db.get_jobs(status="pending"):
            if j.get("source_path") == src:
                job = j
                break
        if job is None:
            return
        if result.get("success"):
            status = "done"
        elif result.get("reason") == "duplicate_skipped":
            status = "skipped"
        else:
            status = "failed"
        self.db.update_job_status(job["job_id"], status, message=result.get("message"))
        self.job_dashboard.refresh()

    def _on_ingest_finished_notify(self, success, skipped, errors):
        level = "error" if errors else "success"
        self.db.add_notification(
            "Ingest complete",
            "{} ok / {} skipped / {} errors".format(success, skipped, errors),
            level=level)
        self.statusBar().showMessage(
            "Ingest complete: {} ok, {} skipped, {} errors".format(success, skipped, errors),
            5000)
        self.job_dashboard.refresh()

    def _retry_job(self, job_id):
        """Re-submit a failed job's payload to a fresh IngestWorker (SP2 seam)."""
        from src.ingest_worker import IngestWorker
        job = self.db.get_job(job_id)
        if not job or not job.get("payload"):
            return
        payload = job["payload"]
        self.db.update_job_status(job_id, "pending")
        self.db.bump_job_attempt(job_id)
        worker = IngestWorker(
            self.db, self.config.get_all(),
            [(payload["source_path"], payload["target_list_id"])],
            copy_policy=self.config.get("default_copy_policy"))
        self._ingest_worker = worker
        worker.file_done.connect(self._on_job_file_done)
        worker.ingest_finished.connect(self._on_ingest_finished_notify)
        worker.start()

    def _cancel_job(self, job_id):
        if getattr(self, "_ingest_worker", None) is not None:
            self._ingest_worker.cancel()
        self.db.update_job_status(job_id, "cancelled")
        self.job_dashboard.refresh()
```

In `perform_ingestion` (`:714`), after building the worker (per the SP2 plan's `perform_ingestion`), call `self._record_ingest_jobs(files, target_list_id)` before `worker.start()` and connect `worker.file_done.connect(self._on_job_file_done)` and `worker.ingest_finished.connect(self._on_ingest_finished_notify)` alongside the SP2 completion handler.

- [ ] **Step 4: Run to verify pass (2 pass, 1 xfail)**

Run: `pytest tests/gui/test_ep6_dashboard_wiring.py -v`
Expected: 2 passed, 1 xfailed (the SP2 retry path).

- [ ] **Step 5: Commit**

```bash
git add main.py tests/gui/test_ep6_dashboard_wiring.py
git commit -m "feat(ep6): job dashboard dock + IngestWorker ledger/notification wiring"
```

---

# Cluster 6B — Watch folders, recipes, duplicate policies, preflight

## Task 5: `watch_folders` table + CRUD

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep6_watch_folders.py`

**Interfaces:**
- Produces table `watch_folders` and: `create_watch_folder(path, target_list_id=None, recipe_id=None, interval_sec=30, enabled=True) -> int`, `get_watch_folders(enabled_only=False) -> list[dict]`, `update_watch_folder(watch_id, **fields)`, `delete_watch_folder(watch_id)`, `set_watch_last_scan(watch_id)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_watch_folders.py`:

```python
import pytest


@pytest.mark.unit
def test_create_and_list(stax_db):
    wid = stax_db.create_watch_folder("/inbox", target_list_id=1, interval_sec=15)
    rows = stax_db.get_watch_folders()
    assert rows[0]["path"] == "/inbox"
    assert rows[0]["interval_sec"] == 15
    assert rows[0]["watch_id"] == wid


@pytest.mark.unit
def test_enabled_only_filter_and_update(stax_db):
    a = stax_db.create_watch_folder("/a", enabled=True)
    b = stax_db.create_watch_folder("/b", enabled=True)
    stax_db.update_watch_folder(b, enabled=0)
    enabled = stax_db.get_watch_folders(enabled_only=True)
    assert [r["path"] for r in enabled] == ["/a"]


@pytest.mark.unit
def test_delete(stax_db):
    wid = stax_db.create_watch_folder("/x")
    stax_db.delete_watch_folder(wid)
    assert stax_db.get_watch_folders() == []
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_watch_folders.py -v`
Expected: FAIL — methods/table missing.

- [ ] **Step 3: Implement schema + migration + CRUD**

Add the table (to `_create_schema` + migration):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watch_folders (
                watch_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                path           TEXT NOT NULL,
                target_list_id INTEGER,
                recipe_id      INTEGER,
                interval_sec   INTEGER NOT NULL DEFAULT 30,
                enabled        INTEGER NOT NULL DEFAULT 1,
                last_scan      TIMESTAMP
            )
        """)
```

Methods:

```python
    _WATCH_FIELDS = {"path", "target_list_id", "recipe_id", "interval_sec", "enabled"}

    def create_watch_folder(self, path, target_list_id=None, recipe_id=None,
                            interval_sec=30, enabled=True):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO watch_folders (path, target_list_id, recipe_id, interval_sec, enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                (path, target_list_id, recipe_id, interval_sec, 1 if enabled else 0))
            return cur.lastrowid

    def get_watch_folders(self, enabled_only=False):
        sql = "SELECT * FROM watch_folders"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY watch_id"
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def update_watch_folder(self, watch_id, **fields):
        updates = {k: v for k, v in fields.items() if k in self._WATCH_FIELDS}
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE watch_folders SET {} WHERE watch_id = ?".format(set_clause),
                list(updates.values()) + [watch_id])

    def delete_watch_folder(self, watch_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM watch_folders WHERE watch_id = ?", (watch_id,))

    def set_watch_last_scan(self, watch_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE watch_folders SET last_scan = CURRENT_TIMESTAMP WHERE watch_id = ?",
                (watch_id,))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep6_watch_folders.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep6_watch_folders.py
git commit -m "feat(ep6): add watch_folders table and CRUD"
```

---

## Task 6: Pure automation helpers module (`scan_folder`, recipe overlay, dup policy, preflight)

**Files:**
- Create: `src/ingest_automation.py`
- Test: `tests/unit/test_ep6_automation_helpers.py`

**Interfaces:**
- Produces (all pure, Qt-free): `MEDIA_EXTS` (frozenset), `scan_folder(path, seen, exts=None) -> (new_paths, updated_seen)`, `apply_recipe_to_config(recipe_values, base_config) -> dict`, `resolve_duplicate_action(policy, duplicates) -> str`, `run_preflight(paths, known_exts=None, duplicate_paths=None) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_automation_helpers.py`:

```python
import os
import pytest

from ingest_automation import (
    scan_folder, apply_recipe_to_config, resolve_duplicate_action, run_preflight,
)


@pytest.mark.unit
def test_scan_folder_detects_new_and_ignores_seen(tmp_path):
    (tmp_path / "a.exr").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")   # wrong ext, ignored
    new, seen = scan_folder(str(tmp_path), set(), exts={".exr"})
    assert [os.path.basename(p) for p in new] == ["a.exr"]
    # second pass: nothing new
    new2, seen2 = scan_folder(str(tmp_path), seen, exts={".exr"})
    assert new2 == []
    # add a file -> detected
    (tmp_path / "c.exr").write_bytes(b"x")
    new3, seen3 = scan_folder(str(tmp_path), seen2, exts={".exr"})
    assert [os.path.basename(p) for p in new3] == ["c.exr"]


@pytest.mark.unit
def test_apply_recipe_overlays_and_preserves_base():
    base = {"copy_policy": "soft", "preview_size": 512, "unrelated": 1}
    merged = apply_recipe_to_config({"copy_policy": "hard", "tags": "review"}, base)
    assert merged["copy_policy"] == "hard"
    assert merged["unrelated"] == 1
    assert merged["tags"] == "review"
    assert base["copy_policy"] == "soft"   # base not mutated


@pytest.mark.unit
def test_resolve_duplicate_action():
    assert resolve_duplicate_action("skip", []) == "allow"       # no dupes
    assert resolve_duplicate_action("skip", [{"element_id": 1}]) == "skip"
    assert resolve_duplicate_action("version", [{"element_id": 1}]) == "version"
    assert resolve_duplicate_action("bogus", [{"element_id": 1}]) == "allow"


@pytest.mark.unit
def test_run_preflight_flags_missing_empty_unknown(tmp_path):
    good = tmp_path / "g.exr"; good.write_bytes(b"data")
    empty = tmp_path / "e.exr"; empty.write_bytes(b"")
    weird = tmp_path / "w.xyz"; weird.write_bytes(b"data")
    issues = run_preflight(
        [str(good), str(empty), str(weird), str(tmp_path / "missing.exr")],
        known_exts={".exr"})
    codes = {i["code"] for i in issues}
    assert codes == {"empty", "unknown_ext", "missing"}
    assert all("path" in i and "level" in i for i in issues)
    # good file produced no issue
    assert run_preflight([str(good)], known_exts={".exr"}) == []
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_automation_helpers.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ingest_automation.py`:

```python
# -*- coding: utf-8 -*-
"""Pure, Qt-free ingest-automation helpers (EP6).

Kept free of Qt/DB imports so watch-folder diffing, recipe overlays, duplicate
policy resolution, preflight validation, proxy-profile mapping, and action-chain
dispatch are unit-testable in isolation (mirrors EP4's metadata_rules.py).
"""

import os
import logging

log = logging.getLogger(__name__)

MEDIA_EXTS = frozenset({
    ".exr", ".dpx", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".tga",
    ".mov", ".mp4", ".mxf", ".avi", ".mkv", ".abc", ".obj", ".fbx", ".glb",
})

DUP_POLICIES = ("allow", "skip", "version", "ask")


def scan_folder(path, seen, exts=None):
    """Non-recursive poll of `path`. Return (new_paths, updated_seen).

    A file is 'new' if its extension is in `exts` (default MEDIA_EXTS) and its
    absolute path is not already in `seen`. `seen` is not mutated; a fresh set
    is returned so callers persist it between polls.
    """
    exts = set(e.lower() for e in (exts or MEDIA_EXTS))
    updated = set(seen)
    new_paths = []
    try:
        entries = list(os.scandir(path))
    except (OSError, ValueError) as exc:
        log.debug("scan_folder: cannot scan %r: %s", path, exc)
        return [], updated
    for entry in sorted(entries, key=lambda e: e.name):
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in exts:
            continue
        full = os.path.abspath(entry.path)
        if full in updated:
            continue
        updated.add(full)
        new_paths.append(full)
    return new_paths, updated


def apply_recipe_to_config(recipe_values, base_config):
    """Return a NEW dict = base_config overlaid with the recipe's values."""
    merged = dict(base_config or {})
    for k, v in (recipe_values or {}).items():
        merged[k] = v
    return merged


def resolve_duplicate_action(policy, duplicates):
    """Return 'allow'|'skip'|'version'|'ask'. No duplicates => 'allow';
    unknown policy => 'allow'."""
    if not duplicates:
        return "allow"
    if policy not in DUP_POLICIES:
        return "allow"
    return policy


def run_preflight(paths, known_exts=None, duplicate_paths=None):
    """Validate `paths` before ingest. Return a list of issue dicts:
    {level: 'error'|'warning', code, path, message}."""
    known_exts = set(e.lower() for e in (known_exts or MEDIA_EXTS))
    duplicate_paths = set(duplicate_paths or ())
    issues = []
    for p in paths:
        if not os.path.exists(p):
            issues.append({"level": "error", "code": "missing", "path": p,
                           "message": "File does not exist"})
            continue
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        if size == 0:
            issues.append({"level": "error", "code": "empty", "path": p,
                           "message": "File is empty (0 bytes)"})
        if os.path.splitext(p)[1].lower() not in known_exts:
            issues.append({"level": "warning", "code": "unknown_ext", "path": p,
                           "message": "Unrecognized media extension"})
        if p in duplicate_paths:
            issues.append({"level": "warning", "code": "duplicate", "path": p,
                           "message": "Possible duplicate of an existing asset"})
    return issues
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep6_automation_helpers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ingest_automation.py tests/unit/test_ep6_automation_helpers.py
git commit -m "feat(ep6): pure automation helpers (scan/recipe/dup-policy/preflight)"
```

---

## Task 7: `ingest_recipes` table + CRUD

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep6_recipes.py`

**Interfaces:**
- Produces table `ingest_recipes` and: `create_ingest_recipe(name, values, sort_order=0) -> int`, `get_ingest_recipes() -> list[dict]` (parsed `values`), `update_ingest_recipe(recipe_id, **fields)` (accepts `values=` → re-serialized), `delete_ingest_recipe(recipe_id)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_recipes.py`:

```python
import pytest


@pytest.mark.unit
def test_create_and_parse_values(stax_db):
    rid = stax_db.create_ingest_recipe(
        "Plates", {"copy_policy": "hard", "duplicate_policy": "skip", "tags": "plate"})
    recipes = stax_db.get_ingest_recipes()
    assert recipes[0]["name"] == "Plates"
    assert recipes[0]["values"]["copy_policy"] == "hard"
    assert recipes[0]["recipe_id"] == rid


@pytest.mark.unit
def test_update_and_delete(stax_db):
    rid = stax_db.create_ingest_recipe("A", {"copy_policy": "soft"})
    stax_db.update_ingest_recipe(rid, name="B", values={"copy_policy": "hard"})
    r = stax_db.get_ingest_recipes()[0]
    assert r["name"] == "B" and r["values"]["copy_policy"] == "hard"
    stax_db.delete_ingest_recipe(rid)
    assert stax_db.get_ingest_recipes() == []
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_recipes.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement schema + migration + CRUD**

Add the table (to `_create_schema` + migration):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingest_recipes (
                recipe_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                values_json TEXT NOT NULL,
                sort_order  INTEGER NOT NULL DEFAULT 0
            )
        """)
```

Methods:

```python
    _RECIPE_FIELDS = {"name", "values_json", "sort_order"}

    def create_ingest_recipe(self, name, values, sort_order=0):
        import json
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ingest_recipes (name, values_json, sort_order) VALUES (?, ?, ?)",
                (name, json.dumps(values), sort_order))
            return cur.lastrowid

    def get_ingest_recipes(self):
        import json
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM ingest_recipes ORDER BY sort_order, name").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["values"] = json.loads(d["values_json"])
                out.append(d)
            return out

    def update_ingest_recipe(self, recipe_id, **fields):
        import json
        if "values" in fields:
            fields["values_json"] = json.dumps(fields.pop("values"))
        updates = {k: v for k, v in fields.items() if k in self._RECIPE_FIELDS}
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE ingest_recipes SET {} WHERE recipe_id = ?".format(set_clause),
                list(updates.values()) + [recipe_id])

    def delete_ingest_recipe(self, recipe_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM ingest_recipes WHERE recipe_id = ?", (recipe_id,))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep6_recipes.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep6_recipes.py
git commit -m "feat(ep6): add ingest_recipes table and CRUD"
```

---

## Task 8: `WatchFolderScanner(QThread)` + `PreflightDialog`

**Files:**
- Create: `src/watch_scanner.py`, `src/ui/preflight_dialog.py`
- Test: `tests/gui/test_ep6_watch_and_preflight.py`

**Interfaces:**
- Produces: `WatchFolderScanner(folders, exts=None, parent=None)` with `scan_once() -> list[(watch_id, [paths])]`, signals `files_detected(int, list)`, `stop()`; `PreflightDialog(issues, parent=None)` with `can_ingest() -> bool` (False when any `error`), `issues_table`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep6_watch_and_preflight.py`:

```python
import os
import pytest
from watch_scanner import WatchFolderScanner
from ui.preflight_dialog import PreflightDialog


@pytest.mark.gui
def test_scan_once_emits_new_files(qtbot, tmp_path):
    (tmp_path / "a.exr").write_bytes(b"x")
    folders = [{"watch_id": 1, "path": str(tmp_path), "recipe_id": None,
                "target_list_id": 2}]
    scanner = WatchFolderScanner(folders, exts={".exr"})
    detected = scanner.scan_once()
    assert detected and detected[0][0] == 1
    assert os.path.basename(detected[0][1][0]) == "a.exr"
    # second pass: nothing new
    assert scanner.scan_once() == []


@pytest.mark.gui
def test_preflight_dialog_blocks_on_error(qtbot):
    issues = [{"level": "error", "code": "missing", "path": "/x", "message": "gone"}]
    dlg = PreflightDialog(issues)
    qtbot.addWidget(dlg)
    assert dlg.can_ingest() is False
    assert dlg.issues_table.rowCount() == 1


@pytest.mark.gui
def test_preflight_dialog_allows_on_warning_only(qtbot):
    issues = [{"level": "warning", "code": "unknown_ext", "path": "/x.abc", "message": "?"}]
    dlg = PreflightDialog(issues)
    qtbot.addWidget(dlg)
    assert dlg.can_ingest() is True
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep6_watch_and_preflight.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement `src/watch_scanner.py`**

```python
# -*- coding: utf-8 -*-
"""Stdlib polling watch-folder scanner (EP6, F031). No watchdog dependency."""

import logging

from PySide2 import QtCore

from src.ingest_automation import scan_folder, MEDIA_EXTS

log = logging.getLogger(__name__)


class WatchFolderScanner(QtCore.QThread):
    """Polls configured folders on an interval and emits newly-seen files.

    `folders` is a list of dicts: {watch_id, path, recipe_id, target_list_id,
    interval_sec?}. Diffing is delegated to the pure `scan_folder`; this class
    only owns the per-folder 'seen' sets, the timer loop, and the signals.
    """

    files_detected = QtCore.Signal(int, list)   # (watch_id, [paths])
    scan_error     = QtCore.Signal(int, str)

    def __init__(self, folders, exts=None, interval_sec=30, parent=None):
        super(WatchFolderScanner, self).__init__(parent)
        self.folders = list(folders)
        self.exts = set(exts) if exts else set(MEDIA_EXTS)
        self.interval_sec = interval_sec
        self._seen = {}          # watch_id -> set(paths)
        self._stopped = False

    def scan_once(self):
        """Run one pass over all folders. Return [(watch_id, [new_paths]), ...]
        for folders that produced new files. Emits files_detected too."""
        results = []
        for wf in self.folders:
            wid = wf["watch_id"]
            seen = self._seen.get(wid, set())
            new_paths, updated = scan_folder(wf["path"], seen, exts=self.exts)
            self._seen[wid] = updated
            if new_paths:
                results.append((wid, new_paths))
                self.files_detected.emit(wid, new_paths)
        return results

    def run(self):
        self._stopped = False
        while not self._stopped:
            try:
                self.scan_once()
            except Exception as exc:              # noqa: BLE001
                log.exception("WatchFolderScanner pass failed")
                self.scan_error.emit(-1, str(exc))
            # sleep in cancellable slices
            slept = 0
            while slept < self.interval_sec * 1000 and not self._stopped:
                self.msleep(200)
                slept += 200

    def stop(self):
        self._stopped = True
```

- [ ] **Step 4: Implement `src/ui/preflight_dialog.py`**

```python
# -*- coding: utf-8 -*-
"""Preflight validation checklist dialog (EP6, F038)."""

from PySide2 import QtWidgets


class PreflightDialog(QtWidgets.QDialog):
    def __init__(self, issues, parent=None):
        super(PreflightDialog, self).__init__(parent)
        self.setWindowTitle("Preflight Check")
        self.issues = list(issues or [])
        layout = QtWidgets.QVBoxLayout(self)

        self.issues_table = QtWidgets.QTableWidget(len(self.issues), 3)
        self.issues_table.setHorizontalHeaderLabels(["Level", "File", "Message"])
        import os
        for r, issue in enumerate(self.issues):
            self.issues_table.setItem(r, 0, QtWidgets.QTableWidgetItem(issue.get("level", "")))
            self.issues_table.setItem(r, 1, QtWidgets.QTableWidgetItem(
                os.path.basename(issue.get("path", ""))))
            self.issues_table.setItem(r, 2, QtWidgets.QTableWidgetItem(issue.get("message", "")))
        layout.addWidget(self.issues_table)

        summary = "No issues." if not self.issues else "{} issue(s) found.".format(len(self.issues))
        layout.addWidget(QtWidgets.QLabel(summary))

        buttons = QtWidgets.QDialogButtonBox()
        self.ingest_button = buttons.addButton("Ingest", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        self.ingest_button.setEnabled(self.can_ingest())
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def can_ingest(self):
        """False when any blocking (error-level) issue is present."""
        return not any(i.get("level") == "error" for i in self.issues)
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep6_watch_and_preflight.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/watch_scanner.py src/ui/preflight_dialog.py tests/gui/test_ep6_watch_and_preflight.py
git commit -m "feat(ep6): polling WatchFolderScanner + PreflightDialog checklist"
```

---

# Cluster 6C — Proxy/transcode profiles + action chains

## Task 9: `proxy_profiles` table + seeded presets + config-overlay mapper

**Files:**
- Modify: `src/db_manager.py`, `src/ingest_automation.py`
- Test: `tests/unit/test_ep6_proxy_profiles.py`

**Interfaces:**
- Produces table `proxy_profiles` seeded with Low/Medium/High and: `create_proxy_profile(name, kind='mp4', max_size=512, fps=24, duration=None, sort_order=0) -> int`, `get_proxy_profiles() -> list[dict]`, `delete_proxy_profile(profile_id)`; and pure `ingest_automation.profile_to_config_overlay(profile) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_proxy_profiles.py`:

```python
import pytest
from ingest_automation import profile_to_config_overlay


@pytest.mark.unit
def test_seeded_presets_exist(stax_db):
    names = {p["name"] for p in stax_db.get_proxy_profiles()}
    assert {"Low", "Medium", "High"}.issubset(names)
    med = next(p for p in stax_db.get_proxy_profiles() if p["name"] == "Medium")
    assert med["max_size"] == 512 and med["is_default"] == 1


@pytest.mark.unit
def test_create_and_delete(stax_db):
    pid = stax_db.create_proxy_profile("Ultra", kind="mp4", max_size=2048, fps=30)
    assert any(p["name"] == "Ultra" for p in stax_db.get_proxy_profiles())
    stax_db.delete_proxy_profile(pid)
    assert not any(p["name"] == "Ultra" for p in stax_db.get_proxy_profiles())


@pytest.mark.unit
def test_profile_to_config_overlay_maps_sp2_keys():
    overlay = profile_to_config_overlay(
        {"kind": "mp4", "max_size": 1024, "fps": 30, "duration": 5})
    assert overlay["preview_size"] == 1024
    assert overlay["gif_size"] == 1024
    assert overlay["sequence_preview_fps"] == 30
    assert overlay["gif_fps"] == 30
    assert overlay["gif_duration"] == 5
    assert overlay["generate_video_previews"] is True
    # a thumbnail-only profile disables video
    assert profile_to_config_overlay(
        {"kind": "thumbnail", "max_size": 256, "fps": 24})["generate_video_previews"] is False
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_proxy_profiles.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement schema + seed + CRUD**

Add the table (to `_create_schema` + migration), then seed presets **only when empty**:

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proxy_profiles (
                profile_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                kind        TEXT NOT NULL DEFAULT 'mp4',
                max_size    INTEGER NOT NULL DEFAULT 512,
                fps         INTEGER NOT NULL DEFAULT 24,
                duration    INTEGER,
                is_default  INTEGER NOT NULL DEFAULT 0,
                sort_order  INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Seed default quality presets (F036) when the table is empty
        if cursor.execute("SELECT COUNT(*) FROM proxy_profiles").fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO proxy_profiles (name, kind, max_size, fps, is_default, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [("Low", "mp4", 256, 24, 0, 0),
                 ("Medium", "mp4", 512, 24, 1, 1),
                 ("High", "mp4", 1024, 24, 0, 2)])
```

> Place the seed inside `_create_schema` where the `cursor`/`conn` transaction is already open, matching how the module creates its other tables.

Methods:

```python
    def create_proxy_profile(self, name, kind="mp4", max_size=512, fps=24,
                             duration=None, sort_order=0):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO proxy_profiles (name, kind, max_size, fps, duration, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, kind, max_size, fps, duration, sort_order))
            return cur.lastrowid

    def get_proxy_profiles(self):
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM proxy_profiles ORDER BY sort_order, name").fetchall()]

    def delete_proxy_profile(self, profile_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM proxy_profiles WHERE profile_id = ?", (profile_id,))
```

- [ ] **Step 4: Implement the pure mapper in `src/ingest_automation.py`**

Append:

```python
def profile_to_config_overlay(profile):
    """Map a proxy/transcode profile row to the SP2 PreviewWorker config keys.

    Only keys PreviewWorker._process already reads are produced — no new
    ffmpeg knobs are invented. `kind == 'mp4'` enables video previews.
    """
    overlay = {}
    max_size = profile.get("max_size")
    if max_size:
        overlay["preview_size"] = int(max_size)
        overlay["gif_size"] = int(max_size)
    fps = profile.get("fps")
    if fps:
        overlay["sequence_preview_fps"] = int(fps)
        overlay["gif_fps"] = int(fps)
    if profile.get("duration") is not None:
        overlay["gif_duration"] = profile["duration"]
    overlay["generate_video_previews"] = (profile.get("kind") == "mp4")
    return overlay
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/unit/test_ep6_proxy_profiles.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_manager.py src/ingest_automation.py tests/unit/test_ep6_proxy_profiles.py
git commit -m "feat(ep6): proxy_profiles (seeded presets) + SP2 config-overlay mapper"
```

---

## Task 10: `action_chains` table + whitelisted executor

**Files:**
- Modify: `src/db_manager.py`, `src/ingest_automation.py`
- Test: `tests/unit/test_ep6_action_chains.py`

**Interfaces:**
- Produces table `action_chains` and: `create_action_chain(name, steps, sort_order=0) -> int`, `get_action_chains() -> list[dict]` (parsed `steps`), `delete_action_chain(chain_id)`; and pure `ingest_automation.run_action_chain(steps, context, handlers=None) -> list[dict]` + `BUILTIN_ACTIONS`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_action_chains.py`:

```python
import pytest
from ingest_automation import run_action_chain, BUILTIN_ACTIONS


@pytest.mark.unit
def test_chain_crud(stax_db):
    cid = stax_db.create_action_chain(
        "Review prep", [{"action": "add_tag", "params": {"tag": "review"}}])
    chains = stax_db.get_action_chains()
    assert chains[0]["name"] == "Review prep"
    assert chains[0]["steps"][0]["action"] == "add_tag"
    stax_db.delete_action_chain(cid)
    assert stax_db.get_action_chains() == []


@pytest.mark.unit
def test_run_action_chain_runs_known_in_order():
    calls = []
    handlers = {
        "one": lambda ctx, p: calls.append(("one", p.get("v"))) or "ok1",
        "two": lambda ctx, p: calls.append(("two", p.get("v"))) or "ok2",
    }
    steps = [{"action": "one", "params": {"v": 1}},
             {"action": "two", "params": {"v": 2}}]
    results = run_action_chain(steps, context={"element_id": 5}, handlers=handlers)
    assert calls == [("one", 1), ("two", 2)]
    assert [r["ok"] for r in results] == [True, True]


@pytest.mark.unit
def test_unknown_action_is_reported_not_executed():
    results = run_action_chain(
        [{"action": "danger_exec", "params": {}}], context={}, handlers={})
    assert results[0]["ok"] is False
    assert "unknown" in results[0]["message"].lower()


@pytest.mark.unit
def test_builtin_actions_are_registered():
    assert {"add_tag", "set_field", "move_to_list", "generate_proxy", "notify"} \
        <= set(BUILTIN_ACTIONS)
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep6_action_chains.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement schema + migration + CRUD**

Add the table (to `_create_schema` + migration):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_chains (
                chain_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                steps_json TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
```

Methods:

```python
    def create_action_chain(self, name, steps, sort_order=0):
        import json
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO action_chains (name, steps_json, sort_order) VALUES (?, ?, ?)",
                (name, json.dumps(steps), sort_order))
            return cur.lastrowid

    def get_action_chains(self):
        import json
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM action_chains ORDER BY sort_order, name").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["steps"] = json.loads(d["steps_json"])
                out.append(d)
            return out

    def delete_action_chain(self, chain_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM action_chains WHERE chain_id = ?", (chain_id,))
```

- [ ] **Step 4: Implement the executor in `src/ingest_automation.py`**

Append:

```python
# ---------------------------------------------------------------------------
# Whitelisted action-chain executor (F040). NEVER exec()/eval() — see C2.
# ---------------------------------------------------------------------------

def _action_add_tag(context, params):
    db, eid = context.get("db"), context.get("element_id")
    tag = params.get("tag")
    if db and eid and tag and hasattr(db, "add_tag_to_element"):
        db.add_tag_to_element(eid, tag)
    return "added tag {!r}".format(tag)


def _action_set_field(context, params):
    # EP4 seam: writes a custom metadata field when EP4's API is present.
    db, eid = context.get("db"), context.get("element_id")
    key, value = params.get("field_key"), params.get("value")
    if db and eid and key and hasattr(db, "set_element_metadata"):
        db.set_element_metadata(eid, key, value)
        return "set {}={!r}".format(key, value)
    return "set_field skipped (EP4 not available)"


def _action_move_to_list(context, params):
    db, eid = context.get("db"), context.get("element_id")
    list_id = params.get("list_id")
    if db and eid and list_id and hasattr(db, "move_element"):
        db.move_element(eid, list_id)
    return "moved to list {}".format(list_id)


def _action_generate_proxy(context, params):
    # Records intent; actual transcode runs via the PreviewWorker overlay.
    return "queued proxy profile {}".format(params.get("profile_id"))


def _action_notify(context, params):
    db = context.get("db")
    if db and hasattr(db, "add_notification"):
        db.add_notification(params.get("title", "Action chain"),
                            params.get("body"), level=params.get("level", "info"))
    return "notified"


BUILTIN_ACTIONS = {
    "add_tag": _action_add_tag,
    "set_field": _action_set_field,
    "move_to_list": _action_move_to_list,
    "generate_proxy": _action_generate_proxy,
    "notify": _action_notify,
}


def run_action_chain(steps, context, handlers=None):
    """Run an ordered list of {action, params} steps against a whitelist.

    Only actions present in `handlers` (default BUILTIN_ACTIONS) execute;
    unknown actions are reported as failed and NEVER evaluated. Returns a list
    of {action, ok, message}.
    """
    handlers = BUILTIN_ACTIONS if handlers is None else handlers
    results = []
    for step in (steps or []):
        action = step.get("action")
        params = step.get("params") or {}
        fn = handlers.get(action)
        if fn is None:
            results.append({"action": action, "ok": False, "message": "unknown action"})
            continue
        try:
            msg = fn(context, params)
            results.append({"action": action, "ok": True, "message": msg or ""})
        except Exception as exc:              # noqa: BLE001
            log.exception("action %r failed", action)
            results.append({"action": action, "ok": False, "message": str(exc)})
    return results
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/unit/test_ep6_action_chains.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_manager.py src/ingest_automation.py tests/unit/test_ep6_action_chains.py
git commit -m "feat(ep6): action_chains store + whitelisted executor (no exec)"
```

---

## Task 11: Automation settings tab (watch folders, recipes, proxy profiles, action chains)

**Files:**
- Modify: `src/ui/settings_panel.py`
- Test: `tests/gui/test_ep6_automation_settings.py`

**Interfaces:**
- Consumes: `get_watch_folders`/`create_watch_folder`/`delete_watch_folder`, `get_ingest_recipes`/`delete_ingest_recipe`, `get_proxy_profiles`, `get_action_chains`; `main_window.check_admin_permission`.
- Produces: `_build_automation_tab(self) -> QWidget` added via `self.tab_widget.addTab(tab, "Automation")`; tables `watch_table`, `recipes_table`, `profiles_table`, `chains_table`; add/delete controls disabled for non-admins.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep6_automation_settings.py`:

```python
import pytest


class _Main:
    def __init__(self, admin): self._a = admin
    def check_admin_permission(self): return self._a


@pytest.mark.gui
def test_automation_tab_lists_and_gates_admin(qtbot, stax_db):
    stax_db.create_watch_folder("/inbox", target_list_id=1)
    stax_db.create_ingest_recipe("Plates", {"copy_policy": "hard"})
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=None, db_manager=stax_db, main_window=_Main(admin=False))
    qtbot.addWidget(panel)
    assert panel.watch_table.rowCount() == 1
    assert panel.recipes_table.rowCount() == 1
    # seeded proxy presets show up
    assert panel.profiles_table.rowCount() >= 3
    assert panel.add_watch_button.isEnabled() is False


@pytest.mark.gui
def test_admin_can_delete_watch(qtbot, stax_db):
    wid = stax_db.create_watch_folder("/inbox")
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=None, db_manager=stax_db, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    panel.watch_table.selectRow(0)
    panel._on_delete_watch()
    assert stax_db.get_watch_folders() == []
```

> Match `SettingsPanel.__init__(config, db_manager, main_window=None, parent=None)` (`src/ui/settings_panel.py:20`) — `config` is positional-first; the test passes `config=None`.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep6_automation_settings.py -v`
Expected: FAIL — `watch_table` / `_build_automation_tab` missing.

- [ ] **Step 3: Implement the tab**

In `SettingsPanel.setup_ui`, after the existing `addTab` calls, add:

```python
        self.tab_widget.addTab(self._build_automation_tab(), "Automation")
```

Add the builder + helpers:

```python
    def _build_automation_tab(self):
        from PySide2 import QtWidgets
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        is_admin = bool(self.main_window.check_admin_permission()) if self.main_window else False

        layout.addWidget(QtWidgets.QLabel("Watch Folders"))
        self.watch_table = QtWidgets.QTableWidget(0, 3)
        self.watch_table.setHorizontalHeaderLabels(["Path", "Interval (s)", "Enabled"])
        layout.addWidget(self.watch_table)
        wrow = QtWidgets.QHBoxLayout()
        self.add_watch_button = QtWidgets.QPushButton("Add folder…")
        self.delete_watch_button = QtWidgets.QPushButton("Remove")
        wrow.addWidget(self.add_watch_button); wrow.addWidget(self.delete_watch_button)
        layout.addLayout(wrow)

        layout.addWidget(QtWidgets.QLabel("Ingest Recipes"))
        self.recipes_table = QtWidgets.QTableWidget(0, 1)
        self.recipes_table.setHorizontalHeaderLabels(["Name"])
        layout.addWidget(self.recipes_table)
        self.delete_recipe_button = QtWidgets.QPushButton("Delete recipe")
        layout.addWidget(self.delete_recipe_button)

        layout.addWidget(QtWidgets.QLabel("Proxy / Transcode Profiles"))
        self.profiles_table = QtWidgets.QTableWidget(0, 3)
        self.profiles_table.setHorizontalHeaderLabels(["Name", "Kind", "Max size"])
        layout.addWidget(self.profiles_table)

        layout.addWidget(QtWidgets.QLabel("Action Chains"))
        self.chains_table = QtWidgets.QTableWidget(0, 1)
        self.chains_table.setHorizontalHeaderLabels(["Name"])
        layout.addWidget(self.chains_table)

        self.add_watch_button.clicked.connect(self._on_add_watch)
        self.delete_watch_button.clicked.connect(self._on_delete_watch)
        self.delete_recipe_button.clicked.connect(self._on_delete_recipe)
        for b in (self.add_watch_button, self.delete_watch_button, self.delete_recipe_button):
            b.setEnabled(is_admin)

        self._reload_automation()
        return tab

    def _reload_automation(self):
        from PySide2 import QtWidgets
        watches = self.db.get_watch_folders()
        self.watch_table.setRowCount(len(watches))
        for r, w in enumerate(watches):
            self.watch_table.setItem(r, 0, QtWidgets.QTableWidgetItem(w["path"]))
            self.watch_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(w["interval_sec"])))
            self.watch_table.setItem(r, 2, QtWidgets.QTableWidgetItem(
                "yes" if w["enabled"] else "no"))
        recipes = self.db.get_ingest_recipes()
        self.recipes_table.setRowCount(len(recipes))
        for r, rec in enumerate(recipes):
            self.recipes_table.setItem(r, 0, QtWidgets.QTableWidgetItem(rec["name"]))
        profiles = self.db.get_proxy_profiles()
        self.profiles_table.setRowCount(len(profiles))
        for r, p in enumerate(profiles):
            self.profiles_table.setItem(r, 0, QtWidgets.QTableWidgetItem(p["name"]))
            self.profiles_table.setItem(r, 1, QtWidgets.QTableWidgetItem(p["kind"]))
            self.profiles_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(p["max_size"])))
        chains = self.db.get_action_chains()
        self.chains_table.setRowCount(len(chains))
        for r, c in enumerate(chains):
            self.chains_table.setItem(r, 0, QtWidgets.QTableWidgetItem(c["name"]))

    def _on_add_watch(self):
        from PySide2 import QtWidgets
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Watch Folder")
        if not path:
            return
        self.db.create_watch_folder(path)
        self._reload_automation()
        self.settings_changed.emit()

    def _on_delete_watch(self):
        row = self.watch_table.currentRow()
        watches = self.db.get_watch_folders()
        if 0 <= row < len(watches):
            self.db.delete_watch_folder(watches[row]["watch_id"])
            self._reload_automation()
            self.settings_changed.emit()

    def _on_delete_recipe(self):
        row = self.recipes_table.currentRow()
        recipes = self.db.get_ingest_recipes()
        if 0 <= row < len(recipes):
            self.db.delete_ingest_recipe(recipes[row]["recipe_id"])
            self._reload_automation()
            self.settings_changed.emit()
```

> `SettingsPanel` stores its DB handle as `self.db` (confirm the attribute name in the file — it is set from the `db_manager` arg in `__init__`; reuse whatever local name the existing tabs use).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep6_automation_settings.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/settings_panel.py tests/gui/test_ep6_automation_settings.py
git commit -m "feat(ep6): admin Automation settings tab (watch/recipes/profiles/chains)"
```

---

## Task 12: Ingest-path integration — recipe overlay, dup policy, action chain

**Files:**
- Modify: `src/ingestion_core.py`
- Test: `tests/unit/test_ep6_ingest_integration.py`

**Interfaces:**
- Consumes: `apply_recipe_to_config`, `resolve_duplicate_action`, `run_action_chain`; SP2's `find_duplicates`; EP4's `apply_template`/`add_relationship`.
- Produces: `ingest_file` honoring `config['duplicate_policy']` via `resolve_duplicate_action`, and running `config['action_chain_steps']` after a successful insert.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep6_ingest_integration.py`:

```python
import pytest

import ingest_automation


@pytest.mark.unit
def test_resolve_duplicate_action_used_by_policy():
    # Contract test: the resolver the ingest path calls behaves as ingest expects.
    assert ingest_automation.resolve_duplicate_action("skip", [{"element_id": 1}]) == "skip"
    assert ingest_automation.resolve_duplicate_action("allow", [{"element_id": 1}]) == "allow"


@pytest.mark.xfail(strict=True, reason="SP2: ingest_file duplicate + preview wiring")
@pytest.mark.unit
def test_ingest_file_skips_on_skip_policy(stax_db, stax_config, tiny_png, monkeypatch):
    from ingestion_core import IngestionCore
    import ingestion_core
    # Force a duplicate hit regardless of DB contents.
    monkeypatch.setattr(ingestion_core, "find_duplicates",
                        lambda db, phash, threshold=8: [{"element_id": 99}], raising=False)
    cfg = stax_config.get_all()
    cfg["dedup_enabled"] = True
    cfg["duplicate_policy"] = "skip"
    core = IngestionCore(stax_db, cfg)
    stack_id = stax_db.create_stack("S", str(tiny_png))
    list_id = stax_db.create_list(stack_id, "L")
    result = core.ingest_file(tiny_png, list_id, copy_policy="soft")
    assert result["success"] is False
    assert result.get("reason") == "duplicate_skipped"


@pytest.mark.xfail(strict=True, reason="EP4: action-chain set_field needs metadata API")
@pytest.mark.unit
def test_action_chain_runs_after_ingest(stax_db, stax_config, tiny_png):
    from ingestion_core import IngestionCore
    cfg = stax_config.get_all()
    cfg["action_chain_steps"] = [{"action": "add_tag", "params": {"tag": "auto"}}]
    core = IngestionCore(stax_db, cfg)
    stack_id = stax_db.create_stack("S", str(tiny_png))
    list_id = stax_db.create_list(stack_id, "L")
    result = core.ingest_file(tiny_png, list_id, copy_policy="soft")
    eid = result["element_id"]
    assert "auto" in (stax_db.get_element_by_id(eid).get("tags") or "")
```

- [ ] **Step 2: Run it to verify failure/xfail**

Run: `pytest tests/unit/test_ep6_ingest_integration.py -v`
Expected: 1 passed (the resolver contract), 2 xfailed (SP2/EP4 seams) — until those land.

- [ ] **Step 3: Implement the hooks in `src/ingestion_core.py`**

After the fileseq/preview imports (added by SP2), add:

```python
from src.ingest_automation import resolve_duplicate_action, run_action_chain
```

In `ingest_file`, where SP2 computes `dupes = find_duplicates(...)`, replace SP2's binary skip check with the policy resolver:

```python
            phash = None
            if self.config.get('dedup_enabled', True):
                phash = compute_phash(filepath_soft or source_path)
                if phash:
                    dupes = find_duplicates(
                        self.db, phash,
                        threshold=int(self.config.get('dedup_threshold', 8)))
                    action = resolve_duplicate_action(
                        self.config.get('duplicate_policy', 'ask'), dupes)
                    if action in ('skip', 'ask'):     # unattended 'ask' == skip
                        self.db.log_ingestion(
                            action='ingest', source_path=source_path,
                            target_list=target_list['name'], status='skipped',
                            message='Duplicate of element {}'.format(
                                dupes[0].get('element_id') if dupes else '?'))
                        return {'success': False, 'reason': 'duplicate_skipped',
                                'message': 'Skipped — duplicate of existing asset.'}
                    # 'version' / 'allow' fall through to normal ingest;
                    # 'version' links to the original when EP4 relationships exist.
                    self._pending_version_of = dupes[0].get('element_id') \
                        if (action == 'version' and dupes) else None
```

Immediately after the `PreviewJob` submission block (end of `ingest_file`), run the recipe's action chain:

```python
            # ---- Action chain (F040): whitelisted post-ingest steps ----
            steps = self.config.get('action_chain_steps')
            if steps:
                run_action_chain(steps, context={
                    'db': self.db, 'element_id': element_id, 'config': self.config})

            # ---- Version-link to the duplicate original (EP4 seam) ----
            if getattr(self, '_pending_version_of', None) and hasattr(self.db, 'add_relationship'):
                try:
                    self.db.add_relationship(element_id, self._pending_version_of, 'variant_of')
                except Exception as exc:
                    log.debug("version relationship failed: %s", exc)
                self._pending_version_of = None
```

> The recipe overlay itself is applied *before* `IngestionCore` is constructed: `IngestWorker` receives `apply_recipe_to_config(recipe['values'], config.get_all())` as its config dict (Task 13 wiring). `ingest_file` therefore only reads `duplicate_policy` / `action_chain_steps` from `self.config`.

- [ ] **Step 4: Run to verify (1 pass, 2 xfail)**

Run: `pytest tests/unit/test_ep6_ingest_integration.py -v`
Expected: 1 passed, 2 xfailed. If SP2/EP4 are already merged in this worktree, remove the corresponding `@pytest.mark.xfail` and expect PASS — never weaken the assertion.

- [ ] **Step 5: Commit**

```bash
git add src/ingestion_core.py tests/unit/test_ep6_ingest_integration.py
git commit -m "feat(ep6): ingest_file honors duplicate policy + runs action chain"
```

---

## Task 13: Watch-scanner + recipe-picker wiring (main.py) and full-suite run

**Files:**
- Modify: `main.py`, the ingest dialog (`src/ui/ingest_library_dialog.py`)
- Test: `tests/gui/test_ep6_watch_wiring.py`

**Interfaces:**
- Consumes: `WatchFolderScanner`, `get_watch_folders`, `get_ingest_recipes`, `apply_recipe_to_config`, `IngestWorker`, `_record_ingest_jobs`.
- Produces: `_start_watch_scanner()` / `_stop_watch_scanner()`; `_on_watched_files(watch_id, paths)` that records jobs and starts an `IngestWorker` with the folder's recipe overlay; a recipe combo in the ingest dialog.

- [ ] **Step 1: Write the failing test (scanner lifecycle, worker-independent)**

Create `tests/gui/test_ep6_watch_wiring.py`:

```python
import pytest


@pytest.mark.gui
def test_start_watch_scanner_builds_from_enabled_rows(qtbot, stax_db, stax_config, mock_nuke):
    stax_db.create_watch_folder("/inbox", enabled=True)
    stax_db.create_watch_folder("/off", enabled=False)
    from main import MainWindow
    win = MainWindow(stax_config, stax_db)
    qtbot.addWidget(win)
    win._start_watch_scanner()
    assert win._watch_scanner is not None
    assert [f["path"] for f in win._watch_scanner.folders] == ["/inbox"]
    win._stop_watch_scanner()


@pytest.mark.gui
def test_on_watched_files_records_jobs(qtbot, stax_db, stax_config, mock_nuke, tmp_path):
    f = tmp_path / "a.exr"; f.write_bytes(b"x")
    wid = stax_db.create_watch_folder(str(tmp_path), target_list_id=4)
    from main import MainWindow
    win = MainWindow(stax_config, stax_db)
    qtbot.addWidget(win)
    win._on_watched_files(wid, [str(f)])
    pending = stax_db.get_jobs(status="pending")
    assert pending and pending[0]["target_list_id"] == 4
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep6_watch_wiring.py -v`
Expected: FAIL — `_start_watch_scanner` / `_on_watched_files` missing.

- [ ] **Step 3: Implement the scanner lifecycle in `main.py`**

Add near the other imports:

```python
from src.watch_scanner import WatchFolderScanner
from src.ingest_automation import apply_recipe_to_config
```

Add methods:

```python
    def _start_watch_scanner(self):
        rows = self.db.get_watch_folders(enabled_only=True)
        if not rows:
            self._watch_scanner = None
            return
        interval = min((r["interval_sec"] for r in rows), default=30)
        self._watch_scanner = WatchFolderScanner(rows, interval_sec=interval)
        self._watch_scanner.files_detected.connect(self._on_watched_files)
        self._watch_scanner.start()

    def _stop_watch_scanner(self):
        scanner = getattr(self, "_watch_scanner", None)
        if scanner is not None:
            scanner.stop()
            scanner.wait(2000)
        self._watch_scanner = None

    def _on_watched_files(self, watch_id, paths):
        """Record ledger rows for detected files and ingest them off-thread."""
        from src.ingest_worker import IngestWorker
        row = next((r for r in self.db.get_watch_folders() if r["watch_id"] == watch_id), None)
        if not row:
            return
        target = row.get("target_list_id")
        self._record_ingest_jobs(paths, target, recipe_id=row.get("recipe_id"))
        config = self.config.get_all()
        if row.get("recipe_id"):
            recipe = next((rc for rc in self.db.get_ingest_recipes()
                           if rc["recipe_id"] == row["recipe_id"]), None)
            if recipe:
                config = apply_recipe_to_config(recipe["values"], config)
        jobs = [(p, target) for p in paths]
        worker = IngestWorker(self.db, config, jobs,
                              copy_policy=config.get("default_copy_policy", "soft"))
        self._watch_ingest_worker = worker
        worker.file_done.connect(self._on_job_file_done)
        worker.ingest_finished.connect(self._on_ingest_finished_notify)
        worker.start()
```

Call `self._start_watch_scanner()` at the end of `__init__` (after `_start_api_server`) and `self._stop_watch_scanner()` in `closeEvent` (next to `shutdown_preview_queue()`).

- [ ] **Step 4: Add the recipe picker to the ingest dialog**

In `src/ui/ingest_library_dialog.py` (near the copy-policy combo), add a recipe combo and apply the overlay when building the `IngestWorker`'s config:

```python
        self.recipe_combo = QtWidgets.QComboBox()
        self.recipe_combo.addItem("(none)", None)
        for rec in self.db.get_ingest_recipes():
            self.recipe_combo.addItem(rec["name"], rec)
```

Where the dialog builds `config_dict` for its `IngestWorker` (per the SP2 plan's `start_ingestion`), overlay the chosen recipe:

```python
        from src.ingest_automation import apply_recipe_to_config
        recipe = self.recipe_combo.currentData()
        if recipe:
            config_dict = apply_recipe_to_config(recipe["values"], config_dict)
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep6_watch_wiring.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full EP6 suite**

Run: `pytest -m "not manual" -k ep6 -v`
Expected: all EP6 unit + gui tests pass; the SP2/EP4 integration tests report `xfail` (not fail).

- [ ] **Step 7: Commit**

```bash
git add main.py src/ui/ingest_library_dialog.py tests/gui/test_ep6_watch_wiring.py
git commit -m "feat(ep6): watch-scanner lifecycle + recipe picker wiring"
```

---

## Self-Review

**1. Spec coverage:**
- Watch folders (F031) → `watch_folders` CRUD Task 5, pure `scan_folder` Task 6, `WatchFolderScanner` Task 8, lifecycle wiring Task 13 ✓
- Ingest recipes (F032) → `ingest_recipes` CRUD Task 7, `apply_recipe_to_config` Task 6, picker Task 13, manager Task 11 ✓
- Central job-queue dashboard (F033) → `ingest_jobs` Task 1, `JobQueueDashboard` Task 3, wiring Task 4 ✓
- Retry failed jobs (F034) → `retry_requested`/`_retry_job` Task 3+4 ✓
- Background transcode profiles (F035) + proxy quality presets (F036) → `proxy_profiles` seeded + `profile_to_config_overlay` Task 9 ✓
- Auto duplicate policies (F037) → `resolve_duplicate_action` Task 6, ingest wiring Task 12 ✓
- Preflight checklist (F038) → `run_preflight` Task 6, `PreflightDialog` Task 8 ✓
- Ingest completion notifications (F039) → `notifications` Task 2, `_on_ingest_finished_notify` Task 4 ✓
- Scriptable action chains (F040) → `action_chains` + `run_action_chain` Task 10, ingest wiring Task 12, manager Task 11 ✓
- Unit + headless GUI tests → every task ✓; SP2/EP4 seams `xfail(strict)` with the dependency id (Tasks 4, 12) ✓

**2. Placeholder scan:** New units — job/notification/watch/recipe/profile/chain CRUD (Tasks 1, 2, 5, 7, 9, 10), all pure helpers (Task 6, 9, 10), `JobQueueDashboard` (Task 3), `WatchFolderScanner`/`PreflightDialog` (Task 8) — have complete code. Integration tasks (4, 11, 12, 13) give complete new-method code plus concrete wiring snippets anchored to verified seams (`main.py:252` dock pattern, `:527` admin gate, `:714` `perform_ingestion`, SP2 `IngestWorker` signals, `SettingsPanel(config, db_manager, ...)` `:20`), naming the exact reuse points rather than leaving them open.

**3. Type consistency:** `create_job`/`get_jobs`/`update_job_status`/`bump_job_attempt`/`clear_finished_jobs` (Task 1) are consumed identically in Tasks 3, 4, 13. `JobQueueDashboard.refresh`/`retry_requested`/`cancel_requested` (Task 3) match Task 4. `add_notification`/`unread_notification_count` (Task 2) match Task 4. `scan_folder(path, seen, exts) -> (list, set)` (Task 6) is consumed by `WatchFolderScanner.scan_once` (Task 8) with identical shape. `apply_recipe_to_config(recipe_values, base_config) -> dict` (Task 6) is consumed in Task 13 with `recipe["values"]` from `get_ingest_recipes` (Task 7). `resolve_duplicate_action(policy, duplicates)` (Task 6) is consumed in Task 12. `profile_to_config_overlay(profile)` (Task 9) produces only SP2 `PreviewWorker` config keys. `run_action_chain(steps, context, handlers)` + `BUILTIN_ACTIONS` (Task 10) are consumed in Task 12. Recipe `values` dicts flow unchanged from CRUD (Task 7) → overlay (Task 6) → ingest (Task 12/13).

**Note for the executor:** EP6 assumes SP1 (+ SP2 for the live worker, EP4 for templates/relationships) have landed. If running before SP1, drop the `write=` kwarg on `get_connection`. Tasks 4, 12, 13 wiring reuses SP2's `IngestWorker` and `main.py`/`ingest_library_dialog.py` entry points — read those files for the exact local names (`self.db` vs `self.db_manager`, the real `perform_ingestion`/`start_ingestion` bodies after SP2's refactor) before editing, and adjust reuse calls to the real names. Where SP2's `IngestWorker` or EP4's `apply_template`/`add_relationship`/`set_element_metadata` are genuinely absent, keep the integration test `xfail(strict=True)` tagged with the dependency id — never weaken an assertion to make CI pass.
