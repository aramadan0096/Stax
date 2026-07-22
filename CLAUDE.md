# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repository.

## What StaX is

StaX is a **stock-footage & VFX asset manager for Foundry Nuke** — a PySide2 desktop app (also embeddable as a Nuke panel) with a SQLite backend, an ffmpeg-based media pipeline, a WebGL 3D (GLB) viewer, a REST API, and a Python extensibility-hook system. It organizes assets as **Stacks → Lists (nestable) → Elements** and drags them straight into the Nuke node graph.

This is a **real, ~20K-line application** (not greenfield). It is in **Beta** and under active remediation — see "Audit remediation program" below.

## Tech stack (authoritative — do not trust older docs)

- **Python 3.9+** (`requires-python = ">=3.9"`). The app uses PySide2, Flask, numpy≥2, `secrets`, `shutil.which` — all Python-3-only. Some file headers still claim "Python 2.7 compatible"; **this is false and being removed** (issue L7). Do not add Py2 shims.
- **GUI:** PySide2 (Qt5), Fusion style + custom dark palette (`src/dark_palette.py`) + `resources/style.qss`.
- **DB:** SQLite via `src/db_manager.py` (`DatabaseManager`), with an external file lock (`src/file_lock.py`) for network shares.
- **Media:** bundled FFmpeg/FFprobe/FFplay via `src/ffmpeg_wrapper.py`; `ffpyplayer` for embedded playback.
- **3D:** GLB in a `QWebEngineView` (`src/geometry_viewer.py`); conversion via Blender/trimesh/pygltflib (`src/glb_converter.py`, `src/convert_to_glb.py`).
- **Packaging:** cx_Freeze (`setup_freeze.py`, the build `build.ps1` actually runs), plus a PyInstaller spec and Inno Setup script; `uv` for dependency management.
- **Target platforms:** **Windows + Linux** (no macOS).

## Repository layout

```
main.py              App shell / MainWindow (3-pane window, docks, auth, services)
menu.py, init.py     In-Nuke menu + plugin bootstrap
nuke_launcher.py     Standalone + embedded StaXPanel (dual-mode)
src/
  db_manager.py      DatabaseManager — schema, CRUD, migrations, auth, tags
  file_lock.py       Cross-platform advisory file locking
  ingestion_core.py  Ingest pipeline: SequenceDetector, copy, convert, previews
  ffmpeg_wrapper.py  Thumbnails / GIFs / video previews / probing
  nuke_bridge.py     NukeBridge (mock/real) + NukeIntegration (insert/toolset)
  api_server.py      REST API (QThread WSGI: Flask app via _build_flask_app)
  extensibility_hooks.py  Pre/Post-ingest & Post-import processor hooks
  preview_worker.py  Async preview QThread    preview_cache.py  LRU pixmap cache
  duplicate_detection.py  Perceptual-hash dedup
  config.py          Config (JSON + STOCK_DB env + DB-backed settings)
  geometry_viewer.py / glb_converter.py       3D preview + conversion
  video_player_widget.py                       ffpyplayer embedded player
  ui/                ~15 panels/dialogs (gallery, settings, analytics, ...)
tests/               Test suite (see Testing)
tools/               Installers, ffmpeg downloader, CLI, build scripts
docs/superpowers/    Audit-remediation specs & plans (see below)
STAX_AUDIT_REPORT.md Full audit: features, ranked issues, competitors, roadmap
```

## Import convention

`src/` is placed on `sys.path` at runtime (by `init.py` in Nuke, and by `tests/conftest.py`), so **modules import their siblings flat**: `from db_manager import DatabaseManager`, `from ffmpeg_wrapper import get_ffmpeg`. Follow this pattern; don't rewrite imports to `src.xxx`.

## Running & building

```bash
# Standalone run (Windows PowerShell)
.\tools\run_standalone.ps1

# Install deps into a portable lib/ + .venv
.\tools\install_libs_requirements_uv.ps1

# Build the frozen app (cx_Freeze)
.\tools\build.ps1
```

## Testing

The test harness is being rebuilt under sub-project **SP0** into a 3-tier layout:

```
tests/unit/   pure logic, no Qt          tests/gui/   headless Qt (pytest-qt, QT_QPA_PLATFORM=offscreen)
tests/nuke/   NukeBridge(mock_mode=True) tests/manual/ archived scratch scripts (NOT collected)
```

```bash
uv pip install -e ".[dev]"        # pytest-qt, pytest-mock, pytest-cov, flask
pytest -m "not manual"            # run the collected suite
```

- **Nuke and the GUI never run "for real" in CI** — Nuke is mocked; Qt runs headless (`offscreen`).
- Use the `stax_db` fixture (real `DatabaseManager` on a temp DB), `stax_config`, `mock_nuke`, and the media fixtures in `tests/conftest.py`.
- ffmpeg-dependent tests are marked `@pytest.mark.ffmpeg` and skip when binaries are absent.
- **The live DB schema uses lowercase tables** (`stacks`, `lists`, `elements`, `ingestion_history`). The capitalized `Stacks`/`Elements`/`InsertionLog` belong to an orphaned, never-applied layer — do not target them.

## Known critical issues (see STAX_AUDIT_REPORT.md for the full ranked list)

The audit found substantial **integration debt** — treat these as landmines:

- **C1 — Two incompatible DB layers.** `src/db_manager_additions.py` / `src/db_migrations.py` are *apply-by-hand patches that were never applied*; live code (API, analytics, batch-edit) calls methods that don't exist → `AttributeError`. **Don't call `db.update_element_metadata` / `get_top_inserted_elements` etc. until SP1 merges them.**
- **C2 — `exec()` RCE** in `extensibility_hooks.py`. Processor scripts run with full builtins; do not present this as "safe."
- **C4 — Async pipeline is dead.** `preview_worker.py` is started but never fed; `lazy_gallery_view.py` is never instantiated; ingestion runs on the GUI thread.
- Orphaned/dead: `*_additions.py`, `*_patch.py`, `lazy_gallery_view.py`, `batch_edit_dialog.py` (unwired), duplicate detection (unwired).

**When you touch a file, check the audit report for open issues in it first.**

## Audit remediation program

Remediation is decomposed into 9 sub-projects (**SP0–SP8**), each with a spec and a plan under `docs/superpowers/`:

- `docs/superpowers/specs/` — approved designs (one per sub-project).
- `docs/superpowers/plans/` — task-by-task TDD implementation plans.
- `docs/superpowers/IMPLEMENTATION_PROGRESS.md` — live checklist tracking status across all SPs.

Order: SP0 (test harness/CI) → SP1 (DB consolidation) → SP2 (async pipeline) → SP3 (ffmpeg/cross-platform) → SP4 (security) → SP5 (Nuke integration) → SP6 (UI correctness) → SP7 (packaging) → SP8 (code quality). Program decisions already locked: **wire half-finished features up (don't delete them)**, **Windows+Linux**, **hybrid 3-tier testing**, **adopt proven OSS building blocks** (OpenImageIO, Fileseq, OpenColorIO, Qt.py, …) where they replace bespoke code.

## Conventions

- Follow existing patterns in the file you're editing; match its style.
- Prefer stdlib and existing dependencies; adding a heavy dependency (e.g. OpenImageIO) is a spec-level decision, not an ad-hoc one.
- Use `logging` / `stax_logger`, not bare `print`, in new code (issue L4).
- Commit messages: conventional prefixes (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `build:`).
- **Do not fix product bugs inside SP0 test work** — document them as `xfail(strict=True)` and let the owning sub-project fix them.
- Never weaken a test to make CI pass; fix the root cause or mark `xfail` with the issue id.
