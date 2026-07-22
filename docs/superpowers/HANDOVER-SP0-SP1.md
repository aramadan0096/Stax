# Handover — Execute SP0 then SP1 (subagent-driven)

> Paste the block below into a fresh Claude Code session opened at
> `d:\Scripts\modern-stock-browser`. It executes the SP0 and SP1 implementation
> plans, in order, task-by-task, using the subagent-driven-development skill.

---

You are implementing the first two sub-projects of the StaX audit-remediation program. Work on branch `uv` — first create a working branch off it: `git checkout -b exec/sp0-sp1`.

**Method:** Invoke the `superpowers:subagent-driven-development` skill and follow it — one fresh subagent per plan task, two-stage review between tasks, TDD. Do the tasks strictly in the order written.

**Execute in this order:**
1. `docs/superpowers/plans/2026-07-22-sp0-test-harness-ci.md` — all 9 tasks.
2. `docs/superpowers/plans/2026-07-22-sp1-database-consolidation.md` — all tasks.

**Read before starting (context + rules):**
- `CLAUDE.md` — stack, flat-import convention, tiers, known landmines. StaX is Python 3.9, PySide2, SQLite; run GUI tests headless with `QT_QPA_PLATFORM=offscreen`.
- `docs/superpowers/specs/2026-07-22-sp0-test-harness-ci-design.md` and `…-sp1-database-consolidation-design.md` — the designs the plans implement.
- `docs/superpowers/CROSS_PLAN_REVIEW.md` — §6 (canonical order) and §7 (reconciliation checklist). Note SP1 must land before any EP.
- `docs/superpowers/IMPLEMENTATION_PROGRESS.md` — the live tracker.

**Non-negotiable rules:**
- Follow each task's TDD steps exactly: write the failing test → run it and confirm it fails → implement → run it and confirm it passes → commit. Use conventional-commit messages as written in the plan.
- **Never weaken or delete a test to make it pass.** If a plan step says mark something `xfail(strict)`, do that with the stated reason; otherwise fix the root cause.
- **SP0 does NOT fix product bugs.** Its smoke tests for C1 (`tests/gui/test_api_smoke.py`, `tests/gui/test_batch_edit_smoke.py`) are `@pytest.mark.xfail(strict=True)` and must stay red-as-expected. **SP1 flips them to real passes** — when SP1 is done, those two tests must PASS (strict xfail turns an accidental early pass into a signal, so this is your SP1 success check).
- After each task: run `pytest -m "not manual"` and confirm the suite is green (expected xfails allowed, 0 real failures/errors). After each sub-project: run the full suite and report the pass/xfail counts.
- Dependencies: implement `write=`-scoped `get_connection` and the versioned migration runner exactly as SP1 specifies; SP0's `stax_db` fixture builds the real `DatabaseManager`.
- Update `docs/superpowers/IMPLEMENTATION_PROGRESS.md`: tick each task's checkbox as it lands, and set SP0/SP1 `Impl` to ☑ when the sub-project is complete.

**Stop-and-confirm gates (outward-facing — do NOT do these without explicit human approval):**
- **SP0 Task 9** creates `.github/workflows/ci.yml`, then **pushes** and **enables branch protection** via `gh`. Do steps 1–2 (write + validate the workflow, commit locally), then **PAUSE and ask the human** before `git push` and before the `gh api … branches/main/protection` call. Branch protection needs repo-admin rights and may be a manual step on their side.
- Do not push any branch or open a PR unless the human asks.

**Definition of done for this handover:**
- SP0: `tests/` restructured into unit/gui/nuke/manual tiers; `conftest.py` rebuilt on the real `DatabaseManager`; `pytest.ini` + `pyproject.toml` dev extra updated; characterization + smoke tests present; CI workflow written (push/branch-protection gated on approval). Suite green with the two C1 smoke tests xfailing.
- SP1: the two DB layers merged into one `DatabaseManager` (lowercase schema), versioned migration runner wired and called, favorites/SQL-whitelist/lock-file/WAL→DELETE/playlist-migration fixes applied, analytics/API/batch-edit calling real methods. The SP0 C1 smoke tests now PASS. Full suite green.
- Tracker updated; all work committed on `exec/sp0-sp1`. Report a summary and wait for the human before proceeding to SP2 or merging.

If a plan step references a local method/name that differs from the real code, read the file and adapt to the real name (the plans flag these). Report anything that can't be reconciled instead of guessing.
