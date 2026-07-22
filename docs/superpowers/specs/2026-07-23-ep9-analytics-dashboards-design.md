# EP9 — Analytics & Ops Dashboards — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F059 (top-used assets dashboard), F060 (search success analytics), F063 (storage hygiene & duplicate savings). **Deferred (documented, not built here):** F061 (ingest throughput/failure rates), F062 (review-cycle duration), F064 (underused-asset recommendations).

---

## 1. Background & Motivation

StaX already ships a dockable `AnalyticsPanel` (`src/ui/analytics_panel.py`) with a dependency-free custom `_BarChart` and four tabs (Top Assets, Details, Over Time, By User). Today those charts are **permanently empty**: `log_insertion` writes to a `InsertionLog` table that is never created, and `get_top_inserted_elements` / `get_insertions_by_month` / `get_insertions_by_user` / `get_total_insertions` are orphaned methods (audit issue **C1**). **SP1 fixes exactly this** — it creates the lowercase `insertion_log` table, the versioned migration runner, the `elements.phash` column, and rewrites those four read methods against the live schema, so the existing panel starts showing **real** data.

EP9 is the **lightest EP in the program**: it builds *only* dashboards whose source data already exists after SP1/EP2/EP4, reusing the existing panel and its `_BarChart` (no plotting libraries). It ships three things users can immediately see:

1. **Top-used assets (F059)** — already rendered by `AnalyticsPanel`; EP9 verifies it against a real SP1-backed `insertion_log`, guarantees a headless render test, and makes CSV export consistent across dashboards.
2. **Search success analytics (F060)** — instrument every search with a `log_search_event(query, result_count, user)` write into a new `search_events` table, then surface success-rate / zero-result-rate and the top failing (zero-result) queries so librarians know what users can't find.
3. **Storage hygiene & duplicate savings (F063)** — compute repository size, hard/soft/deprecated breakdown, and — from the `elements.phash` column SP1 adds — duplicate-cluster count and **reclaimable bytes**, so admins see how much disk a dedup pass would recover.

EP9 explicitly **does not** build dead or placeholder panels: F061 (ingest throughput/failure rates) needs EP6's job queue, F062 (review-cycle duration) needs EP5's review workflow, and F064 (underused-asset recommendations) is low-priority. They are documented as follow-ons (§9) and wired only when the source EP lands.

### Locked design decisions
- **Build on available data now; add review/ingest ops panels later.** Ship F059, F060, F063 only. Defer F061/F062/F064 — no placeholder tabs.
- **Reuse, don't replace.** Extend the existing `AnalyticsPanel` with new tabs and reuse `_BarChart`. **No new dependencies** — no matplotlib/plotly/pyqtgraph. Custom bar chart + tables only.
- **All stats are computed by `DatabaseManager` read methods** over the live lowercase schema; the panel is a thin view. Every dashboard has a **CSV export** following the panel's existing `_export_csv` pattern.
- **Search success needs a result count**, which EP2's `recent_searches` table does not store — so EP9 adds a dedicated `search_events(query, result_count, user)` table rather than overloading `recent_searches`.
- Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`; conventional commits.

### Dependencies
- **SP1 (hard)** — the C1 fix. EP9 **assumes SP1 has landed**: the lowercase `insertion_log` table, the versioned migration runner + `get_connection(write=…)`, `elements.phash`, and the four real analytics read methods (`get_top_inserted_elements`, `get_insertions_by_month`, `get_insertions_by_user`, `get_total_insertions`). Without SP1 the Top-Assets dashboard renders empty and duplicate savings has no `phash` to group on. If running strictly before SP1, drop the `write=` kwarg (plain `get_connection()`).
- **EP2 (soft)** — the search entry point (`run_text_search` / `on_search` in `media_display_widget.py`) is where `log_search_event` is instrumented, and `user_name` is threaded through the media widget. EP9's DB-level stats and its own `_log_search` helper are independently testable without EP2.
- **EP4 (soft, optional)** — metadata completeness (required-field coverage) can later feed the storage-hygiene "quality" section via `get_quality_summary`; out of scope here, noted as follow-on.
- **SP0** — the `stax_db` (real `DatabaseManager` on a temp DB) and headless offscreen Qt fixtures used by every test.

### Delivery clusters
- **9A — Search success analytics (F060):** `search_events` table + `log_search_event` + `get_search_success_stats` + `get_zero_result_queries`; instrument the search path; Search tab + CSV.
- **9B — Storage hygiene & duplicate savings (F063):** `get_storage_stats` + `get_duplicate_stats`; Storage tab + CSV.
- **9C — Top-used assets verification (F059):** headless render test for the existing insertion-log dashboards against seeded data; per-tab CSV consistency.

Each cluster is independently shippable; 9A and 9B do not depend on each other.

---

## 2. Goals / Non-Goals

### Goals
- Surface **real** top-used-asset dashboards (F059) off the SP1 `insertion_log`, with a guaranteed headless render test.
- Instrument searches and compute **search success rate**, **zero-result rate**, and the **top zero-result queries** (F060).
- Compute **repository size**, hard/soft/deprecated storage breakdown, and **duplicate-cluster count + reclaimable bytes** from `elements.phash` (F063).
- Reuse `AnalyticsPanel` + `_BarChart`; add a **Search** tab and a **Storage** tab; per-dashboard **CSV export**.
- No new third-party dependencies; all stats unit-tested on seeded rows; dashboards headless-GUI-tested.

### Non-Goals (deferred)
- **Ingest throughput & failure rates (F061)** — needs EP6's job queue as the event source. `ingestion_history` alone lacks durations/queue-wait; wired when EP6 lands.
- **Review-cycle duration (F062)** — needs EP5's review/approval state transitions.
- **Underused-asset recommendation widgets (F064)** — low priority; a follow-on that can reuse `insertion_log` (assets with zero recent insertions).
- **Live/streaming dashboards, scheduled reports, or a web analytics page** — the panel refreshes on demand (`refresh()` / `showEvent`).
- **Near-duplicate (Hamming-distance) clustering for reclaimable bytes** — EP9 clusters on **exact phash equality** (O(n)); threshold-based near-dup clustering is O(n²) and a follow-on (§9).
- **Any new charting dependency.**

---

## 3. Detailed Design — Cluster 9A (Search success analytics, F060)

### 3.1 Table

```sql
CREATE TABLE IF NOT EXISTS search_events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name    TEXT,
    query_text   TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    ran_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_search_events_zero ON search_events(result_count);
```

Added in `_create_schema` (and mirrored in the idempotent `_apply_migrations` block) as `CREATE TABLE IF NOT EXISTS`, following the EP2 saved-searches/recent-searches pattern. Distinct from EP2's `recent_searches` (which stores only `query_text`, no result count) — success-rate analytics require the outcome, so this is its own table. `recent_searches` remains the search-box completer source; `search_events` is the analytics source.

### 3.2 DB API

```
log_search_event(query, result_count, user_name=None) -> int
    INSERT one row; called after a search resolves its result count. Never raises into the caller.
get_search_success_stats() -> dict
    {"total", "zero_result", "success", "success_rate", "zero_result_rate"}
    success = total - zero_result; rates are fractions in [0.0, 1.0] (0.0 when total == 0).
get_zero_result_queries(limit=20) -> list[dict]
    [{"query_text", "count"}, ...] for queries that returned 0 results, most frequent first.
```

`get_search_success_stats` is a single grouped `SELECT COUNT(*)` + `SUM(CASE WHEN result_count = 0 …)` over `search_events`. `get_zero_result_queries` groups the zero-result rows by `query_text`.

### 3.3 Instrumentation

`MediaDisplayWidget` gains a small guarded helper:

```
_log_search(self, text, result_count)  ->  self.db.log_search_event(text, result_count, self.user_name)
```

wrapped in `try/except` (analytics must never break search). It is called from the existing search entry point (`run_text_search` from EP2, or `on_search` at `media_display_widget.py:546`) once the result count is known (`count_elements_advanced` for EP2's path, or `len(elements)` for the tag path). Empty/whitespace queries are skipped.

### 3.4 Search dashboard (Search tab)

A new **Search** tab in `AnalyticsPanel`:
- A summary label: `Searches: N   ·   Success: X%   ·   Zero-result: Y%` from `get_search_success_stats`.
- A **Top failing searches** table (`query_text`, `count`) from `get_zero_result_queries` — the actionable output (synonyms/tags to add).
- An **Export CSV…** button → `_export_search_csv` (summary + zero-result rows), following the existing `_export_csv` pattern.

---

## 4. Detailed Design — Cluster 9B (Storage hygiene & duplicate savings, F063)

### 4.1 DB API (no new tables — pure reads over `elements`)

```
get_storage_stats() -> dict
    {"element_count", "total_bytes", "hard_copy_bytes", "hard_copy_count",
     "soft_copy_count", "deprecated_count", "deprecated_bytes"}
    A single aggregate SELECT over elements (file_size, is_hard_copy, is_deprecated).
get_duplicate_stats() -> dict
    {"cluster_count", "duplicate_count", "reclaimable_bytes"}
```

**Duplicate savings** groups `elements` by non-empty `phash` (the column SP1 adds). For each cluster of size > 1:
- `cluster_count += 1`
- `duplicate_count += len(cluster) - 1` (extra copies beyond the first)
- `reclaimable_bytes += sum(file_size in cluster) - max(file_size in cluster)` (keep the largest copy, reclaim the rest)

Grouping is done in Python over `SELECT phash, file_size FROM elements WHERE phash IS NOT NULL AND phash != ''` — the same clusters `duplicate_detection.find_duplicates` would surface at distance 0, but computed in aggregate for the whole repo. `NULL` `file_size` coerces to 0.

### 4.2 Storage dashboard (Storage tab)

A new **Storage** tab in `AnalyticsPanel`:
- Repository summary: element count, total size (human-readable via `_fmt_bytes`), hard-copy vs soft-copy counts, deprecated count + deprecated bytes ("reclaimable by purging deprecated").
- Duplicate savings: cluster count, duplicate-copy count, **reclaimable bytes** (human-readable).
- An **Export CSV…** button → `_export_storage_csv`.

`_fmt_bytes(n)` is a small static helper (B/KB/MB/GB/TB) reused by both the storage summary and the CSV.

---

## 5. Detailed Design — Cluster 9C (Top-used assets verification, F059)

The Top Assets / Details / Over Time / By User tabs already exist and call SP1's four read methods. EP9's work here is **verification, not new UI**:
- A headless GUI test seeds `insertion_log` rows (via `log_insertion` against the SP1 table) and asserts the panel's `refresh()` populates the top-assets chart data, the details table, and the total label — proving the dashboard renders **real** data end-to-end post-SP1.
- CSV export consistency: the existing toolbar **Export CSV…** (top assets) is retained; the Search and Storage tabs each get their own export button so every dashboard is exportable.

No schema or query changes — F059's data layer is delivered by SP1; EP9 owns its dashboard verification and export parity.

---

## 6. Architecture & File Impact

| File | Change |
|---|---|
| `src/db_manager.py` | `search_events` table (+ migration); `log_search_event`, `get_search_success_stats`, `get_zero_result_queries`; `get_storage_stats`, `get_duplicate_stats`. All reads use `get_connection(write=False)`; the write uses `write=True`. |
| `src/ui/analytics_panel.py` | New **Search** and **Storage** tabs in `_setup_ui`; `_load_search`, `_load_storage` in `refresh()`; `_export_search_csv`, `_export_storage_csv`, static `_fmt_bytes`. Reuses `_BarChart`; no new deps. |
| `src/ui/media_display_widget.py` | `_log_search(text, result_count)` helper; one call from the existing search entry point (EP2's `run_text_search` / `on_search`). |
| (tests) | `tests/unit/test_ep9_search_stats.py`, `tests/unit/test_ep9_storage_stats.py`, `tests/gui/test_ep9_search_tab.py`, `tests/gui/test_ep9_storage_tab.py`, `tests/gui/test_ep9_top_assets_render.py`, `tests/gui/test_ep9_search_instrument.py`. |

All stat computation lives in `DatabaseManager` (testable without Qt); the panel stays a thin, dependency-light view.

---

## 7. Testing Strategy

- **Unit (`stax_db`, seeded rows):**
  - `log_search_event` inserts a row; `get_search_success_stats` computes total / zero / success / rates correctly (incl. the empty-DB `total == 0 → rate 0.0` case); `get_zero_result_queries` groups and orders zero-result queries by frequency.
  - `get_storage_stats` sums `file_size` and counts hard/soft/deprecated correctly (incl. `NULL` file_size → 0).
  - `get_duplicate_stats` clusters by exact `phash`: one cluster of 3 → `cluster_count=1`, `duplicate_count=2`, `reclaimable_bytes = total − largest`; singletons and `NULL`/empty phash are ignored.
- **GUI (headless offscreen):**
  - Search tab: after seeding events, `refresh()` shows the success-rate summary and lists zero-result queries.
  - Storage tab: after seeding sized/phashed elements, `refresh()` shows total size and reclaimable bytes.
  - Top-assets render: seed `insertion_log`, `refresh()`, assert the chart/table/total populate (F059 renders real data).
  - Instrumentation: `MediaDisplayWidget._log_search(text, n)` writes a `search_events` row (`get_search_success_stats()["total"] == 1`).
- **No test is weakened to pass.** If SP1 has not landed, dependency-gated tests `xfail(strict=True)` with the SP1 id rather than asserting on empty data.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| SP1 not yet merged → empty top-assets dashboard, no `phash` for dedup | EP9 declares the hard SP1 dependency; dependency-gated tests `xfail(strict)` with the SP1 id; instructions to drop `write=` if running pre-SP1. |
| Analytics logging breaks search | `_log_search` and `log_search_event` are fully `try/except`-guarded; a logging failure is warned and swallowed, never propagated to the search path. |
| Reclaimable-bytes over/under-counts on near-duplicates | EP9 clusters on **exact phash** only (documented); near-dup (Hamming ≤ threshold) clustering is a follow-on. Exact-match savings is a safe lower bound. |
| `file_size` may be `NULL` for legacy rows | All sums use `COALESCE(file_size, 0)`; reported total is a lower bound; noted in the panel. |
| `search_events` grows unbounded | Rows are tiny; if needed a cap/prune mirrors EP2's `recent_searches` trim. Out of scope for v1 (documented follow-on). |
| Building F061/F062 panels before their source EPs | Explicitly deferred; no placeholder tabs shipped — only dashboards whose data exists. |
| Panel construction heavy in headless tests | Stat methods are pure `DatabaseManager` reads unit-tested without Qt; GUI tests use SP0 offscreen fixtures and call `refresh()` directly. |

---

## 9. Deliverables Checklist
- [ ] `search_events` table + migration; `log_search_event`, `get_search_success_stats`, `get_zero_result_queries`.
- [ ] `get_storage_stats`, `get_duplicate_stats` (exact-phash clustering, reclaimable bytes).
- [ ] `MediaDisplayWidget._log_search` + instrumentation of the search entry point.
- [ ] `AnalyticsPanel` **Search** tab + `_export_search_csv`.
- [ ] `AnalyticsPanel` **Storage** tab + `_export_storage_csv` + `_fmt_bytes`.
- [ ] F059 top-assets headless render test against seeded `insertion_log`.
- [ ] Unit + headless GUI tests green.

---

## 10. Follow-on
- **F061 (ingest throughput & failure rates):** when EP6's job queue lands, add `get_ingest_throughput_stats` over the queue's timing/status events and an Ops tab (retry/failure rates, queue-wait percentiles).
- **F062 (review-cycle duration):** when EP5's review statuses land, measure WIP→Approved transition durations.
- **F064 (underused-asset recommendations):** reuse `insertion_log` to surface assets with zero recent insertions as a Home/analytics widget.
- **EP4 hook:** feed `get_quality_summary` (metadata completeness) into the Storage/hygiene tab as a data-health section.
- **Near-duplicate savings:** upgrade `get_duplicate_stats` to threshold-based clustering once a phash index/BK-tree makes it sub-quadratic.
- **Retention:** optional prune/cap for `search_events` mirroring `recent_searches`.
