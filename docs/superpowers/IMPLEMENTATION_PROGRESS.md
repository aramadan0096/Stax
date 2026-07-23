# StaX Audit Remediation — Implementation Progress

Live tracker for the audit-driven remediation program. Source of issues:
[`STAX_AUDIT_REPORT.md`](../../STAX_AUDIT_REPORT.md). Each sub-project has a
design spec (`specs/`) and a task plan (`plans/`).

**Legend:** ☐ not started · ◐ in progress · ☑ done

**Program-level decisions (locked):** wire half-finished features up (don't
delete) · target Windows + Linux · hybrid 3-tier testing · adopt proven OSS
building blocks where they replace bespoke code.

---

## Sub-project status overview

| SP | Title | Spec | Plan | Impl | Issues |
|----|-------|:----:|:----:|:----:|--------|
| SP0 | Test harness & CI foundation | ☑ | ☑ | ☑ | (CI push + branch-protection deferred to human) |
| SP1 | Database consolidation & concurrency | ☑ | ☑ | ☑ | C1, H1, H3, M1, L6, L11 — all fixed |
| SP2 | Async ingestion & preview pipeline | ☑ | ☑ | ☑ | C4, H7, M12, L8, L5 — all fixed |
| SP3 | FFmpeg/media hardening & cross-platform | ☑ | ☑ | ☑ | H4, M8, M9, M10 — all fixed |
| SP4 | Security hardening | ☑ | ☑ | ☑ | C2, C3, H2, H6, M2, L9 |
| SP5 | Nuke integration & embedded-mode | ☑ | ☑ | ☑ | H5, H8, L1, L3, L7 |
| SP6 | UI correctness & memory | ☑ | ☑ | ☑ | M3, M4, M5, M6, M7, M13, L2 |
| SP7 | Build, packaging & deployment | ☑ | ☑ | ☐ | M11, M14 |
| SP8 | Code quality & consistency | ☑ | ☑ | ☐ | L4, L10 |

**All specs and plans are written** (`docs/superpowers/specs/` and `plans/`). Execution has not started. See "Cross-SP reconciliation notes" at the bottom before executing.

---

## SP0 — Test harness & CI foundation
Spec: [`specs/2026-07-22-sp0-test-harness-ci-design.md`](specs/2026-07-22-sp0-test-harness-ci-design.md) ·
Plan: [`plans/2026-07-22-sp0-test-harness-ci.md`](plans/2026-07-22-sp0-test-harness-ci.md)

- [x] Task 1 — Restructure `tests/` into unit/gui/nuke tiers, archive scratch
- [x] Task 2 — Add dev dependencies (`pytest-qt`, `pytest-mock`, `pytest-cov`, `flask`)
- [x] Task 3 — Rewrite `conftest.py` around the real `DatabaseManager`
- [x] Task 4 — Update `pytest.ini` (testpaths, strict markers)
- [x] Task 5 — Characterization tests: SequenceDetector & Config
- [x] Task 6 — Characterization tests: PreviewCache & FileLockManager
- [x] Task 7 — Nuke-tier smoke: NukeBridge mock mode
- [x] Task 8 — GUI-tier smoke tests (strict `xfail` for C1)
- [x] Task 9 — GitHub Actions CI workflow written + committed locally (push + branch protection pending human approval)

---

## SP1 — Database consolidation & concurrency
Spec: [`specs/…-sp1-database-consolidation-design.md`](specs/2026-07-22-sp1-database-consolidation-design.md) · Plan: [`plans/…-sp1-database-consolidation.md`](plans/2026-07-22-sp1-database-consolidation.md)

- [x] **C1** — Merge the two DB layers into one `DatabaseManager`; single versioned migration runner; wire analytics/API/batch-edit; write `ingestion_history`/insertion log. Flip SP0's C1 `xfail` smoke tests to pass. _(migration runner + phash + insertion_log; analytics/count/metadata/phash methods; C1 smoke tests now real PASS)_
- [x] **H1** — Fix lock-file delete-on-release race; switch WAL→DELETE/TRUNCATE on network shares.
- [x] **H3** — Remove duplicated, signature-swapped favorite methods; single canonical signature.
- [x] **M1** — Whitelist column names in `search_elements` / `update_element` (kill SQL-format injection).
- [x] **L6** — Scope the external lock to writes; allow concurrent readers; reuse per-thread connection.
- [x] **L11** — Playlist migration: verify row counts, raise on mismatch (no silent data loss).

---

## SP2 — Async ingestion & preview pipeline
Spec: [`specs/…-sp2-async-pipeline-design.md`](specs/2026-07-22-sp2-async-pipeline-design.md) · Plan: [`plans/…-sp2-async-pipeline.md`](plans/2026-07-22-sp2-async-pipeline.md)

- [x] **C4** — Wire `PreviewWorker` + `LazyGalleryView`; move ingestion off the GUI thread. _(IngestWorker QThread drives perform_ingestion/library/drop-ingest; ingest_file submits async PreviewJob; DragGalleryView subclasses LazyGalleryView with viewport-bounded decode; ingestion_core_patch.py deleted)_
- [x] **H7** — Drop-ingest: pass `config.get_all()`, use `default_copy_policy`, hold thread reference.
- [x] **M12** — Decode EXR/DPX; derive padding from detected sequence, not `%04d`. _(routed through bundled ffmpeg via `ffmpeg_wrapper` — NOT OpenImageIO, per this batch's no-new-heavy-dependency decision; real sequence pattern + first_frame)_
- [x] **L8** — Replace/harden frame-range parsing with **Fileseq**. _(parse_frame_range + _compact_frame_range; nuke_bridge real-mode hardened)_
- [x] **L5** — Wire duplicate detection into ingest; fix MD5-fallback distance semantics. _(tagged p:/m: hashes; compute_phash+find_duplicates wired into ingest_file)_

---

## SP3 — FFmpeg/media hardening & cross-platform
Spec: [`specs/…-sp3-ffmpeg-cross-platform-design.md`](specs/2026-07-22-sp3-ffmpeg-cross-platform-design.md) · Plan: [`plans/…-sp3-ffmpeg-cross-platform.md`](plans/2026-07-22-sp3-ffmpeg-cross-platform.md)

- [x] **H4** — Select ffmpeg binary names by platform (Win `.exe` / Linux) — unblock Linux. _(`_binary_name` + `_resolve_binary` with `shutil.which` fallback)_
- [x] **M8** — Per-call temp palette file for GIF two-pass (no shared `palette.png` race). _(`mkdtemp` per call, cleaned in `finally`)_
- [x] **M9** — Add `timeout=` to all ffmpeg subprocess calls; handle `TimeoutExpired`. _(all 10 check_output sites; PROBE_TIMEOUT=60 / ENCODE_TIMEOUT=600)_
- [x] **M10** — Fix ffplay PIPE deadlock (`DEVNULL` / drain); `CREATE_NO_WINDOW` on Windows.

---

## SP4 — Security hardening
Spec: [`specs/…-sp4-security-hardening-design.md`](specs/2026-07-22-sp4-security-hardening-design.md) · Plan: [`plans/…-sp4-security-hardening.md`](plans/2026-07-22-sp4-security-hardening.md)

- [x] **C2** — Restrict processor `exec()` to an admin-owned trusted dir; validate paths (realpath containment); drop "safe" claim. (Not sandboxed — path-restricted, per locked decision.)
- [x] **C3** — Pin + checksum ffmpeg download; sanitize archive extraction (Zip-Slip). *(SHA-256 values deferred: empty placeholders fail closed; need a human-approved one-time download to populate.)*
- [x] **H2** — Salted PBKDF2 (stdlib); eliminate default `admin/admin`; random seed + `must_change_password`. (Forced-reset dialog delivered in SP6.)
- [x] **H6** — GeometryViewer: allow-list served files; reject paths outside previews root; server shutdown hook. (`closeEvent` wiring delivered in SP6.)
- [x] **M2** — API: `hmac.compare_digest` token check (both backends); ingest-path allowlist.
- [x] **L9** — CLI: support HTTPS; prefer `STAX_API_TOKEN` env over `--token` in argv.

---

## SP5 — Nuke integration & embedded-mode
Spec: [`specs/…-sp5-nuke-integration-design.md`](specs/2026-07-22-sp5-nuke-integration-design.md) · Plan: [`plans/…-sp5-nuke-integration.md`](plans/2026-07-22-sp5-nuke-integration.md)

- [x] **H5** — `menu.py` commands target the live `StaXPanel` singleton via `get_stax_panel()`, not a pane result.
- [x] **H8** — DebugManager scoped to the `stax` logger; never replaces/swallows stdout/stderr.
- [x] **L1** — `init.py`: pure `build_plugin_paths(stax_root)` returns absolute normalized paths; imports cleanly without Nuke.
- [x] **L3** — Deleted orphaned `nuke_bridge_patch.py` (+ regression guard).
- [x] **L7** — Removed Python-2.7 claims/shims across 13 files; single Py3 interpreter (guard test enforces).

---

## SP6 — UI correctness & memory
Spec: [`specs/…-sp6-ui-correctness-design.md`](specs/2026-07-22-sp6-ui-correctness-design.md) · Plan: [`plans/…-sp6-ui-correctness.md`](plans/2026-07-22-sp6-ui-correctness.md)

- [x] **M3** — Admin bulk actions: read `is_admin` from `main_window`, not the splitter parent.
- [x] **M4** — Add `on_advanced_search_result` to `MainWindow` (or emit a signal).
- [x] **M5** — Bound/clear `gif_movies` and the icon cache; disconnect `frameChanged`.
- [x] **M6** — Video player config: use `Config.get/set`, not `isinstance(dict)`.
- [x] **M7** — MediaInfoPopup: detect video/sequence by extension, not a nonexistent `type`.
- [x] **M13** — SettingsPanel reset: delete old layout before rebuilding.
- [x] **L2** — Wire `BatchEditDialog` into the bulk menu (depends on SP1's DB methods).
- [x] **SP4 handoff** — Forced login reset flow for `must_change_password` + GeometryViewer `closeEvent` shutdown wiring.

---

## SP7 — Build, packaging & deployment
Spec: [`specs/…-sp7-packaging-design.md`](specs/2026-07-22-sp7-packaging-design.md) · Plan: [`plans/…-sp7-packaging.md`](plans/2026-07-22-sp7-packaging.md)

- [ ] **M11** — Converge on one packager; remove absolute paths; declare build tool; `.ico` icon; single version source.
- [ ] **M14** — Write logs/config to a per-user writable location; add rotation; init once.
- [ ] Linux packaging path (Win+Linux build).

---

## SP8 — Code quality & consistency
Spec: [`specs/…-sp8-code-quality-design.md`](specs/2026-07-22-sp8-code-quality-design.md) · Plan: [`plans/…-sp8-code-quality.md`](plans/2026-07-22-sp8-code-quality.md)

- [ ] **L4** — Replace bare/blanket excepts and `print` with narrowed exceptions + `logging`.
- [ ] **L10** — Extract shared utils (`_resolve_path`, size-format, dark palette); split god modules.

---

## Cross-SP reconciliation notes (resolve during execution)

The plans were drafted in parallel; these known touch-point overlaps must be handled when sequencing execution. None require re-planning — they are ordering/merge concerns.

1. **Execution order = SP0 → SP1 → SP2 → SP3 → SP4 → SP5 → SP6 → SP7 → SP8.** SP1 must land before SP2/SP6 (they consume its new DB methods `update_element_phash`, `get_elements_with_phash`, `update_element_metadata`, verified to match). SP2 & SP6 mark those consumer tests `xfail(strict)` until SP1 lands — flip them when executing on top of SP1.
2. **`file_lock.py`** is edited by both SP1 (H1 lock-on-release + journal_mode) and SP5 (L7 `TimeoutError` polyfill removal). Do SP1 first; SP5's change is a small header/shim edit that rebases cleanly.
3. **`stax_cli.py`** is edited by SP4 (L9 HTTPS + env token) and SP5 (L7 `urllib2` removal). Coordinate — ideally fold both into whichever runs second.
4. **`nuke_bridge.py`** frame-range parse is touched by SP2 (L8 fileseq hardening) and SP5 (L7 `unicode` shim). Independent lines; SP2 first, SP5 rebases.
5. **`paths` module naming:** SP7 creates `src/paths.py` (per-user app-data/log dirs) and SP8 creates `src/utils/paths.py` (`resolve_path`). Different purpose, but the names are confusable — **decision at execution:** put SP7's under `src/utils/appdirs.py` (recommended) or otherwise disambiguate so there is one obvious "paths" util.
6. **SP4→SP6 handoffs:** SP4 sets `must_change_password` and adds `GeometryViewerServer` shutdown/allow-list, but explicitly hands the **forced-reset dialog** and the GeometryViewer **`closeEvent` wiring** to SP6. Ensure SP6 picks these up (SP6's plan already anticipates the dialog seam).
7. **`human_size` behavior (SP8):** SP8 refines sub-MB formatting to KB/B (≥1 MB output unchanged). Flagged for reviewer veto — confirm acceptable before SP8 execution.
8. **`pyproject.toml`** is edited by SP0 (dev extra), SP2 (`fileseq` dep), SP7 (build system → hatchling, `cx-freeze` build extra, drop `pyinstaller`). Merge these additively; SP7's build-system change is the most structural — apply carefully and re-run SP0's CI afterward.

---

## Enhancement Program (EP1–EP9)

Feature-expansion program derived from [`STAX_FEATURE_ENHANCEMENT_REPORT.md`](../../STAX_FEATURE_ENHANCEMENT_REPORT.md). Builds **on top of** SP0–SP8 (does not duplicate the half-built-feature activation, which SP1/SP2/SP6 own). Brainstormed one EP at a time.

| EP | Theme | Spec | Plan | Impl | Report features |
|----|-------|:----:|:----:|:----:|-----------------|
| EP1 | Curation primitives | ☑ | ☑ | ☐ | F013, F014, F052, F053 |
| EP2 | Search & discovery UX (non-AI) | ☑ | ☑ | ☐ | F007–F012, facets |
| EP3 | Browse productivity shell | ☑ | ☑ | ☐ | F049–F058 |
| EP4 | Metadata schema & automation | ☑ | ☑ | ☐ | F015, F016, F018–F022 |
| EP5 | Review, notes & approval | ☐ | ☐ | ☐ | F023–F030 |
| EP6 | Ingestion automation & job queue | ☑ | ☑ | ☐ | F031–F040 |
| EP7 | AI discovery (local-only) | ☑ | ☑ | ☐ | F001–F004 (+auto-tag) |
| EP8 | Team collaboration (sync first) | ☑ | ☑ | ☐ | F041–F043 |
| EP9 | Analytics & ops dashboards | ☑ | ☑ | ☐ | F059, F060, F063 |

> **EP5 (Review, notes & approval) is the only remaining unplanned EP** — deferred by request; resume its brainstorm when ready. EP6–EP9 were batch-drafted with locked decisions (EP6 polling watch-folders + wraps SP2 workers; EP7 local-only AI; EP8 metadata-sync-first, bridges deferred; EP9 available-data dashboards).

### EP1 — Curation primitives
Spec: [`specs/…-ep1-curation-primitives-design.md`](specs/2026-07-23-ep1-curation-primitives-design.md) · Plan: [`plans/…-ep1-curation-primitives.md`](plans/2026-07-23-ep1-curation-primitives.md) · **Depends on SP1 + SP6.**

- [ ] Task 1 — Schema: rating + label_fk columns, labels table, seeded palette
- [ ] Task 2 — DB API: rating methods (validated)
- [ ] Task 3 — DB API: label methods + labels CRUD (SET NULL on delete)
- [ ] Task 4 — `EmptyStateWidget`
- [ ] Task 5 — `MultiSelectActionTray`
- [ ] Task 6 — Grid badges + hover quick-edit
- [ ] Task 7 — Table Rating/Label columns
- [ ] Task 8 — Admin-gated Labels settings tab
- [ ] Task 9 — Wire tray + empty states into MediaDisplayWidget

### EP2 — Search & discovery UX
Spec: [`specs/…-ep2-search-discovery-design.md`](specs/2026-07-23-ep2-search-discovery-design.md) · Plan: [`plans/…-ep2-search-discovery.md`](plans/2026-07-23-ep2-search-discovery.md) · **Depends on EP1 + SP1.** Clusters: 2A facets · 2B persistence · 2C text-quality (trimmable).

- [ ] Task 1 — `FilterSpec` model
- [ ] Task 2 — Query builder (`search_elements_advanced` + count)
- [ ] Task 3 — `get_facet_counts`
- [ ] Task 4 — `FacetDrawer` (tri-state, negative filters)
- [ ] Task 5 — `FilterChipBar` + result count
- [ ] Task 6 — Wire drawer + chips into MediaDisplayWidget
- [ ] Task 7 — Saved searches (personal) table + CRUD
- [ ] Task 8 — Smart collections (shared) table + CRUD
- [ ] Task 9 — Nav integration (saved searches + smart collections)
- [ ] Task 10 — Synonyms table + `expand_terms`
- [ ] Task 11 — difflib `suggest_correction` + capped recent searches
- [ ] Task 12 — Wire did-you-mean + synonym expansion + recent completer
- [ ] Task 13 — Admin Search settings tab (synonyms + smart collections)

### EP3 — Browse productivity shell
Spec: [`specs/…-ep3-browse-productivity-design.md`](specs/2026-07-23-ep3-browse-productivity-design.md) · Plan: [`plans/…-ep3-browse-productivity.md`](plans/2026-07-23-ep3-browse-productivity.md) · **Depends on EP1 + SP1/SP2/SP6.** Clusters: 3A interaction · 3B inspector/loading · 3C shell polish (trimmable).

- [ ] Task 1 — Command harvesting + registry + fuzzy filter
- [ ] Task 2 — `CommandPalette` dialog + Ctrl+K
- [ ] Task 3 — Spacebar quicklook overlay
- [ ] Task 4 — Keyboard help overlay (`?`)
- [ ] Task 5 — Extract shared metadata formatting (`metadata_format.py`)
- [ ] Task 6 — `InspectorPanel` + right-pane vertical split
- [ ] Task 7 — Skeleton placeholders + scroll retention
- [ ] Task 8 — Layout presets (Browse/Review/Ingest/Curation)
- [ ] Task 9 — Accessibility (contrast/text-scale/focus)
- [ ] Task 10 — Onboarding checklist
- [ ] Task 11 — `get_recent_elements` + minimal start page

> **Cross-note (EP3 ↔ SP8):** EP3 Task 5 adds `src/ui/metadata_format.py::human_size`; SP8 (L10) adds `src/utils/formatting.py::human_size`. When both land, converge on one — have EP3's module import SP8's util (or vice-versa) so there is a single size formatter.

### EP4 — Metadata schema & automation
Spec: [`specs/…-ep4-metadata-schema-design.md`](specs/2026-07-23-ep4-metadata-schema-design.md) · Plan: [`plans/…-ep4-metadata-schema.md`](plans/2026-07-23-ep4-metadata-schema.md) · **Depends on SP1 + SP2 + EP1/EP3.** Clusters: 4A schema · 4B templates/auto-tag · 4C rules/links.

- [ ] Task 1 — Schema tables (fields, EAV values, defaults)
- [ ] Task 2 — Value coercion helpers (`metadata_rules.py`)
- [ ] Task 3 — Field CRUD + validation
- [ ] Task 4 — EAV values + inheritance resolution
- [ ] Task 5 — `CustomFieldsWidget` + edit/inspector integration
- [ ] Task 6 — Admin metadata-fields manager tab
- [ ] Task 7 — Metadata templates + `apply_template`
- [ ] Task 8 — Auto-tag rules + pure `evaluate_autotag`
- [ ] Task 9 — Ingest hook (auto-tag + derived fields)
- [ ] Task 10 — Automation manager tab + ingest template picker
- [ ] Task 11 — Quality rules + `check_element_quality`
- [ ] Task 12 — Health panel dock
- [ ] Task 13 — Naming assistant (`suggest_name`)
- [ ] Task 14 — Element relationships table + API
- [ ] Task 15 — Inspector Related section

> **Cross-note (EP4 ↔ SP2):** EP4 Task 9 adds an additive auto-tag hook to `ingestion_core.ingest_file`, which SP2 (C4) also rewrites (async ingest). Apply EP4's hook on top of SP2's rewritten `ingest_file`, not the pre-SP2 version. `ON CONFLICT … DO UPDATE` upserts require SQLite ≥ 3.24 (bundled with Python 3.9 on Win/Linux); fall back to SELECT-then-write on older SQLite.

### EP6 — Ingestion automation & job queue
Spec: [`specs/…-ep6-ingestion-automation-design.md`](specs/2026-07-23-ep6-ingestion-automation-design.md) · Plan: [`plans/…-ep6-ingestion-automation.md`](plans/2026-07-23-ep6-ingestion-automation.md) · **Depends on SP2 + SP3 + EP4.** Clusters: 6A queue/retry/notify · 6B watch/recipes/dup-policy/preflight · 6C proxy profiles/action-chains (trimmable). 14 tasks. Polling watch-folders (no watchdog); durable `ingest_jobs` ledger wraps SP2's `IngestWorker`/`PreviewWorker`; action chains use whitelisted handlers (never `exec()`).

### EP7 — AI discovery (local-only)
Spec: [`specs/…-ep7-ai-discovery-design.md`](specs/2026-07-23-ep7-ai-discovery-design.md) · Plan: [`plans/…-ep7-ai-discovery.md`](plans/2026-07-23-ep7-ai-discovery.md) · **Depends on SP1 + SP2 + EP1/EP2.** `Embedder` abstraction (local CLIP ViT-B/32 via **onnxruntime CPU**, ~120–170 MB first-run download) + `FakeEmbedder` for tests; SQLite embeddings + brute-force numpy cosine; semantic/visual/similar + color search + human-in-the-loop auto-tag. F005 (transcript) / F006 (scene descriptors) deferred.

### EP8 — Team collaboration (metadata sync first)
Spec: [`specs/…-ep8-team-collaboration-design.md`](specs/2026-07-23-ep8-team-collaboration-design.md) · Plan: [`plans/…-ep8-team-collaboration.md`](plans/2026-07-23-ep8-team-collaboration.md) · **Depends on SP1 + SP4 + EP4.** Clusters: 8A granular roles · 8B activity feed · 8C `.staxbundle` metadata/preview export-import (newest-wins). `CollaborationConnector` ABC seam; Kitsu/Ftrack/Flow/DCC (F044–F048) deferred behind it.

### EP9 — Analytics & ops dashboards
Spec: [`specs/…-ep9-analytics-dashboards-design.md`](specs/2026-07-23-ep9-analytics-dashboards-design.md) · Plan: [`plans/…-ep9-analytics-dashboards.md`](plans/2026-07-23-ep9-analytics-dashboards.md) · **Depends on SP1 (+EP2/EP4).** Extends `AnalyticsPanel` (reuses `_BarChart`, no plotting libs) with Search + Storage tabs (`search_events` table, `get_storage_stats`/`get_duplicate_stats`). F061 (ingest throughput→EP6) / F062 (review cycle→EP5) / F064 (underused) deferred.

> **Cross-note (EP7 dependency):** EP7 adds `onnxruntime` — the **only new heavy pip dependency** in the whole enhancement program — plus a first-run model download. Every AI path guards for a missing embedder and degrades gracefully, so the rest of StaX is unaffected if it's not installed.
> **Cross-note (EP8 ↔ admin gating):** EP8's granular `has_permission`/`check_permission` supersede the binary `check_admin_permission` used by EP1/EP2/EP4/EP6 admin-gated surfaces. When EP8 lands, migrate those surfaces to the granular gate (a `check_admin_permission` shim mapping to `can_manage_*` keeps them working in the interim).
> **Cross-note (EP6 ↔ EP4 ↔ SP2 ingest):** EP6 recipes, EP4 auto-tag, and SP2's async rewrite all touch `ingest_file`. Land SP2 first, then layer EP4's hook, then EP6's recipe/proxy options — all additive.

---

## Deferred / future (not a bug fix — tracked separately)

- [ ] Qt.py migration for PySide6 / Nuke 16 forward-compat (see report §7).
- [ ] Strategic building blocks: OpenAssetIO, OpenRV/DJV review, USD, Kitsu/ftrack bridge (report §6–§7).
- [ ] Differentiators: AI auto-tagging, visual/similarity search (report §6 gaps #1–2).
