# Handover — Remaining Execution Batches (SP2–SP8, EP1–EP4, EP6–EP9)

> Follows `HANDOVER-SP0-SP1.md` (Batch 1). Execute batches **in order**; each
> batch is one Claude Code session. To run a batch, paste its block into a fresh
> session opened at `d:\Scripts\modern-stock-browser`. Every block says to read
> **§Common Execution Rules** below first — start there.

## Batching overview

| Batch | Sub-projects | Why grouped | Approx. tasks |
|---|---|---|---|
| 1 (done handover) | SP0 + SP1 | test harness → DB consolidation | ~9 + ~9 |
| 2 | SP2 + SP3 | async pipeline + ffmpeg/cross-platform (media core) | ~large |
| 3 | SP4 + SP5 | security hardening + Nuke integration | ~6 + ~5 |
| 4 | SP6 + SP7 + SP8 | UI fixes + packaging + code-quality (finalize remediation) | ~7 + ~small |
| 5 | EP1 + EP2 | curation primitives + search/discovery (enhancement foundation) | 9 + 13 |
| 6 | EP3 | browse productivity shell (solo — large) | 11 |
| 7 | EP4 | metadata schema & automation (solo — largest) | 15 |
| 8 | EP6 | ingestion automation & job queue (solo — large) | 14 |
| 9 | EP7 | AI discovery, local-only (solo — adds a dependency) | large |
| 10 | EP8 | team collaboration (solo — large) | large |
| 11 | EP9 | analytics dashboards (small) | small |

Canonical order and all cross-project reconciliation items live in
`docs/superpowers/CROSS_PLAN_REVIEW.md` (§6 order, §7 checklist). Enhancement
batches (5–11) assume the remediation batches (2–4) have landed.

---

## §Common Execution Rules

Read these before any batch, then follow the batch block.

- **Method:** Invoke `superpowers:subagent-driven-development` — one fresh subagent per plan task, two-stage review between tasks, strict TDD, tasks in written order.
- **Read first each session:** `CLAUDE.md` (stack, flat imports, tiers, landmines), the specs+plans named in the batch, and `CROSS_PLAN_REVIEW.md` §6–§7.
- **Branch:** create a working branch off `uv` named for the batch, e.g. `git checkout -b exec/<batch>` (`exec/sp2-sp3`, `exec/ep1-ep2`, …). Confirm the previous batch's work is present on `uv` first.
- **TDD, verbatim:** failing test → confirm fail → implement → confirm pass → commit (conventional-commit messages). **Never weaken/delete a test to pass**; where a step says `xfail(strict)`, do that with the stated reason; otherwise fix the root cause.
- **Headless:** GUI tests run with `QT_QPA_PLATFORM=offscreen`; Nuke is mocked. Python 3.9, `uv`, Windows/Linux.
- **After each task:** `pytest -m "not manual"` green (expected xfails OK, 0 real failures). **After each sub-project:** full suite; report pass/xfail counts.
- **Adapt names, don't guess:** if a plan references a local method/name that differs from the real code, read the file and adapt (plans flag these). Report anything you can't reconcile.
- **Tracker:** tick each task box in `docs/superpowers/IMPLEMENTATION_PROGRESS.md`; set the sub-project's `Impl` to ☑ when complete.
- **Outward-facing actions need explicit human approval:** never `git push`, open a PR, change branch protection, add a new pip dependency that downloads large artifacts, or delete/merge onto `main` without asking. Commit locally and pause.
- **Between sub-projects and at batch end:** report a summary and wait for the human before proceeding past the batch or merging.

---

## Batch 2 — SP2 + SP3 (media core)

Apply §Common Execution Rules. Branch: `exec/sp2-sp3`. Confirm SP0+SP1 are landed on `uv` first (SP2 needs the consolidated DB + migration runner + `phash` column + insertion-log path).

Execute in order:
1. `docs/superpowers/plans/2026-07-22-sp2-async-pipeline.md`
2. `docs/superpowers/plans/2026-07-22-sp3-ffmpeg-cross-platform.md`

Watch-outs:
- **SP2 rewrites `ingest_file`** (async) and wires `PreviewWorker` + `LazyGalleryView` + duplicate detection; it flips SP0's C4-related expectations. SP2's preview decode routes through `ffmpeg_wrapper` and `fileseq` (added to `pyproject.toml`) — adding `fileseq` is a normal in-plan dep (small, pure-Python); it is fine to add without a special gate.
- **SP2 ↔ SP3 are coupled on `ffmpeg_wrapper.py`.** SP2 uses it; SP3 makes it cross-platform (H4) + adds timeouts/pipe/palette fixes. Do SP2 first per the plan, then SP3; when SP3 lands, re-run SP2's ffmpeg-touching tests to confirm still green on this platform.
- SP2's `ingest_file` is later layered by EP4/EP6/EP7 — leave the hook points clean.

Done when: async ingest/preview live and non-blocking, lazy gallery in use, dedup wired; `ffmpeg_wrapper` selects binaries by platform with timeouts and no ffplay pipe deadlock; full suite green.

---

## Batch 3 — SP4 + SP5 (security + Nuke)

Apply §Common Execution Rules. Branch: `exec/sp4-sp5`. Confirm SP0–SP3 landed.

Execute in order:
1. `docs/superpowers/plans/2026-07-22-sp4-security-hardening.md`
2. `docs/superpowers/plans/2026-07-22-sp5-nuke-integration.md`

Watch-outs:
- **Both edit `tools/stax_cli.py`:** SP4 (L9: HTTPS + `STAX_API_TOKEN`) and SP5 (L7: remove `urllib2` shim). Do SP4's change first, then SP5's shim removal on top — reconcile in one file, don't clobber.
- **SP5 also removes Py2 shims in `file_lock.py`/`nuke_bridge.py`** which SP1/SP2 already touched — rebase onto their current state.
- **SP4 defers two items to SP6 (Batch 4):** the forced-password-reset dialog (`must_change_password`) and the GeometryViewer `closeEvent` wiring. Leave the DB flag/allow-list in place; SP6 adds the UI.
- SP4 password change is **pbkdf2_hmac (stdlib)** — no new dependency. C2 hooks are **restricted to an admin dir**, not sandboxed/Pyblish. C3 pins+checksums the ffmpeg download.

Done when: pbkdf2 auth + no default admin, restricted processor hooks, checksummed/ sanitized installer download, GeometryViewer allow-list + shutdown, constant-time API token + ingest allow-list, HTTPS CLI; Nuke menu targets the live panel singleton, DebugManager no longer swallows stderr, `init.py` uses absolute paths, `nuke_bridge_patch.py` deleted, Py2 claims/shims gone. Full suite green.

---

## Batch 4 — SP6 + SP7 + SP8 (finalize remediation)

Apply §Common Execution Rules. Branch: `exec/sp6-sp7-sp8`. Confirm SP0–SP5 landed.

Execute in order:
1. `docs/superpowers/plans/2026-07-22-sp6-ui-correctness.md`
2. `docs/superpowers/plans/2026-07-22-sp7-packaging.md`
3. `docs/superpowers/plans/2026-07-22-sp8-code-quality.md`

Watch-outs:
- **SP6 picks up SP4's deferred UI:** wire the forced-password-reset dialog and the GeometryViewer `closeEvent` here if the SP6 plan includes them; if not, add them as small follow-on tasks referencing SP4.
- **SP7 packaging:** converge on **cx_Freeze**, delete the PyInstaller specs and `tools/build_installer.py`, single-source the version, fix the `.ico`, move logs/config to per-user dirs. **Rename SP7's app-dirs module to `src/utils/appdirs.py`** (not `src/paths.py`) to avoid clashing with SP8's `src/utils/paths.py` (per CROSS_PLAN_REVIEW §4.3). SP7 changes `pyproject.toml`'s build system — merge carefully; re-run SP0's CI locally after.
- **SP8 code quality:** when creating the shared size formatter, put it at **`src/utils/formatting.py::human_size`** (the canonical home per CROSS_PLAN_REVIEW §4.2); **keep the media_display_widget god-module split DEFERRED** (SP8 already scoped it out) so it doesn't collide with the EP work.

Done when: UI correctness bugs fixed, one packager with per-user writable logs and single version source, shared utils extracted with exceptions→logging. Full suite green. **Remediation complete** — report and wait before starting enhancements.

---

## Batch 5 — EP1 + EP2 (enhancement foundation)

Apply §Common Execution Rules. Branch: `exec/ep1-ep2`. Confirm remediation (SP0–SP8, at least SP1+SP6) landed.

Execute in order:
1. `docs/superpowers/plans/2026-07-23-ep1-curation-primitives.md`
2. `docs/superpowers/plans/2026-07-23-ep2-search-discovery.md`

Watch-outs:
- Both add tabs to `settings_panel.py` — the real signature is `SettingsPanel(config, db_manager, main_window=None, parent=None)` (already corrected in the plans). Append each tab in `setup_ui`.
- EP2's query builder + facets **consume EP1's `rating`/`label_fk` columns** — do EP1 first.
- EP2 adds `recent_searches`; EP9 later adds `search_events` for analytics. Optional convergence noted in CROSS_PLAN_REVIEW §4.4 — fine to leave separate for now.

Done when: team ratings + admin label palette + action tray + empty states live; faceted drawer/chips/count, saved searches, smart collections, synonyms/fuzzy/recent working. Full suite green.

---

## Batch 6 — EP3 (browse productivity shell, solo)

Apply §Common Execution Rules. Branch: `exec/ep3`. Confirm SP0–SP8 + EP1 landed (EP3 also pairs with EP2's surface and SP2's async previews).

Execute: `docs/superpowers/plans/2026-07-23-ep3-browse-productivity.md`

Watch-outs:
- **`human_size` convergence:** EP3 Task 5 creates `src/ui/metadata_format.py`. If SP8 already added `src/utils/formatting.py::human_size`, have `metadata_format.py` **import/re-export it** rather than defining a second copy (CROSS_PLAN_REVIEW §4.2).
- Skeletons are driven by SP2's `preview_ready`; without SP2 they simply don't show (no-op) — but SP2 should be landed by now.
- Extract the shared metadata formatter **after** SP6's M7 popup fix so it reflects corrected type detection.

Done when: command palette, spacebar quicklook, help overlay, sticky inspector, skeletons+scroll retention, layout presets, accessibility, onboarding, minimal start page — all live. Full suite green.

---

## Batch 7 — EP4 (metadata schema & automation, solo — largest)

Apply §Common Execution Rules. Branch: `exec/ep4`. Confirm SP1 + SP2 + EP1 + EP3 landed (EP4 hosts custom-field UI in EP3's inspector and hooks SP2's ingest).

Execute: `docs/superpowers/plans/2026-07-23-ep4-metadata-schema.md`

Watch-outs:
- **Ingest hook layering:** EP4 Task 9 adds an additive auto-tag/field hook to `ingest_file` — apply it **on top of SP2's rewritten** `ingest_file`, not a pre-SP2 version (CROSS_PLAN_REVIEW §4.5).
- **Upserts** (`ON CONFLICT … DO UPDATE`) need SQLite ≥ 3.24 (bundled with Python 3.9 on Win/Linux). If an older SQLite is ever in play, fall back to SELECT-then-write.
- Pure rule logic lives in `src/metadata_rules.py` (Qt/DB-free) — keep it testable in isolation.

Done when: per-stack typed custom fields (EAV) + inheritance, templates, auto-tag at ingest, quality checker + Health dock, naming assistant, relationships — all live. Full suite green.

---

## Batch 8 — EP6 (ingestion automation & job queue, solo — large)

Apply §Common Execution Rules. Branch: `exec/ep6`. Confirm SP2 + SP3 + EP4 landed.

Execute: `docs/superpowers/plans/2026-07-23-ep6-ingestion-automation.md`

Watch-outs:
- The job-queue dashboard **wraps SP2's `IngestWorker`/`PreviewWorker`** — do not build a second queue.
- Watch folders use a **stdlib polling scanner** (no `watchdog` dependency).
- Proxy/transcode profiles overlay SP2's PreviewWorker keys through the SP3 `ffmpeg_wrapper`.
- **Action chains use whitelisted handlers, never `exec()`** (avoids the C2 RCE class).
- Ingest recipes layer on the same `ingest_file` as SP2/EP4 — additive, land after EP4.

Done when: watch folders, recipes, queue dashboard + retry/cancel, proxy profiles, dup policies, preflight, notifications, action chains — all live. Full suite green.

---

## Batch 9 — EP7 (AI discovery, local-only, solo — adds a dependency)

Apply §Common Execution Rules. Branch: `exec/ep7`. Confirm SP1 + SP2 + EP1 + EP2 landed.

Execute: `docs/superpowers/plans/2026-07-23-ep7-ai-discovery.md`

**Stop-and-confirm gate:** EP7 adds **`onnxruntime`** to `pyproject.toml` and downloads a **~120–170 MB CLIP model on first run**. Before adding the dependency or triggering any model download, **PAUSE and confirm with the human**. Until then, implement against the injected `FakeEmbedder` (all unit tests use it; real-model tests are `@pytest.mark.manual`).

Watch-outs:
- **Local-only, no cloud** — every AI code path must guard for a missing embedder (`get_embedder()` returns `None`) and degrade gracefully.
- Embeddings + color histograms are SQLite blobs; similarity is brute-force numpy cosine/L1 (no vector DB).
- Reuse EP2's `FilterSpec`/result surface for AI results. Transcript/scene (F005/F006) are out of scope.

Done when: semantic/visual/similar/color search + human-in-the-loop auto-tag live behind a guarded local embedder; suite green with fakes (real-model tests skipped/manual).

---

## Batch 10 — EP8 (team collaboration, solo — large)

Apply §Common Execution Rules. Branch: `exec/ep8`. Confirm SP1 + SP4 + EP4 landed.

Execute: `docs/superpowers/plans/2026-07-23-ep8-team-collaboration.md`

Watch-outs:
- **Granular roles supersede `check_admin_permission`.** Add a `check_admin_permission` → `can_manage_*` **shim** so EP1/EP2/EP4/EP6/EP7 admin-gated surfaces keep working without edits (CROSS_PLAN_REVIEW §4.6).
- Team sync is **stdlib `zipfile`/`json` `.staxbundle` export/import** (newest-timestamp-wins) — no real-time/cloud sync, no new deps.
- PM/DCC bridges (Kitsu/Ftrack/Flow) are **deferred behind the `CollaborationConnector` seam** — build the seam, ship no live bridge.

Done when: role→permission matrix + gate + admin UI, activity feed + dock, metadata/preview export-import — all live. Full suite green.

---

## Batch 11 — EP9 (analytics dashboards, small)

Apply §Common Execution Rules. Branch: `exec/ep9`. Confirm SP1 (+ EP2, EP4) landed.

Execute: `docs/superpowers/plans/2026-07-23-ep9-analytics-dashboards.md`

Watch-outs:
- EP9 extends the existing `AnalyticsPanel` and reuses its `_BarChart` — **no plotting libraries**.
- Ships only dashboards whose data exists (top-used, search success, storage hygiene). **No dead panels** — ingest-throughput (needs EP6) and review-cycle (EP5, cancelled) stay deferred.
- Optionally converge EP2 `recent_searches` + EP9 `search_events` into one search-log write path (§4.4) — not required.

Done when: top-used, search-success, and storage-hygiene dashboards + CSV export live. Full suite green. **Enhancement program complete** (EP5 was cancelled).

---

## Final state after all batches

Remediation SP0–SP8 and enhancements EP1–EP4, EP6–EP9 implemented, each on its
`exec/*` branch, merged into `uv` in order (merges gated on human approval).
EP5 is intentionally not built. Keep `IMPLEMENTATION_PROGRESS.md` current as the
single source of truth.
