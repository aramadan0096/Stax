# EP9 — Analytics & Ops Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three dashboards whose data already exists — **top-used assets** (F059, off SP1's `insertion_log`), **search success analytics** (F060, from a new `search_events` table), and **storage hygiene & duplicate savings** (F063, from `elements.file_size` + SP1's `elements.phash`) — by extending the existing `AnalyticsPanel` and its dependency-free `_BarChart`. No plotting libraries, no placeholder panels.

**Architecture:** All stats are computed by new `DatabaseManager` read methods over the live lowercase schema (unit-testable without Qt). `AnalyticsPanel` gains a **Search** tab and a **Storage** tab that call those methods and render with the existing `_BarChart` + `QTableWidget`; each dashboard exports CSV following the panel's existing `_export_csv` pattern. Searches are instrumented with a `log_search_event(query, result_count, user)` write from `MediaDisplayWidget`. F059's dashboards already exist and are delivered by SP1; EP9 verifies them with a headless render test.

**Tech Stack:** Python 3.9, SQLite (via `DatabaseManager`), PySide2 (headless offscreen), pytest / pytest-qt, stdlib `csv`. No new dependencies.

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat. **Logging:** `logging`, not `print`. **Commits:** conventional.
- **No new dependencies.** Reuse `_BarChart` + `QTableWidget`; no matplotlib/plotly/pyqtgraph.
- **No dead panels.** Build only F059, F060, F063. F061 (needs EP6 job queue), F062 (needs EP5 review), F064 (low priority) are deferred — do **not** add placeholder tabs.
- **All stat computation lives in `DatabaseManager`**; the panel is a thin view. Every dashboard has a CSV export.
- **Analytics must never break the app.** `log_search_event` and `_log_search` are `try/except`-guarded.
- **Dependency — SP1 (hard):** `get_connection(write=True|False)`, the versioned migration runner, the lowercase `insertion_log` table, `elements.phash`, and the four real analytics reads (`get_top_inserted_elements`, `get_insertions_by_month`, `get_insertions_by_user`, `get_total_insertions`). **EP9 assumes SP1 has landed** — these return real data. If executing before SP1, drop the `write=` kwarg (plain `get_connection()`) and `xfail(strict=True)` the F059/dup-savings tests with the SP1 id.
- **Dependency — EP2 (soft):** the search entry point (`run_text_search` / `on_search`) and `self.user_name` on `MediaDisplayWidget` are where instrumentation hooks. EP9's `_log_search` helper and DB stats are independently testable.
- New stat methods go on `DatabaseManager`; new tabs extend the existing `AnalyticsPanel` (single file).

---

## Key facts (verified against the codebase)

- `AnalyticsPanel` (`src/ui/analytics_panel.py:155`) already has tabs Top Assets / Details / Over Time / By User, a `refresh()` that calls `get_top_inserted_elements(n)` / `get_insertions_by_month()` / `get_insertions_by_user()` / `get_total_insertions()`, a `_BarChart` (`:89`), and an `_export_csv` (`:334`). Qt classes are guarded behind `_QT_AVAILABLE`; headless stubs live in the `else` branch (`:369`).
- `log_insertion(db, element_id, user_id=None, project="", host="")` (`src/ui/analytics_panel.py:51`) is the pure-Python insertion-log writer SP1 repoints to the lowercase `insertion_log` table.
- SP1 creates `insertion_log(log_id, element_fk, user_fk, inserted_at, project, host, context)` and `elements.phash TEXT` (`docs/superpowers/plans/2026-07-22-sp1-database-consolidation.md:154,145`).
- SP1's `get_top_inserted_elements(n)` returns dict keys `element_id, name, list_name, format, type, count` (`sp1 plan:348`).
- `elements` has `file_size INTEGER`, `is_hard_copy BOOLEAN`, `is_deprecated BOOLEAN`, and (post-SP1) `phash TEXT` (`src/db_manager.py:223,232,233`).
- DB write idiom: `with self.get_connection(write=True) as conn: cur = conn.cursor(); ...`; reads use `write=False` (SP1 Task 6).
- Schema tables are created in `_create_schema` (`src/db_manager.py:183`) with `CREATE TABLE IF NOT EXISTS`, mirrored idempotently in `_apply_migrations` (`:359`). EP2 added `recent_searches`/`saved_searches`/`smart_collections` this way.
- EP2's `recent_searches(recent_id, user_name, query_text, ran_at)` has **no** result count — insufficient for success-rate; EP9 adds `search_events`.
- `MediaDisplayWidget.__init__(self, db_manager, config, nuke_bridge, main_window=None, parent=None)` (`src/ui/media_display_widget.py:24`); `self.db` at `:26`; search handler `on_search` at `:546`; EP2 adds `run_text_search` + `self.user_name`.
- `duplicate_detection` clusters by phash Hamming distance; distance-0 clusters == exact phash equality (`src/duplicate_detection.py:105,151`).
- SP0 fixtures: `stax_db` (real `DatabaseManager` on temp DB), `stax_config`, `mock_nuke`, headless offscreen Qt.

---

# Cluster 9A — Search success analytics (F060)

## Task 1: `search_events` table + success/zero-result stats

**Files:**
- Modify: `src/db_manager.py` (schema + migration + methods)
- Test: `tests/unit/test_ep9_search_stats.py`

**Interfaces:**
- Produces table `search_events` and: `log_search_event(query, result_count, user_name=None) -> int`, `get_search_success_stats() -> dict` (keys `total, zero_result, success, success_rate, zero_result_rate`), `get_zero_result_queries(limit=20) -> list[dict]` (keys `query_text, count`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep9_search_stats.py`:

```python
import pytest


@pytest.mark.unit
def test_success_stats_computed(stax_db):
    stax_db.log_search_event("fire", 5, "alice")
    stax_db.log_search_event("water", 3, "alice")
    stax_db.log_search_event("zzzzz", 0, "bob")
    stax_db.log_search_event("qqqqq", 0, "bob")
    stats = stax_db.get_search_success_stats()
    assert stats["total"] == 4
    assert stats["zero_result"] == 2
    assert stats["success"] == 2
    assert stats["success_rate"] == 0.5
    assert stats["zero_result_rate"] == 0.5


@pytest.mark.unit
def test_success_stats_empty_db_is_zero(stax_db):
    stats = stax_db.get_search_success_stats()
    assert stats["total"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["zero_result_rate"] == 0.0


@pytest.mark.unit
def test_zero_result_queries_grouped_by_frequency(stax_db):
    for _ in range(3):
        stax_db.log_search_event("greenscreen", 0, "alice")
    stax_db.log_search_event("hologram", 0, "bob")
    stax_db.log_search_event("fire", 9, "bob")   # a hit — excluded
    rows = stax_db.get_zero_result_queries(limit=10)
    assert [r["query_text"] for r in rows] == ["greenscreen", "hologram"]
    assert rows[0]["count"] == 3
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep9_search_stats.py -v`
Expected: FAIL — `log_search_event` / `get_search_success_stats` not defined.

- [ ] **Step 3: Implement schema + migration + methods**

Add the table to `_create_schema` and mirror it in the idempotent `_apply_migrations` block (EP2 pattern):

```python
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_events (
                    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name    TEXT,
                    query_text   TEXT NOT NULL,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    ran_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_search_events_zero ON search_events(result_count)")
```

Add methods to `DatabaseManager`:

```python
    def log_search_event(self, query, result_count, user_name=None):
        """Record one search and its result count (EP9 F060). Never raises into the caller."""
        try:
            with self.get_connection(write=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO search_events (user_name, query_text, result_count) "
                    "VALUES (?, ?, ?)",
                    (user_name, (query or "").strip(), int(result_count or 0)))
                return cur.lastrowid
        except Exception:
            log.warning("Could not log search event", exc_info=True)
            return None

    def get_search_success_stats(self):
        """Aggregate search success. success_rate/zero_result_rate are fractions in [0,1]."""
        with self.get_connection(write=False) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) AS zero "
                "FROM search_events").fetchone()
        total = row["total"] or 0
        zero = row["zero"] or 0
        success = total - zero
        return {
            "total": total,
            "zero_result": zero,
            "success": success,
            "success_rate": (success / total) if total else 0.0,
            "zero_result_rate": (zero / total) if total else 0.0,
        }

    def get_zero_result_queries(self, limit=20):
        """Top zero-result queries, most frequent first (EP9 F060)."""
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT query_text, COUNT(*) AS count FROM search_events "
                "WHERE result_count = 0 AND query_text != '' "
                "GROUP BY query_text ORDER BY count DESC, query_text LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
```

> `log` is the module logger already defined at the top of `db_manager.py`; if the module uses a different name (e.g. `logger`/`self._log`), match it.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep9_search_stats.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep9_search_stats.py
git commit -m "feat(ep9): add search_events table and success/zero-result stats"
```

---

## Task 2: Instrument the search path

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep9_search_instrument.py`

**Interfaces:**
- Consumes: `log_search_event`.
- Produces: `MediaDisplayWidget._log_search(self, text, result_count)` — guarded call to `self.db.log_search_event(text, result_count, self.user_name)`; invoked from the existing search entry point once the result count is known.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep9_search_instrument.py`:

```python
import pytest


@pytest.mark.gui
def test_log_search_writes_event(qtbot, stax_db, stax_config, mock_nuke):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, mock_nuke)
    qtbot.addWidget(w)
    w._log_search("fire", 3)
    assert stax_db.get_search_success_stats()["total"] == 1


@pytest.mark.gui
def test_log_search_skips_empty_query(qtbot, stax_db, stax_config, mock_nuke):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db, stax_config, mock_nuke)
    qtbot.addWidget(w)
    w._log_search("   ", 0)
    assert stax_db.get_search_success_stats()["total"] == 0
```

> Match the real `MediaDisplayWidget.__init__(db_manager, config, nuke_bridge, ...)` signature (`:24`). Use the SP0 `stax_config`/`mock_nuke` fixtures.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep9_search_instrument.py -v`
Expected: FAIL — `_log_search` not defined.

- [ ] **Step 3: Implement**

Add to `MediaDisplayWidget`:

```python
    def _log_search(self, text, result_count):
        """Record a search for EP9 analytics. Never breaks the search itself."""
        query = (text or "").strip()
        if not query:
            return
        try:
            user = getattr(self, "user_name", None)
            self.db.log_search_event(query, result_count, user)
        except Exception:
            logger.exception("search event logging failed")
```

> Use the module's existing logger name (`logger`/`log`); match what `media_display_widget.py` already imports. If the widget has no `self.user_name` yet (pre-EP2), `getattr` yields `None`, which `search_events.user_name` accepts.

Wire one call at the existing search entry point. For EP2's `run_text_search` (preferred), after `count = self.db.count_elements_advanced(spec)`:

```python
        self._log_search(text, count)
```

If EP2 has not landed, add it to `on_search` (`:546`) after the result set is built, using the tag-search result length:

```python
        self._log_search(text, len(elements))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep9_search_instrument.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep9_search_instrument.py
git commit -m "feat(ep9): instrument search path with log_search_event"
```

---

## Task 3: Search dashboard tab + CSV export

**Files:**
- Modify: `src/ui/analytics_panel.py`
- Test: `tests/gui/test_ep9_search_tab.py`

**Interfaces:**
- Consumes: `get_search_success_stats`, `get_zero_result_queries`.
- Produces: a **Search** tab with `self._search_summary` (QLabel) and `self._zero_table` (QTableWidget); `_load_search()` called from `refresh()`; `_export_search_csv()`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep9_search_tab.py`:

```python
import pytest


@pytest.mark.gui
def test_search_tab_shows_success_and_failures(qtbot, stax_db):
    stax_db.log_search_event("fire", 5, "alice")
    stax_db.log_search_event("zzzzz", 0, "bob")
    from ui.analytics_panel import AnalyticsPanel
    panel = AnalyticsPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    assert "50" in panel._search_summary.text()        # 50% success
    assert panel._zero_table.rowCount() == 1
    assert panel._zero_table.item(0, 0).text() == "zzzzz"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep9_search_tab.py -v`
Expected: FAIL — `_search_summary` / Search tab missing.

- [ ] **Step 3: Implement**

In `AnalyticsPanel._setup_ui`, after the "By User" tab is added (before `self._total_label`), add the Search tab:

```python
            # Tab 5 — search success (EP9 F060)
            tab_search = QtWidgets.QWidget()
            tls = QtWidgets.QVBoxLayout(tab_search)
            self._search_summary = QtWidgets.QLabel("No search data yet.")
            self._search_summary.setTextFormat(QtCore.Qt.RichText)
            tls.addWidget(self._search_summary)
            tls.addWidget(QtWidgets.QLabel("<b>Top failing searches</b> (zero results)"))
            self._zero_table = QtWidgets.QTableWidget(0, 2)
            self._zero_table.setHorizontalHeaderLabels(["Query", "Count"])
            self._zero_table.horizontalHeader().setStretchLastSection(True)
            self._zero_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self._zero_table.verticalHeader().hide()
            tls.addWidget(self._zero_table)
            export_search_btn = QtWidgets.QPushButton("Export CSV…")
            export_search_btn.clicked.connect(self._export_search_csv)
            tls.addWidget(export_search_btn)
            tabs.addTab(tab_search, "Search")
```

Add `self._load_search()` to `refresh()`:

```python
        def refresh(self):
            n = self._n_spin.value()
            self._load_top_assets(n)
            self._load_over_time()
            self._load_by_user()
            self._load_search()
            self._load_total()
```

Add the loader + export:

```python
        def _load_search(self):
            try:
                stats = self.db.get_search_success_stats()
                zeros = self.db.get_zero_result_queries(self._n_spin.value())
            except Exception as exc:
                log.warning("Analytics search: %s", exc)
                stats, zeros = {"total": 0, "success_rate": 0.0, "zero_result_rate": 0.0}, []
            self._search_summary.setText(
                "Searches: <b>{}</b> &nbsp;·&nbsp; Success: <b>{:.0f}%</b> "
                "&nbsp;·&nbsp; Zero-result: <b>{:.0f}%</b>".format(
                    stats.get("total", 0),
                    stats.get("success_rate", 0.0) * 100,
                    stats.get("zero_result_rate", 0.0) * 100))
            self._zero_table.setRowCount(len(zeros))
            for i, row in enumerate(zeros):
                self._zero_table.setItem(i, 0, QtWidgets.QTableWidgetItem(row.get("query_text", "")))
                cnt = QtWidgets.QTableWidgetItem(str(row.get("count", 0)))
                cnt.setTextAlignment(QtCore.Qt.AlignCenter)
                self._zero_table.setItem(i, 1, cnt)
            self._zero_table.resizeColumnsToContents()

        def _export_search_csv(self):
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Search Analytics CSV", "stax_search_analytics.csv",
                "CSV files (*.csv)")
            if not path:
                return
            try:
                stats = self.db.get_search_success_stats()
                zeros = self.db.get_zero_result_queries(1000)
                with open(path, "w", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["metric", "value"])
                    for k in ("total", "success", "zero_result",
                              "success_rate", "zero_result_rate"):
                        writer.writerow([k, stats.get(k, 0)])
                    writer.writerow([])
                    writer.writerow(["zero_result_query", "count"])
                    for row in zeros:
                        writer.writerow([row.get("query_text", ""), row.get("count", 0)])
                QtWidgets.QMessageBox.information(
                    self, "Exported", "Search analytics exported to:\n{}".format(path))
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Export Failed", "Could not write CSV:\n{}".format(exc))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep9_search_tab.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/analytics_panel.py tests/gui/test_ep9_search_tab.py
git commit -m "feat(ep9): add Search analytics tab with success rate + CSV export"
```

---

# Cluster 9B — Storage hygiene & duplicate savings (F063)

## Task 4: `get_storage_stats` + `get_duplicate_stats`

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep9_storage_stats.py`

**Interfaces:**
- Produces: `get_storage_stats() -> dict` (keys `element_count, total_bytes, hard_copy_bytes, hard_copy_count, soft_copy_count, deprecated_count, deprecated_bytes`) and `get_duplicate_stats() -> dict` (keys `cluster_count, duplicate_count, reclaimable_bytes`). Reads only; no new tables. Depends on SP1's `elements.phash`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep9_storage_stats.py`:

```python
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        rows = [
            # name, file_size, is_hard_copy, is_deprecated, phash
            ("a", 1000, 1, 0, "hhhh"),
            ("b",  800, 1, 0, "hhhh"),   # dup of a (same phash)
            ("c",  600, 0, 0, "hhhh"),   # dup of a (same phash)
            ("d",  500, 0, 1, "zzzz"),   # deprecated, unique phash
            ("e",  400, 0, 0, None),     # no phash
        ]
        for name, size, hard, dep, phash in rows:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, file_size, is_hard_copy, "
                "is_deprecated, phash) VALUES (1, ?, '2D', ?, ?, ?, ?)",
                (name, size, hard, dep, phash))


@pytest.mark.unit
def test_storage_stats(stax_db):
    _seed(stax_db)
    s = stax_db.get_storage_stats()
    assert s["element_count"] == 5
    assert s["total_bytes"] == 3300
    assert s["hard_copy_count"] == 2
    assert s["soft_copy_count"] == 3
    assert s["deprecated_count"] == 1
    assert s["deprecated_bytes"] == 500


@pytest.mark.unit
def test_duplicate_stats_exact_phash_cluster(stax_db):
    _seed(stax_db)
    d = stax_db.get_duplicate_stats()
    # cluster "hhhh" has a(1000), b(800), c(600): keep largest 1000, reclaim 1400
    assert d["cluster_count"] == 1
    assert d["duplicate_count"] == 2
    assert d["reclaimable_bytes"] == 1400
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep9_storage_stats.py -v`
Expected: FAIL — `get_storage_stats` / `get_duplicate_stats` not defined. (If it errors on `phash` not existing, SP1 has not landed — `xfail(strict=True)` with the SP1 id.)

- [ ] **Step 3: Implement**

Add to `DatabaseManager`:

```python
    def get_storage_stats(self):
        """Repository size + hard/soft/deprecated breakdown (EP9 F063). Bytes coerce NULL to 0."""
        with self.get_connection(write=False) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS element_count, "
                "COALESCE(SUM(file_size), 0) AS total_bytes, "
                "COALESCE(SUM(CASE WHEN is_hard_copy = 1 THEN file_size ELSE 0 END), 0) "
                "    AS hard_copy_bytes, "
                "SUM(CASE WHEN is_hard_copy = 1 THEN 1 ELSE 0 END) AS hard_copy_count, "
                "SUM(CASE WHEN is_hard_copy = 0 THEN 1 ELSE 0 END) AS soft_copy_count, "
                "SUM(CASE WHEN is_deprecated = 1 THEN 1 ELSE 0 END) AS deprecated_count, "
                "COALESCE(SUM(CASE WHEN is_deprecated = 1 THEN file_size ELSE 0 END), 0) "
                "    AS deprecated_bytes "
                "FROM elements").fetchone()
            return {k: (row[k] or 0) for k in row.keys()}

    def get_duplicate_stats(self):
        """Duplicate clusters (exact phash) + reclaimable bytes (EP9 F063).

        Per cluster of size > 1: keep the largest copy, reclaim the rest.
        Depends on SP1's elements.phash column.
        """
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT phash, file_size FROM elements "
                "WHERE phash IS NOT NULL AND phash != ''").fetchall()
        clusters = {}
        for r in rows:
            clusters.setdefault(r["phash"], []).append(r["file_size"] or 0)
        cluster_count = duplicate_count = reclaimable_bytes = 0
        for sizes in clusters.values():
            if len(sizes) > 1:
                cluster_count += 1
                duplicate_count += len(sizes) - 1
                reclaimable_bytes += sum(sizes) - max(sizes)
        return {
            "cluster_count": cluster_count,
            "duplicate_count": duplicate_count,
            "reclaimable_bytes": reclaimable_bytes,
        }
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep9_storage_stats.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep9_storage_stats.py
git commit -m "feat(ep9): add storage + duplicate-savings stats"
```

---

## Task 5: Storage dashboard tab + CSV export

**Files:**
- Modify: `src/ui/analytics_panel.py`
- Test: `tests/gui/test_ep9_storage_tab.py`

**Interfaces:**
- Consumes: `get_storage_stats`, `get_duplicate_stats`.
- Produces: a **Storage** tab with `self._storage_summary` (QLabel); `_load_storage()` called from `refresh()`; `_export_storage_csv()`; static `_fmt_bytes(n)`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep9_storage_tab.py`:

```python
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        for name, size, phash in [("a", 1000, "hh"), ("b", 800, "hh"), ("c", 500, "zz")]:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, file_size, phash) "
                "VALUES (1, ?, '2D', ?, ?)", (name, size, phash))


@pytest.mark.gui
def test_storage_tab_reports_reclaimable(qtbot, stax_db):
    _seed(stax_db)
    from ui.analytics_panel import AnalyticsPanel
    panel = AnalyticsPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    text = panel._storage_summary.text()
    assert "3" in text                 # 3 elements
    assert "800" in text or "KB" in text  # reclaimable 800 bytes shown (raw or humanized)


@pytest.mark.gui
def test_fmt_bytes():
    from ui.analytics_panel import AnalyticsPanel
    assert AnalyticsPanel._fmt_bytes(0) == "0 B"
    assert AnalyticsPanel._fmt_bytes(1024) == "1.0 KB"
    assert AnalyticsPanel._fmt_bytes(1536) == "1.5 KB"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep9_storage_tab.py -v`
Expected: FAIL — `_storage_summary` / `_fmt_bytes` missing.

- [ ] **Step 3: Implement**

Add the static formatter to `AnalyticsPanel` (inside the `_QT_AVAILABLE` class):

```python
        @staticmethod
        def _fmt_bytes(n):
            n = float(n or 0)
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if n < 1024.0 or unit == "TB":
                    return ("{:.0f} {}".format(n, unit) if unit == "B"
                            else "{:.1f} {}".format(n, unit))
                n /= 1024.0
```

In `_setup_ui`, after the Search tab, add the Storage tab:

```python
            # Tab 6 — storage hygiene (EP9 F063)
            tab_storage = QtWidgets.QWidget()
            tlst = QtWidgets.QVBoxLayout(tab_storage)
            self._storage_summary = QtWidgets.QLabel("No storage data yet.")
            self._storage_summary.setTextFormat(QtCore.Qt.RichText)
            self._storage_summary.setWordWrap(True)
            self._storage_summary.setAlignment(QtCore.Qt.AlignTop)
            tlst.addWidget(self._storage_summary, 1)
            export_storage_btn = QtWidgets.QPushButton("Export CSV…")
            export_storage_btn.clicked.connect(self._export_storage_csv)
            tlst.addWidget(export_storage_btn)
            tabs.addTab(tab_storage, "Storage")
```

Add `self._load_storage()` to `refresh()` (alongside the other loaders), then the loader + export:

```python
        def _load_storage(self):
            try:
                s = self.db.get_storage_stats()
                d = self.db.get_duplicate_stats()
            except Exception as exc:
                log.warning("Analytics storage: %s", exc)
                s, d = {}, {}
            fb = self._fmt_bytes
            self._storage_summary.setText(
                "<b>Repository</b><br>"
                "Elements: <b>{ec}</b> &nbsp;·&nbsp; Total size: <b>{tb}</b><br>"
                "Hard copies: <b>{hc}</b> ({hb}) &nbsp;·&nbsp; Soft copies: <b>{sc}</b><br>"
                "Deprecated: <b>{dc}</b> ({db} reclaimable by purge)<br><br>"
                "<b>Duplicate savings</b> (exact perceptual-hash match)<br>"
                "Clusters: <b>{cc}</b> &nbsp;·&nbsp; Redundant copies: <b>{du}</b><br>"
                "Reclaimable: <b>{rb}</b>".format(
                    ec=s.get("element_count", 0), tb=fb(s.get("total_bytes", 0)),
                    hc=s.get("hard_copy_count", 0), hb=fb(s.get("hard_copy_bytes", 0)),
                    sc=s.get("soft_copy_count", 0),
                    dc=s.get("deprecated_count", 0), db=fb(s.get("deprecated_bytes", 0)),
                    cc=d.get("cluster_count", 0), du=d.get("duplicate_count", 0),
                    rb=fb(d.get("reclaimable_bytes", 0))))

        def _export_storage_csv(self):
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Storage Analytics CSV", "stax_storage_analytics.csv",
                "CSV files (*.csv)")
            if not path:
                return
            try:
                s = self.db.get_storage_stats()
                d = self.db.get_duplicate_stats()
                with open(path, "w", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["metric", "value"])
                    for k in ("element_count", "total_bytes", "hard_copy_bytes",
                              "hard_copy_count", "soft_copy_count",
                              "deprecated_count", "deprecated_bytes"):
                        writer.writerow([k, s.get(k, 0)])
                    for k in ("cluster_count", "duplicate_count", "reclaimable_bytes"):
                        writer.writerow([k, d.get(k, 0)])
                QtWidgets.QMessageBox.information(
                    self, "Exported", "Storage analytics exported to:\n{}".format(path))
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Export Failed", "Could not write CSV:\n{}".format(exc))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep9_storage_tab.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/analytics_panel.py tests/gui/test_ep9_storage_tab.py
git commit -m "feat(ep9): add Storage hygiene + duplicate-savings tab with CSV export"
```

---

# Cluster 9C — Top-used assets verification (F059)

## Task 6: Headless render test for the insertion-log dashboards

**Files:**
- Test: `tests/gui/test_ep9_top_assets_render.py`
- (No production change unless the test surfaces a gap; F059's data layer is delivered by SP1.)

**Interfaces:**
- Consumes: `log_insertion`, `get_top_inserted_elements`, `get_total_insertions` (SP1); the existing `AnalyticsPanel` Top Assets / Details tabs.

- [ ] **Step 1: Write the failing/gating test**

Create `tests/gui/test_ep9_top_assets_render.py`:

```python
import pytest
from ui.analytics_panel import log_insertion


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'hero_plate', '2D')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'bg_plate', '2D')")
    # hero_plate inserted 3x, bg_plate 1x
    for _ in range(3):
        log_insertion(stax_db, 1, user_id=None)
    log_insertion(stax_db, 2, user_id=None)


@pytest.mark.gui
def test_top_assets_dashboard_renders_real_data(qtbot, stax_db):
    _seed(stax_db)
    from ui.analytics_panel import AnalyticsPanel
    panel = AnalyticsPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    # details table populated, ranked hero_plate first
    assert panel._top_table.rowCount() == 2
    assert panel._top_table.item(0, 1).text() == "hero_plate"
    assert panel._top_table.item(0, 4).text() == "3"
    assert "4" in panel._total_label.text()   # 4 total insertions logged
```

> `log_insertion` uses `db.execute(...)` against the lowercase `insertion_log` table — **provided by SP1**. If SP1 has not landed, this test errors on the missing table; mark it `xfail(strict=True, reason="needs SP1 insertion_log")` and unmark once SP1 merges (do not weaken the assertions).

- [ ] **Step 2: Run it to verify current state**

Run: `pytest tests/gui/test_ep9_top_assets_render.py -v`
Expected (SP1 landed): PASS. Expected (pre-SP1): the guarded `xfail`.

- [ ] **Step 3: Fix only if a real gap appears**

If the panel does not populate despite SP1 being present, trace the concrete cause (e.g. `refresh()` not calling `_load_top_assets`, or a key mismatch vs SP1's documented keys `element_id, name, list_name, format, type, count`) and fix the root cause in `analytics_panel.py` — never weaken the test.

- [ ] **Step 4: Run the full EP9 suite**

Run: `pytest -m "not manual" -k ep9 -v`
Expected: all EP9 unit + GUI tests pass (or the single SP1-gated `xfail`).

- [ ] **Step 5: Commit**

```bash
git add tests/gui/test_ep9_top_assets_render.py
git commit -m "test(ep9): verify top-used-assets dashboard renders real insertion_log data"
```

---

## Self-Review

**1. Spec coverage:**
- Search success table + stats (F060) → Task 1 ✓
- Search instrumentation (F060) → Task 2 ✓
- Search dashboard tab + CSV (F060) → Task 3 ✓
- Storage + duplicate-savings stats (F063) → Task 4 ✓
- Storage dashboard tab + CSV (F063) → Task 5 ✓
- Top-used-assets dashboard verification + CSV parity (F059) → Task 6 (+ retained toolbar export) ✓
- Deferred F061/F062/F064 → no tasks, documented in spec §2/§10 (no placeholder panels) ✓
- Tests unit + headless GUI → every task ✓

**2. Placeholder scan:** New DB units (`log_search_event`, `get_search_success_stats`, `get_zero_result_queries`, `get_storage_stats`, `get_duplicate_stats`) and panel additions (Search tab, Storage tab, `_fmt_bytes`, both exporters, `_log_search`) ship complete real code with exact SQL and Qt wiring. The only task without new production code (Task 6) is a verification test anchored to SP1's documented method keys, with an explicit fix-the-root-cause instruction and a named `xfail` gate — not a placeholder.

**3. Type consistency:** `log_search_event(query, result_count, user_name)` (Task 1) is consumed identically by `_log_search` (Task 2). `get_search_success_stats` keys (`total, success, zero_result, success_rate, zero_result_rate`) and `get_zero_result_queries` keys (`query_text, count`) produced in Task 1 are consumed exactly in Task 3. `get_storage_stats` keys (`element_count, total_bytes, hard_copy_bytes, hard_copy_count, soft_copy_count, deprecated_count, deprecated_bytes`) and `get_duplicate_stats` keys (`cluster_count, duplicate_count, reclaimable_bytes`) produced in Task 4 are consumed exactly in Task 5. `get_top_inserted_elements` keys used in Task 6 (`name`, `count`) match SP1's documented output. `AnalyticsPanel._fmt_bytes` is a static method usable both instance-side (Task 5 loader) and class-side (Task 5 test).

**Note for the executor:** EP9 assumes **SP1** (lowercase `insertion_log`, `elements.phash`, `get_connection(write=…)`, the four real analytics reads) and — for instrumentation only — **EP2**'s search entry point + `self.user_name`. If running before SP1, drop the `write=` kwarg and `xfail(strict=True)` the F059 render test and the duplicate-savings test with the SP1 id; do not assert on empty data. Match the real logger name and `MediaDisplayWidget.__init__` signature in the file before editing. Never weaken a test to pass — fix the root cause or `xfail(strict)` with the dependency id.
