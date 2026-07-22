# Copilot Instructions for StaX

> These instructions describe the **actual current state** of StaX. An earlier
> version of this file described a "greenfield, Python 2.7" project — that was
> incorrect. StaX is a real, ~20K-line Python 3.9+ application in Beta.
> For the fuller agent guide see `CLAUDE.md` at the repo root.

## Project Overview

StaX is a **stock-footage & VFX asset manager for Foundry Nuke**: a PySide2
desktop app (also embeddable as a Nuke panel) backed by SQLite, with an
ffmpeg-based media pipeline, a WebGL 3D (GLB) viewer, a REST API, and a Python
extensibility-hook system. Assets are organized as **Stacks → Lists
(nestable) → Elements** and dragged directly into the Nuke node graph.

**Status:** Beta, under active audit-driven remediation (see `STAX_AUDIT_REPORT.md`).
**Platforms:** Windows + Linux (no macOS).

## Technology Stack (authoritative)

- **Python 3.9+** — `requires-python = ">=3.9"`. Uses PySide2, Flask, numpy≥2,
  `secrets`, `shutil.which` (all Py3-only). Old headers claiming "Python 2.7
  compatible" are **false and being removed** — do NOT add Python 2 shims.
- **PySide2** (Qt5) for the GUI; Fusion style + dark palette + `resources/style.qss`.
- **SQLite** via `src/db_manager.py`, with an external file lock
  (`src/file_lock.py`) for network shares.
- **FFmpeg** (bundled) via `src/ffmpeg_wrapper.py`; `ffpyplayer` for playback.
- **uv** for dependency management; cx_Freeze / PyInstaller / Inno Setup for packaging.

## Architecture

```
GUI (main.py, src/ui/*)                     ← MainWindow, panels, dialogs
  ↓
Core (ingestion_core.py, preview_worker.py, extensibility_hooks.py, config.py)
  ↓
Data (db_manager.py → SQLite; file_lock.py)
  ↓
Nuke Bridge (nuke_bridge.py — mock/real abstraction)  Media (ffmpeg_wrapper.py)
```

**Key pattern:** `nuke_bridge.py` is a pure abstraction with a `mock_mode`
branch for every operation, so the app runs and is testable without Nuke.
Instantiate as `NukeBridge(mock_mode=True)` outside Nuke.

## Data model (3-level hierarchy)

```
Stacks  (e.g. "Plates", "3D Assets")
  └─ Lists  (nestable via parent_list_fk; e.g. "Cityscape", "Explosions")
       └─ Elements  (individual assets — the richest entity)
```

Elements use a **dual-path** design: `filepath_soft` (reference in place) vs
`filepath_hard` (copied into the repository), selected by `is_hard_copy`.
Element `type` is one of `2D` / `3D` / `Toolset`.

**Live schema tables are lowercase** (`stacks`, `lists`, `elements`,
`ingestion_history`). The capitalized `Stacks`/`Elements`/`InsertionLog` seen
in `db_manager_additions.py` / `db_migrations.py` are an **orphaned, never-applied
layer** — do not target them (issue C1).

## Import convention

`src/` is on `sys.path` at runtime, so modules import siblings flat:
`from db_manager import DatabaseManager`. Keep this style.

## Ingestion pipeline (order matters)

1. Sequence detection (`SequenceDetector` — auto frame-range discovery from a
   single dropped frame; patterns like `name.####.ext`).
2. Pre-Ingest processor hook (may cancel).
3. Hard/soft copy per policy (`default_copy_policy`).
4. 3D→GLB conversion when applicable.
5. Preview generation (thumbnail / GIF / MP4 proxy via ffmpeg).
6. DB insert + `ingestion_history` log.
7. Post-Ingest processor hook.

## Nuke integration

- **2D** → `Read` node (with frame range + sequence printf pattern)
- **3D** (`.abc`→`ReadGeo2`, else `ReadGeo`) → geometry node
- **Toolset** (`.nk`) → node paste

All via `nuke_bridge.py` (mock fallback outside Nuke).

## Testing

3-tier layout (being finalized under sub-project SP0):
`tests/unit/` (pure logic), `tests/gui/` (headless Qt, `QT_QPA_PLATFORM=offscreen`,
pytest-qt), `tests/nuke/` (mocked nuke), `tests/manual/` (not collected).

```bash
uv pip install -e ".[dev]"
pytest -m "not manual"
```

Use the `stax_db` / `stax_config` / `mock_nuke` fixtures. Nuke and the GUI are
never run "for real" in CI.

## Known critical issues (see STAX_AUDIT_REPORT.md)

- **C1** two incompatible DB layers — live code calls missing methods
  (`update_element_metadata`, `get_top_inserted_elements`) → `AttributeError`.
- **C2** unsandboxed `exec()` of processor scripts.
- **C4** async preview worker started but never fed; ingestion blocks the GUI thread.
- Orphaned/dead modules: `*_additions.py`, `*_patch.py`, `lazy_gallery_view.py`,
  `batch_edit_dialog.py`, duplicate detection.

**Before editing a file, check the audit report for open issues in it.**

## Remediation program

Work is decomposed into sub-projects **SP0–SP8** with specs and plans under
`docs/superpowers/`; progress is tracked in
`docs/superpowers/IMPLEMENTATION_PROGRESS.md`. Locked decisions: wire
half-finished features up (don't delete), target Windows+Linux, hybrid 3-tier
testing, adopt proven OSS building blocks (OpenImageIO, Fileseq, OpenColorIO,
Qt.py) where they replace bespoke code.

## Pitfalls to avoid

- Don't add Python 2.7 shims or claim Py2 support.
- Don't `import nuke` outside `nuke_bridge.py` — keep the abstraction.
- Don't call the orphaned capitalized-schema DB methods until SP1 lands them.
- Don't fake UI responsiveness with `QApplication.processEvents()` — use QThreads.
- Use `logging`/`stax_logger`, not bare `print`, in new code.
- Sequence detection is automatic — never require users to type frame ranges.
