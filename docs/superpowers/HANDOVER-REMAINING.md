# Handover — Remaining Execution Batches (EP1–EP4, EP6–EP9)

> Follows `HANDOVER-SP0-SP1.md` (Batch 1). Execute batches **in order**; each
> batch is one Claude Code session. To run a batch, paste its block into a fresh
> session opened at `e:\Scripts\Stax`. Every block says to read
> **§Common Execution Rules** below first — start there.
>
> **Remediation (Batches 1–4 / SP0–SP8) is COMPLETE and merged to `main`.**
> Batch 5 is the next thing to run. Read **§State on `main`** before starting it.

## Batching overview

| Batch | Sub-projects | Why grouped | Approx. tasks | Status |
|---|---|---|---|---|
| 1 | SP0 + SP1 | test harness → DB consolidation | ~9 + ~9 | ☑ done |
| 2 | SP2 + SP3 | async pipeline + ffmpeg/cross-platform (media core) | ~large | ☑ done |
| 3 | SP4 + SP5 | security hardening + Nuke integration | ~6 + ~5 | ☑ done |
| 4 | SP6 + SP7 + SP8 | UI fixes + packaging + code-quality (finalize remediation) | ~7 + ~small | ☑ done |
| 5 | EP1 + EP2 | curation primitives + search/discovery (enhancement foundation) | 9 + 13 | **← next** |
| 6 | EP3 | browse productivity shell (solo — large) | 11 | ☐ |
| 7 | EP4 | metadata schema & automation (solo — largest) | 15 | ☐ |
| 8 | EP6 | ingestion automation & job queue (solo — large) | 14 | ☐ |
| 9 | EP7 | AI discovery, local-only (solo — adds a dependency) | large | ☐ |
| 10 | EP8 | team collaboration (solo — large) | large | ☐ |
| 11 | EP9 | analytics dashboards (small) | small | ☐ |

Canonical order and all cross-project reconciliation items live in
`docs/superpowers/CROSS_PLAN_REVIEW.md` (§6 order, §7 checklist). Live task
status is `docs/superpowers/IMPLEMENTATION_PROGRESS.md`.

---

## §State on `main` (as of Batch 4 completion)

Everything below is **already true** — don't redo it, but do rely on it.

**Suite:** `186 passed, 0 failed, 0 xfailed` on the default gate. Every `xfail`
placed by SP0/SP2/SP6 for a not-yet-delivered dependency has been flipped to a
real pass. **A new xfail or a drop below 186 passed is a regression.**

**Test environment — read this first or you will waste a session.** Neither the
system Python nor the repo's `.venv` has `pytest-qt`/`flask`; `.venv` is the app
runtime env and must not be re-synced (`uv sync` would prune `trimesh`,
`pygltflib`, `pyrender`, `PyOpenGL`, which the GLB pipeline needs). Batch 4
created a separate dev env. Use it:

```powershell
# already exists; recreate only if missing
uv venv --python 3.9 .venv-dev
uv pip install --python .venv-dev\Scripts\python.exe -e ".[dev,build]"

# the command to run for every verification step
.venv-dev\Scripts\python.exe -m pytest -m "not manual and not slow" -q
```

**Import-order landmine (still present, now guarded).** `src/ui/__init__.py`
eagerly imports `src.ui.drag_gallery_view`, which imports the flat `ui` package.
Whichever of `ui` / `src.ui` loads first decides whether that resolves. Rules:

- **In tests, import widgets flat** — `from ui.media_display_widget import ...`,
  not `from src.ui...`. Flat is what the existing gui tier does; `src.ui.*` in a
  test that runs standalone raises `ImportError: cannot import name
  'DragGalleryView'`.
- `tests/unit/test_entrypoints_importable.py` imports `main` and
  `nuke_launcher` in a **fresh interpreter**. If it goes red, an entry point is
  broken for real users even though the rest of the suite is green.

**Landed in Batch 4 beyond the plans** (all committed, don't re-litigate):

- `src/utils/appdirs.py` — SP7's per-user dir resolver (was `src/paths.py`);
  `src/utils/paths.py` is SP8's `resolve_path`. Tests: `test_appdirs.py`,
  `test_utils_paths.py`. Resolves CROSS_PLAN_REVIEW §4.3.
- `src/utils/formatting.py::human_size` — canonical size formatter (§4.2). The
  sub-MB refinement (512 KB → `512.0 KB`, was `0.5 MB`) was **accepted**; ≥1 MB
  output is byte-identical to before.
- `setup_freeze.py` excludes `PySide2.QtQml/QtQuick/QtQuickWidgets`. Without it
  cx_Freeze's qtqml hook asks `QLibraryInfo` for the Qt6-only `QmlImportsPath`
  and aborts the entire build with `KeyError` (reproduced on cx_Freeze 7.2.7 and
  8.4.1). **Do not remove.** `tests/manual/test_freeze_smoke.py` verifies a real
  build and passes.
- `main.py` / `nuke_launcher.py` circular-import fix (see landmine above) — they
  had been unimportable since SP2's `0767192`.
- `MediaDisplayWidget._populate_bulk_menu` / `_dispatch_bulk_action` — one bulk
  menu builder. **Add new bulk actions there**, not in `show_context_menu` /
  `show_bulk_menu`.
- The god-module split remains **deferred** (SP8 design §4.6). Keep it that way.

**Git state.** `main` contains all of SP0–SP8. It has **diverged from
`origin/main`: ahead 107, behind 1** — the 1 is merge commit `4aad404`, whose
content is already present (both parents are in history); only the merge node is
missing. A plain `git push` will be rejected until someone reconciles
(`git merge origin/main`). **That reconciliation and any push are the human's
call — do not do either unprompted.**

---

## §Common Execution Rules

Read these before any batch, then follow the batch block.

- **Method:** Invoke `superpowers:subagent-driven-development` — one fresh subagent per plan task, two-stage review between tasks, strict TDD, tasks in written order.
- **Read first each session:** `CLAUDE.md` (stack, flat imports, tiers, landmines), **§State on `main`** above, the specs+plans named in the batch, and `CROSS_PLAN_REVIEW.md` §6–§7.
- **Branch:** create a working branch off **`main`** named for the batch — `git checkout -b exec/<batch>` (`exec/ep1-ep2`, `exec/ep3`, …). Confirm the previous batch is present on `main` first. (Batches 1–4 used `uv` as the base; that is historical — `main` is now the trunk.)
- **TDD, verbatim:** failing test → confirm fail → implement → confirm pass → commit (conventional-commit messages). **Never weaken/delete a test to pass**; where a step says `xfail(strict)`, do that with the stated reason; otherwise fix the root cause.
- **Headless:** GUI tests run with `QT_QPA_PLATFORM=offscreen`; Nuke is mocked. Python 3.9, `uv`, Windows/Linux.
- **Test command:** `.venv-dev\Scripts\python.exe -m pytest -m "not manual and not slow" -q` (see §State — the other envs lack `pytest-qt`).
- **After each task:** suite green. **After each sub-project:** full suite; report pass/xfail counts. Baseline entering Batch 5 is **186 passed, 0 failed, 0 xfailed** — going below that, or introducing an unplanned xfail, is a regression to fix, not to accept.
- **Test imports are flat** (`from ui.x import Y`, `from utils.paths import ...`) — see the import-order landmine in §State.
- **Adapt names, don't guess:** if a plan references a local method/name that differs from the real code, read the file and adapt (plans flag these). Report anything you can't reconcile.
- **Tracker:** tick each task box in `docs/superpowers/IMPLEMENTATION_PROGRESS.md`; set the sub-project's `Impl` to ☑ when complete.
- **Outward-facing actions need explicit human approval:** never `git push`, open a PR, change branch protection, add a new pip dependency that downloads large artifacts, or delete/merge onto `main` without asking. Commit locally and pause.
- **Between sub-projects and at batch end:** report a summary and wait for the human before proceeding past the batch or merging.

---

## Batches 2–4 — SP2…SP8 (COMPLETE)

Landed and merged to `main`. Kept for provenance only; details in
`IMPLEMENTATION_PROGRESS.md` and the per-SP plans.

- **Batch 2 — SP2 + SP3:** async ingest/preview (`IngestWorker`, `PreviewWorker`,
  `LazyGalleryView`), dedup wired, `fileseq` frame ranges; `ffmpeg_wrapper`
  platform binary selection + timeouts + no ffplay pipe deadlock.
- **Batch 3 — SP4 + SP5:** pbkdf2 auth, no default admin, path-restricted
  processor hooks, checksummed ffmpeg download, GeometryViewer allow-list,
  constant-time API token, HTTPS CLI; Nuke panel singleton, scoped DebugManager,
  absolute plugin paths, Py2 shims gone.
- **Batch 4 — SP6 + SP7 + SP8:** the seven UI-correctness bugs + batch-edit
  wiring + SP4's deferred forced-reset/`closeEvent` handoff; cx_Freeze-only
  packaging with per-user rotating logs and a single version source; shared
  `resolve_path`/`human_size`/palette/bulk-menu extraction and L4 logging. Plus
  the three out-of-plan fixes recorded in §State (cx_Freeze QML exclusion,
  entry-point circular import, stale `StaX.spec`).

---

## Batch 5 — EP1 + EP2 (enhancement foundation) ← **NEXT**

Apply §Common Execution Rules and §State on `main`. Branch: `exec/ep1-ep2`.

Execute in order:
1. `docs/superpowers/plans/2026-07-23-ep1-curation-primitives.md`
2. `docs/superpowers/plans/2026-07-23-ep2-search-discovery.md`

Watch-outs:
- Both add tabs to `settings_panel.py` — the real signature is `SettingsPanel(config, db_manager, main_window=None, parent=None)` (already corrected in the plans). Append each tab in `setup_ui`.
- EP2's query builder + facets **consume EP1's `rating`/`label_fk` columns** — do EP1 first.
- EP2 adds `recent_searches`; EP9 later adds `search_events` for analytics. Optional convergence noted in CROSS_PLAN_REVIEW §4.4 — fine to leave separate for now.
- **Schema changes go through SP1's versioned migration runner** in `src/db_manager.py` — add a new numbered migration, never hand-edit `_create_schema` alone, and never target the orphaned capitalized `Stacks`/`Elements` tables.
- **New bulk/context actions go in `MediaDisplayWidget._populate_bulk_menu` + `_dispatch_bulk_action`** (SP8), not in the two menu methods.
- Admin gating currently uses the binary `check_admin_permission`; EP8 later replaces it with granular roles behind a shim. Use `check_admin_permission` now.

Done when: team ratings + admin label palette + action tray + empty states live; faceted drawer/chips/count, saved searches, smart collections, synonyms/fuzzy/recent working. Full suite green (≥186 passed, 0 failed, no new xfail).

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
- Ships only dashboards whose data exists (top-used, search success, storage hygiene). **No dead panels** — ingest-throughput (needs EP6) and review-cycle (needs EP5, which is unplanned) stay deferred.
- Optionally converge EP2 `recent_searches` + EP9 `search_events` into one search-log write path (§4.4) — not required.

Done when: top-used, search-success, and storage-hygiene dashboards + CSV export live. Full suite green. **Enhancement program complete** as scoped (EP5 remains unplanned — see "Final state" below).

---

## Final state after all batches

Remediation SP0–SP8 and enhancements EP1–EP4, EP6–EP9 implemented, each on its
`exec/*` branch, merged into `main` in order (merges gated on human approval).
Keep `IMPLEMENTATION_PROGRESS.md` current as the single source of truth.

**EP5 (Review, notes & approval) has no spec and no plan.** This document
previously called it "cancelled" while `IMPLEMENTATION_PROGRESS.md` calls it
"deferred by request — resume its brainstorm when ready." Treat it as
**deferred, not cancelled**: it is simply not in any batch, and building it
would need a brainstorm + spec + plan first. EP9 correspondingly defers the
review-cycle dashboard (F062).

---

## Ready-to-copy prompt — Batch 5 (EP1 + EP2)

Paste the block below verbatim into a fresh Claude Code session opened at
`e:\Scripts\Stax`.

````text
Execute Batch 5 (EP1 + EP2) of the StaX enhancement program.

Read these first, in this order, before doing anything else:
1. CLAUDE.md
2. docs/superpowers/HANDOVER-REMAINING.md — especially "§State on main" and
   "§Common Execution Rules"
3. docs/superpowers/CROSS_PLAN_REVIEW.md §6-§7
4. docs/superpowers/specs/2026-07-23-ep1-curation-primitives-design.md
5. docs/superpowers/plans/2026-07-23-ep1-curation-primitives.md
6. docs/superpowers/specs/2026-07-23-ep2-search-discovery-design.md
7. docs/superpowers/plans/2026-07-23-ep2-search-discovery.md

Method: use the superpowers:subagent-driven-development skill — one fresh
subagent per plan task, strict TDD (failing test -> confirm red -> implement ->
confirm green -> conventional commit), tasks in written order. Never weaken or
delete a test to make it pass.

Setup:
- Branch off main: git checkout -b exec/ep1-ep2
- Test command (the repo's .venv does NOT have pytest-qt; do not `uv sync` it):
      .venv-dev\Scripts\python.exe -m pytest -m "not manual and not slow" -q
  If .venv-dev is missing, create it:
      uv venv --python 3.9 .venv-dev
      uv pip install --python .venv-dev\Scripts\python.exe -e ".[dev,build]"
- Baseline is 186 passed, 0 failed, 0 xfailed. Anything below that, or any new
  unplanned xfail, is a regression to fix — not to accept.

Order: EP1 fully (9 tasks), then EP2 (13 tasks). EP2's query builder and facets
consume EP1's rating/label_fk columns, so EP1 must land first.

Repo-specific rules that override habit:
- Tests import flat: `from ui.media_display_widget import MediaDisplayWidget`,
  `from utils.paths import resolve_path`. Importing `src.ui.*` in a test that
  runs standalone raises a circular-import ImportError.
- Schema changes go through the versioned migration runner in src/db_manager.py
  as a new numbered migration. Never target the orphaned capitalized
  Stacks/Elements/InsertionLog tables — the live schema is lowercase.
- New bulk/context menu actions go in MediaDisplayWidget._populate_bulk_menu and
  _dispatch_bulk_action, not in show_context_menu / show_bulk_menu.
- SettingsPanel(config, db_manager, main_window=None, parent=None) — append new
  tabs inside setup_ui.
- Admin gating uses check_admin_permission for now (EP8 later swaps in granular
  roles behind a shim).
- Use logging, never print. Keep the media_display_widget god-module split
  deferred.
- Do not remove the PySide2.QtQml/QtQuick excludes in setup_freeze.py — they are
  what keeps the cx_Freeze build from aborting.

Tracker: tick each task box in docs/superpowers/IMPLEMENTATION_PROGRESS.md and
set the EP's Impl to done when it is complete.

Stop and ask before: git push, opening a PR, merging to main, adding any new pip
dependency, or deviating from a plan step. Commit locally and pause with a
summary between EP1 and EP2, and again at the end of the batch.
````
