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
| SP0 | Test harness & CI foundation | ☑ | ☑ | ☐ | (test-coverage gap) |
| SP1 | Database consolidation & concurrency | ☑ | ☑ | ☐ | C1, H1, H3, M1, L6, L11 |
| SP2 | Async ingestion & preview pipeline | ☑ | ☑ | ☐ | C4, H7, M12, L8, L5 |
| SP3 | FFmpeg/media hardening & cross-platform | ☑ | ☑ | ☐ | H4, M8, M9, M10 |
| SP4 | Security hardening | ☑ | ☑ | ☐ | C2, C3, H2, H6, M2, L9 |
| SP5 | Nuke integration & embedded-mode | ☑ | ☑ | ☐ | H5, H8, L1, L3, L7 |
| SP6 | UI correctness & memory | ☑ | ☑ | ☐ | M3, M4, M5, M6, M7, M13, L2 |
| SP7 | Build, packaging & deployment | ☑ | ☑ | ☐ | M11, M14 |
| SP8 | Code quality & consistency | ☑ | ☑ | ☐ | L4, L10 |

**All specs and plans are written** (`docs/superpowers/specs/` and `plans/`). Execution has not started. See "Cross-SP reconciliation notes" at the bottom before executing.

---

## SP0 — Test harness & CI foundation
Spec: [`specs/2026-07-22-sp0-test-harness-ci-design.md`](specs/2026-07-22-sp0-test-harness-ci-design.md) ·
Plan: [`plans/2026-07-22-sp0-test-harness-ci.md`](plans/2026-07-22-sp0-test-harness-ci.md)

- [ ] Task 1 — Restructure `tests/` into unit/gui/nuke tiers, archive scratch
- [ ] Task 2 — Add dev dependencies (`pytest-qt`, `pytest-mock`, `pytest-cov`, `flask`)
- [ ] Task 3 — Rewrite `conftest.py` around the real `DatabaseManager`
- [ ] Task 4 — Update `pytest.ini` (testpaths, strict markers)
- [ ] Task 5 — Characterization tests: SequenceDetector & Config
- [ ] Task 6 — Characterization tests: PreviewCache & FileLockManager
- [ ] Task 7 — Nuke-tier smoke: NukeBridge mock mode
- [ ] Task 8 — GUI-tier smoke tests (strict `xfail` for C1)
- [ ] Task 9 — GitHub Actions CI + branch protection

---

## SP1 — Database consolidation & concurrency
Spec: [`specs/…-sp1-database-consolidation-design.md`](specs/2026-07-22-sp1-database-consolidation-design.md) · Plan: [`plans/…-sp1-database-consolidation.md`](plans/2026-07-22-sp1-database-consolidation.md)

- [ ] **C1** — Merge the two DB layers into one `DatabaseManager`; single versioned migration runner; wire analytics/API/batch-edit; write `ingestion_history`/insertion log. Flip SP0's C1 `xfail` smoke tests to pass.
- [ ] **H1** — Fix lock-file delete-on-release race; switch WAL→DELETE/TRUNCATE on network shares.
- [ ] **H3** — Remove duplicated, signature-swapped favorite methods; single canonical signature.
- [ ] **M1** — Whitelist column names in `search_elements` / `update_element` (kill SQL-format injection).
- [ ] **L6** — Scope the external lock to writes; allow concurrent readers; reuse per-thread connection.
- [ ] **L11** — Playlist migration: verify row counts, raise on mismatch (no silent data loss).

---

## SP2 — Async ingestion & preview pipeline
Spec: [`specs/…-sp2-async-pipeline-design.md`](specs/2026-07-22-sp2-async-pipeline-design.md) · Plan: [`plans/…-sp2-async-pipeline.md`](plans/2026-07-22-sp2-async-pipeline.md)

- [ ] **C4** — Wire `PreviewWorker` + `LazyGalleryView`; move ingestion off the GUI thread.
- [ ] **H7** — Drop-ingest: pass `config.get_all()`, use `default_copy_policy`, hold thread reference.
- [ ] **M12** — Decode EXR/DPX via **OpenImageIO**; derive padding from detected sequence, not `%04d`.
- [ ] **L8** — Replace/harden frame-range parsing with **Fileseq**.
- [ ] **L5** — Wire duplicate detection into ingest; fix MD5-fallback distance semantics.

---

## SP3 — FFmpeg/media hardening & cross-platform
Spec: [`specs/…-sp3-ffmpeg-cross-platform-design.md`](specs/2026-07-22-sp3-ffmpeg-cross-platform-design.md) · Plan: [`plans/…-sp3-ffmpeg-cross-platform.md`](plans/2026-07-22-sp3-ffmpeg-cross-platform.md)

- [ ] **H4** — Select ffmpeg binary names by platform (Win `.exe` / Linux) — unblock Linux.
- [ ] **M8** — Per-call temp palette file for GIF two-pass (no shared `palette.png` race).
- [ ] **M9** — Add `timeout=` to all ffmpeg subprocess calls; handle `TimeoutExpired`.
- [ ] **M10** — Fix ffplay PIPE deadlock (`DEVNULL` / drain); `CREATE_NO_WINDOW` on Windows.

---

## SP4 — Security hardening
Spec: [`specs/…-sp4-security-hardening-design.md`](specs/2026-07-22-sp4-security-hardening-design.md) · Plan: [`plans/…-sp4-security-hardening.md`](plans/2026-07-22-sp4-security-hardening.md)

- [ ] **C2** — Sandbox/restrict processor `exec()` to an admin-owned dir; validate paths; drop "safe" claim.
- [ ] **C3** — Pin + checksum ffmpeg download; sanitize archive extraction (Zip-Slip).
- [ ] **H2** — Salted KDF (pbkdf2/bcrypt/argon2); eliminate default `admin/admin`; force reset.
- [ ] **H6** — GeometryViewer: allow-list served files; reject paths outside previews root; shutdown hook.
- [ ] **M2** — API: `hmac.compare_digest` token check; ingest-path allowlist.
- [ ] **L9** — CLI: support HTTPS; prefer `STAX_API_TOKEN` env over `--token` in argv.

---

## SP5 — Nuke integration & embedded-mode
Spec: [`specs/…-sp5-nuke-integration-design.md`](specs/2026-07-22-sp5-nuke-integration-design.md) · Plan: [`plans/…-sp5-nuke-integration.md`](plans/2026-07-22-sp5-nuke-integration.md)

- [ ] **H5** — `menu.py` commands must target the live `StaXPanel` (singleton), not a pane result.
- [ ] **H8** — Scope stdout/stderr suppression to StaX; never swallow `stderr` in Nuke.
- [ ] **L1** — `init.py`: add absolute plugin paths (`os.path.join(stax_root, subdir)`).
- [ ] **L3** — Delete orphaned `nuke_bridge_patch.py`.
- [ ] **L7** — Remove Python-2.7 claims/shims; state single interpreter.

---

## SP6 — UI correctness & memory
Spec: [`specs/…-sp6-ui-correctness-design.md`](specs/2026-07-22-sp6-ui-correctness-design.md) · Plan: [`plans/…-sp6-ui-correctness.md`](plans/2026-07-22-sp6-ui-correctness.md)

- [ ] **M3** — Admin bulk actions: read `is_admin` from `main_window`, not the splitter parent.
- [ ] **M4** — Add `on_advanced_search_result` to `MainWindow` (or emit a signal).
- [ ] **M5** — Bound/clear `gif_movies` and the icon cache; disconnect `frameChanged`.
- [ ] **M6** — Video player config: use `Config.get/set`, not `isinstance(dict)`.
- [ ] **M7** — MediaInfoPopup: detect video/sequence by extension, not a nonexistent `type`.
- [ ] **M13** — SettingsPanel reset: delete old layout before rebuilding.
- [ ] **L2** — Wire `BatchEditDialog` into the bulk menu (depends on SP1's DB methods).

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
| EP2 | Search & discovery UX (non-AI) | ☐ | ☐ | ☐ | F007–F012, facets |
| EP3 | Browse productivity shell | ☐ | ☐ | ☐ | F049–F058 |
| EP4 | Metadata schema & automation | ☐ | ☐ | ☐ | F015, F016, F018–F022 |
| EP5 | Review, notes & approval | ☐ | ☐ | ☐ | F023–F030 |
| EP6 | Ingestion automation & job queue | ☐ | ☐ | ☐ | F031–F040 |
| EP7 | AI discovery | ☐ | ☐ | ☐ | F001–F006 |
| EP8 | Collaboration & integrations | ☐ | ☐ | ☐ | F041–F048 |
| EP9 | Analytics & ops dashboards | ☐ | ☐ | ☐ | F059–F064 |

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

---

## Deferred / future (not a bug fix — tracked separately)

- [ ] Qt.py migration for PySide6 / Nuke 16 forward-compat (see report §7).
- [ ] Strategic building blocks: OpenAssetIO, OpenRV/DJV review, USD, Kitsu/ftrack bridge (report §6–§7).
- [ ] Differentiators: AI auto-tagging, visual/similarity search (report §6 gaps #1–2).
