# Cross-Plan Review — SP0–SP8 + EP1–EP4, EP6–EP9

**Date:** 2026-07-23
**Purpose:** A single-context conflict & duplication audit across all 17 planned sub-projects (8 remediation SP + 9 enhancement EP, minus EP5 which is cancelled), to confirm the plans can be implemented without colliding or doing the same work twice.
**Method:** Mechanically extracted, from every plan, the set of source files each touches, the new tables each creates, and the new modules each adds; then reasoned over that matrix and spot-checked the hotspots.

---

## 1. Verdict

**The plan set is coherent and safe to implement in dependency order.** There are **no structural collisions** — no two sub-projects create the same table or the same new file, and every new table name is unique. Feature overlaps between EPs and SPs are **complementary, not duplicated** (each EP consumes an SP's fix rather than re-doing it). One **real bug was found and fixed** during this review (a wrong `SettingsPanel` constructor arg-order in three EP plans). The remaining findings are **merge-discipline notes** for the handful of hub files that many sub-projects extend additively, plus a few **semantic-duplication** items to converge.

| Check | Result |
|---|---|
| Duplicate table names | **None** — 25 new tables, all unique |
| Duplicate new module files | **None** — no path created by 2 plans |
| Duplicate/redundant feature work | **None** — overlaps are consumer/provider, not re-implementations |
| Constructor/signature mismatches | **1 found → fixed** (`SettingsPanel`) |
| Hub-file contention | 4 files; additive; needs ordering + merge discipline |
| Semantic duplicate helpers | 2 (converge on one) |
| Dependency graph | Acyclic; canonical order below |

---

## 2. New tables — ownership (no duplicates)

25 new tables, each owned by exactly one sub-project:

- **SP1:** `schema_version`, `insertion_log`
- **EP1:** `labels`
- **EP2:** `saved_searches`, `smart_collections`, `search_synonyms`, `recent_searches`
- **EP4:** `metadata_fields`, `element_metadata`, `metadata_defaults`, `metadata_templates`, `autotag_rules`, `quality_rules`, `element_relationships`
- **EP6:** `ingest_jobs`, `ingest_recipes`, `watch_folders`, `proxy_profiles`, `notifications`, `action_chains`
- **EP7:** `element_embeddings`, `element_colors`
- **EP8:** `roles`, `role_permissions`, `activity_log`
- **EP9:** `search_events`

No name clashes. (EP1 also adds columns `elements.rating`/`label_fk`; EP8 adds `elements.updated_at` — different columns, no clash.)

---

## 3. Shared-file hotspots & merge discipline

Four files are extended by many sub-projects. All changes are **additive** (new methods / new tabs / new wiring), so there is no semantic conflict — but if implemented out of order or in parallel they will produce **git merge conflicts** and dangling assumptions. Implement in the canonical order (§6) and treat these as append-only.

| File | Sub-projects | Nature | Discipline |
|---|---|---|---|
| `src/db_manager.py` | SP1, SP4, EP1, EP2, EP3, EP4, EP6, EP7, EP8, EP9 (10) | New methods + tables | **SP1 must land first** (it consolidates the two DB layers and adds `get_connection(write=)` + the migration runner every EP assumes). All later additions are new methods — append, don't reorder. |
| `src/ui/settings_panel.py` | SP6, EP1, EP2, EP3, EP4, EP6, EP7, EP8 (8) | New admin tabs via `addTab` | **SP6 first** (fixes M13 `reset_settings` layout bug). Each EP appends one `addTab(...)` in `setup_ui` + its own `_build_*_tab`. Keep tab-builders in separate methods to minimize merge surface. |
| `main.py` | SP2, SP5, SP8, EP3, EP4, EP6, EP7, EP8 (8) | Shortcuts, docks, panes, wiring | Additive. New docks (Health/Activity/Queue/AI) and shortcuts append to `__init__`/`setup_menus`. |
| `src/ui/media_display_widget.py` | SP6, SP8, EP1, EP2, EP3, EP7, EP9 (7) | Badges, drawer, quicklook, AI actions | This is the audit's god module. **SP8 deliberately DEFERS splitting it** (its plan §4.6) precisely to avoid colliding with these EPs — correct call. Recommend: do the split (if ever) as a *final* pass after all EPs, or not this cycle. New widgets already live in their own files (EP1 tray, EP2 drawer/chips, EP3 overlays) to keep this file's growth minimal. |

Two more with light contention: `src/ui/dialogs.py` (EP4 custom-fields + naming, SP6 M4/M13 — additive), `src/ui/media_info_popup.py` (EP3 extracts format helpers, SP6 M7 fix — EP3 should extract *after* SP6's M7 type-detection fix so the shared helper reflects the corrected logic).

---

## 4. Issues found

### 4.1 FIXED — `SettingsPanel` constructor arg-order (EP1, EP2, EP4)
The real signature is `SettingsPanel(config, db_manager, main_window=None, parent=None)` (**config first**), but the EP1/EP2/EP4 plan test snippets called `SettingsPanel(stax_db, config=None, main_window=...)`, which would pass the DB into the `config` parameter. **Fixed in this review** — all six call sites across the three plans now use `SettingsPanel(config=None, db_manager=stax_db, main_window=...)`. (EP6/EP7/EP8 already used the correct order.)

### 4.2 CONVERGE — duplicate `human_size` helper (EP3 ↔ SP8)
EP3 Task 5 creates `src/ui/metadata_format.py::human_size`; SP8 (L10) creates `src/utils/formatting.py::human_size`. Not a collision (different paths) but two implementations of the same thing. **Resolution:** whichever lands second imports the first (recommend the canonical home be `src/utils/formatting.py`; have `metadata_format.py` re-export it). Already noted in the tracker.

### 4.3 CONVERGE — `paths` module naming (SP7 ↔ SP8)
SP7 creates `src/paths.py` (per-user app-data/log dirs); SP8 creates `src/utils/paths.py` (`resolve_path`). Different purpose, confusable name. **Resolution:** rename SP7's to `src/utils/appdirs.py` (recommended in the tracker) so there is one obvious `paths` util.

### 4.4 CONVERGE — two search-logging tables (EP2 ↔ EP9)
EP2 creates `recent_searches` (query history for the recent-dropdown/completer); EP9 creates `search_events` (query + result_count for success-rate analytics). Mild overlap — both log searches. **Resolution (optional):** either add a `result_count` column to `recent_searches` and have EP9 read it, or keep both but have the single `on_search` path write once and derive both. Low priority; not a blocker.

### 4.5 SEQUENCING — `ingest_file` is layered by three sub-projects (SP2, EP4, EP6, +EP7)
SP2 rewrites `ingest_file` (async), EP4 adds an auto-tag/field hook, EP6 adds recipe/proxy options, EP7 adds an embedding/color hook. All additive. **Order: SP2 → EP4 → EP6 → EP7**, each layering its hook onto the previous version. Integration tests in EP4/EP6/EP7 are already marked `xfail(strict)` tagged with the dependency id until SP2 lands.

### 4.6 SEQUENCING — admin gating supersession (EP8)
EP8 introduces granular `has_permission`/`check_permission`; EP1/EP2/EP4/EP6/EP7 admin-gated surfaces use the binary `check_admin_permission`. **Resolution:** when EP8 lands, keep a `check_admin_permission` shim that maps to the relevant `can_manage_*` permission, so earlier surfaces keep working without edits.

---

## 5. No-double-work verification

Checked every plausible feature overlap between an EP and an SP (or another EP). All are **provider/consumer relationships**, not duplicated implementations:

| Potential overlap | Reality — complementary |
|---|---|
| EP1 action-tray "Edit…" vs SP6 batch-edit wiring (L2) | EP1 *opens* the `BatchEditDialog` that SP6 *wires*. Consumer. |
| EP6 job-queue dashboard vs SP2 async worker | EP6 *wraps/surfaces* SP2's `IngestWorker`/`PreviewWorker`; no second queue. Consumer. |
| EP6 dup-policy vs SP2 duplicate_detection (L5) | EP6 *applies policy* over SP2's wired `find_duplicates`. Consumer. |
| EP9 dashboards vs SP1 analytics fix (C1) | SP1 fixes the insertion-log backend; EP9 *visualizes* it. Consumer. |
| EP4 auto-tag vs EP6 recipes | Distinct: EP4 = path→tags/fields at ingest; EP6 = named ingest presets/proxy. Compose. |
| EP7 similar-search vs SP2/EP6 duplicate detection | Distinct algorithms: EP7 = CLIP embeddings; dedup = pHash. Different purpose. |
| EP7 auto-tag vs EP4 auto-tag | Distinct: EP4 = deterministic path rules; EP7 = model-suggested tags (human-in-loop). Compose. |
| EP3 quicklook/skeleton vs SP2 async previews | EP3 *shows* skeletons driven by SP2's `preview_ready`; consumer, no-op without SP2. |
| EP1 color-label vs EP5 review statuses | EP5 is cancelled; EP1's label is the sole status marker. No overlap. |

**Conclusion:** no sub-project re-implements another's work.

---

## 6. Canonical implementation order (acyclic)

The dependency notes across all plans form a DAG. A valid total order:

```
SP0 → SP1 → SP2 → SP3 → SP4 → SP5 → SP6 → SP7 → SP8      (remediation)
  then
EP1 → EP2 → EP3 → EP4 → EP6 → EP7 → EP8 → EP9            (enhancements)
```

Key hard edges (must precede):
- **SP0 before everything** (test harness/CI; C1 xfail smoke tests).
- **SP1 before every EP** (consolidated DB, `get_connection(write=)`, migrations, real analytics).
- **SP2 before EP4/EP6/EP7** (`ingest_file` rewrite; async worker the queue/backfill wrap).
- **SP4 before EP8** (auth/roles hardening).
- **SP6 before EP1/EP3** (multi-select/admin-flag fixes; M13 settings-reset; M7 popup types).
- **EP1 before EP2/EP3/EP4/EP7/EP9** (rating/label columns as facets/inputs).
- **EP2 before EP3/EP7/EP9** (`FilterSpec`/result surface).
- **EP3 before EP4** (inspector hosts EP4 custom-fields + related).
- **EP4 before EP6/EP7/EP9** (metadata schema / templates / completeness).

Enhancements may begin once their SP prerequisites are in; they need not wait for *all* of SP0–SP8 (e.g. EP1 needs SP1+SP6, not SP7). But the simplest safe path is remediation-complete, then EPs in number order.

---

## 7. Consolidated reconciliation checklist (do at implementation time)

- [ ] Land **SP1 first**; every EP's DB additions append to the consolidated `DatabaseManager`.
- [ ] Layer `ingest_file` hooks in order **SP2 → EP4 → EP6 → EP7** (all additive).
- [ ] Land **SP6 before EP1/EP3**; extract EP3's shared metadata formatter **after** SP6's M7 fix.
- [ ] Converge `human_size` on `src/utils/formatting.py` (SP8); `metadata_format.py` re-exports.
- [ ] Rename SP7's app-dirs module to `src/utils/appdirs.py` to avoid clashing with SP8's `src/utils/paths.py`.
- [ ] When **EP8** lands, add a `check_admin_permission` → `can_manage_*` shim so EP1/EP2/EP4/EP6/EP7 gates keep working.
- [ ] (Optional) Merge EP2 `recent_searches` + EP9 `search_events` into one search-log write path.
- [ ] Keep the **media_display_widget split (SP8) deferred** to a final pass, or skip it this cycle.
- [ ] Add deps to `pyproject.toml` additively: SP0 dev group, SP2 `fileseq`, SP7 build-system (`cx-freeze`, structural — merge carefully), EP7 `onnxruntime`.

---

## 8. Bottom line

Across ~40,000 lines of specs and plans, the only executable defect was one constructor arg-order (now fixed). Everything else is additive and correctly sequenced. Implement in the canonical order, treat the four hub files as append-only, and apply the eight reconciliation items at the relevant step — there is no duplicated work and no design conflict.
