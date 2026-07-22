# SP2 — Async Ingestion & Preview Pipeline — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). SP2 is the third sub-project. It depends on **SP0** (test harness/CI, fixtures) and **SP1** (DB consolidation: `phash` column, insertion-log write path, consolidated DB methods). It makes StaX's *advertised-but-dead* async pipeline real.

---

## 1. Background & Motivation

The audit (`STAX_AUDIT_REPORT.md`) found StaX's headline problem is **integration debt** — features that were written but never wired. SP2 owns the largest cluster of that debt: the responsiveness pipeline and the sequence/duplicate plumbing that hangs off it.

The five issues in scope:

- **C4 — the advertised async pipeline is dead.** `PreviewWorker` (`src/preview_worker.py`) is *started* in `main.py` (`_start_preview_worker`, line 129) and its signals wired, but **nothing ever calls `submit()`** — the only `PreviewJob(...)` construction lives in the never-applied `src/ingestion_core_patch.py`. Live `IngestionCore.ingest_file` (`src/ingestion_core.py:710-849`) generates thumbnails/GIF/MP4 **synchronously on the calling thread**. Separately, `LazyGalleryView` (`src/ui/lazy_gallery_view.py`) is **never imported** — `MediaDisplayWidget` (line 164) uses a plain `DragGalleryView` and `_update_views_with_elements` decodes a whole page of `QPixmap`s synchronously on the UI thread. Bulk ingestion in `main.perform_ingestion` (line 714) and `ingest_library_dialog.start_ingestion` (line 365) runs a **blocking loop on the GUI thread** behind a `QProgressDialog`.
- **H7 — drop-ingest passes the wrong config type + wrong key + fragile thread lifetime** (`src/ui/media_display_widget.py:320-411`): `IngestionCore(self.db, self.config)` passes a `Config` **object** where everywhere else it is `self.config.get_all()` (a dict); copy policy is read as `self.config.get('copy_policy', 'soft')` but the real key is `default_copy_policy`; the worker `thread` is a local only held by lambda slots with a 3 s `wait`.
- **M12 — the preview worker can't decode core VFX formats + hardcodes 4-digit padding** (`src/preview_worker.py:244, 290, 328`): `PIL.Image.open` cannot read `.exr`/`.dpx`/`.mxf`, and the MP4 input pattern hardcodes `%04d` regardless of real padding.
- **L8 — fragile frame-range parsing** (`src/nuke_bridge.py:95-100`): `frame_range.split('-')` breaks on negative first frames and stepped/missing ranges.
- **L5 — duplicate detection is orphaned and its MD5 fallback corrupts distance semantics** (`src/duplicate_detection.py:99-157`): never invoked in the live ingest path; `hamming_distance` routes MD5-fallback strings through `imagehash.hex_to_hash`, producing garbage distances.

### Locked program decisions honored here
- **Wire up, don't delete.** `PreviewWorker`, `LazyGalleryView`, and `duplicate_detection` are *finished and connected*, not removed. The only deletion is `src/ingestion_core_patch.py`, whose entire purpose was to describe this wiring.
- **Windows + Linux.** No `.exe`-hardcoding is introduced (ffmpeg binary naming is SP3's job; SP2 routes through the existing `get_ffmpeg()` facade and does not regress it).
- **Hybrid 3-tier testing** (unit / gui / nuke), **flat imports in tests**, **`logging` not `print`** in new code, **TDD + conventional commits + frequent commits**.

### Adopted OSS building blocks (per program §7)
- **Fileseq** (`pip install fileseq`) — replaces the fragile homegrown frame-range parsing (L8). Handles negative frames, stepped ranges (`1-10x2`), and missing frames.
- **M12 decision (locked by this spec):** route EXR/DPX/MXF thumbnail + preview decode through the **already-bundled ffmpeg** via `ffmpeg_wrapper` — *not* OpenImageIO. ffmpeg already reads EXR/DPX and ships with StaX, so this is zero new binary weight. **OpenImageIO is explicitly deferred** as a future optional enhancement (color-correct/OCIO previews), not adopted in SP2.

---

## 2. Goals / Non-Goals

### Goals
- `IngestionCore.ingest_file` submits a `PreviewJob` to the shared `PreviewWorker` instead of generating previews inline. Thumbnails/GIF/MP4 are produced off-thread.
- `PreviewWorker` decodes EXR/DPX/MXF and sequences through `ffmpeg_wrapper` (no PIL), using **real** sequence padding derived from `SequenceDetector` (no hardcoded `%04d`).
- All ingestion loops (drop-ingest, `perform_ingestion`, library ingest) run on a **shared `IngestWorker(QThread)` driven by signals** — no `QApplication.processEvents()`, no GUI-thread blocking loop.
- The live gallery **is** a `LazyGalleryView` (via `DragGalleryView` subclassing it), loading thumbnails only for the visible viewport with LRU eviction, and updating icons from `preview_ready` as the worker finishes.
- Duplicate detection is wired into `ingest_file`: compute a perceptual hash, check the DB before insert, store the hash after insert; the MD5-fallback path compares by exact equality only.
- H7 fixed: drop-ingest passes `config.get_all()`, key `default_copy_policy`, and holds a member reference to the ingest worker until `finished`.
- `src/ingestion_core_patch.py` deleted.

### Non-Goals (explicitly deferred)
- OpenImageIO / OpenColorIO adoption; color-correct previews (future enhancement #8).
- Fixing ffmpeg's Windows-only binary names (**SP3**) — SP2 uses `get_ffmpeg()` and does not touch binary resolution.
- Bounding the unbounded `QMovie`/icon caches (M5), timeouts on ffmpeg subprocesses (M9), the GIF palette temp-file race (M8) — those are SP3/SP6.
- A synchronous, GUI-thread `DuplicateDialog` flow. SP2 wires detection + a config-driven skip policy; the interactive dialog stays available for a future GUI-triggered synchronous path (SP6).
- BK-tree bucketing of phashes (audit L5's O(N²) note) — SP2 fixes correctness (semantics + wiring); the linear scan is acceptable at current library sizes and is a later optimization.

---

## 3. Approach

**Two cooperating background threads, one queue.** Ingestion I/O (copy, Blender GLB conversion, DB insert, phash/dedup) runs on a per-operation `IngestWorker(QThread)`. Preview *rendering* (thumbnail/GIF/MP4 via ffmpeg) runs on the long-lived singleton `PreviewWorker(QThread)` that already exists and is already started by `MainWindow`. `ingest_file` connects them: after the DB row is written, it enqueues one `PreviewJob` carrying the **deterministic output paths** it already computes plus the detected **sequence info** (real padding). The worker writes to exactly those paths and emits `preview_ready(element_id, path, type)`; the gallery swaps the icon in place.

Why deterministic paths (not worker-chosen names): the DB row is written *before* the preview exists (async), so `ingest_file` stores the *predicted* preview paths. The worker must write to those same paths for persistence across restarts. This is the single most important contract in SP2 and is captured in the Key Signatures below.

**LazyGalleryView adoption without feature regression.** Rather than swap the gallery widget wholesale (which would drop drag-to-Nuke, status badges, and GIF-first-frame), `DragGalleryView` becomes a **subclass of `LazyGalleryView`**, inheriting viewport-based lazy loading, LRU eviction, and the `on_preview_ready` slot, while keeping `startDrag`/`insert_to_nuke`. `MediaDisplayWidget` keeps building its items and the table, but registers a per-item **loader hook** so the expensive decode (and badge compositing) runs only for items the lazy loader decides are visible.

Rejected alternatives:
- *Generate previews synchronously but on the IngestWorker thread only* — simpler, but leaves the started-but-unfed `PreviewWorker` dead (violates "wire up, don't delete") and re-decodes on every gallery navigation.
- *Replace `DragGalleryView` with `LazyGalleryView` directly* — regresses drag-to-Nuke, badges, and GIF preview.
- *OpenImageIO for decode* — heavier dependency for a capability bundled ffmpeg already has; deferred.

---

## 4. Detailed Design

### 4.1 `PreviewJob` — carries outputs + real sequence info (`src/preview_worker.py`)

Extend `PreviewJob.__slots__` and constructor (backward-compatible defaults) so a job fully describes *where* to write and *how* to read a sequence:

| Field | Type | Meaning |
|---|---|---|
| `element_id` | int | (existing) |
| `source_path` | str | (existing) first-frame / movie path |
| `output_dir` | str | (existing) previews root |
| `asset_type` | str | (existing) `'2D'`/`'3D'`/`'Toolset'` |
| `frame_range` | str/None | (existing) e.g. `'1001-1100'` |
| `config` | dict | (existing) config snapshot |
| `priority` | int | (existing) |
| `thumb_path` | str/None | **new** — exact PNG path to write |
| `gif_path` | str/None | **new** — exact GIF path to write |
| `video_path` | str/None | **new** — exact MP4 path to write |
| `is_sequence` | bool | **new** |
| `ffmpeg_pattern` | str/None | **new** — full padded pattern path (`.../shot.%04d.exr`) from `SequenceDetector.get_sequence_path` |
| `first_frame` | int | **new** — real start frame (default 1) |

### 4.2 `PreviewWorker._process` — ffmpeg decode, real padding (M12)

Replace the PIL-based `_generate_thumbnail` / `_generate_gif` / `_generate_video` with calls through `get_ffmpeg()`:

- **Thumbnail:** `is_sequence` → `ffmpeg.generate_sequence_thumbnail(ffmpeg_pattern, thumb_path, max_size, frame_number=first_frame)`; else `ffmpeg.generate_thumbnail(source_path, thumb_path, max_size)`. This decodes EXR/DPX/MXF (M12) and uses the **real** pattern padding (no `%04d`).
- **GIF** (2D only): `ffmpeg.generate_gif_preview(input, gif_path, ..., start_frame=first_frame, is_sequence=is_sequence, ...)` where `input = ffmpeg_pattern if is_sequence else source_path`.
- **Video** (2D sequence): `ffmpeg.generate_sequence_video_preview(ffmpeg_pattern, video_path, start_frame=first_frame, ...)`; non-sequence video → `ffmpeg.generate_video_preview(source_path, video_path)`.

Each successful write emits `preview_ready(element_id, <path>, <type>)`. All sizing/fps values are read from the `config` dict snapshot (`preview_size`, `gif_size`, `gif_fps`, `gif_duration`, `sequence_preview_fps`, `generate_previews`, `generate_video_previews`). Failures are logged via `logging` (not `print`) and simply skip that output — the DB still holds the predicted path and the gallery shows the type fallback icon.

### 4.3 `ingest_file` wiring (C4-part-1 + L5) (`src/ingestion_core.py`)

Replace the synchronous preview block (lines ~710-849: `PreviewGenerator.*`, the inline GIF ffmpeg call, and the MP4 call) with:

1. Compute the same deterministic paths already used (`preview_path`, `gif_preview_path`, `video_preview_path`).
2. **Duplicate check (before DB insert):** if `config.get('dedup_enabled', True)`, `phash = compute_phash(first_frame_path)`; `dupes = find_duplicates(self.db, phash, threshold=config.get('dedup_threshold', 8))`. If `dupes` and `config.get('dedup_skip_duplicates', False)` → return `{'success': False, 'reason': 'duplicate_skipped', 'message': ...}`. (`perform_ingestion` already tallies `reason == 'duplicate_skipped'`.)
3. `create_element(...)` storing the **predicted** preview paths.
4. **Store phash after insert:** `if phash: self.db.update_element_phash(element_id, phash)` (SP1-provided).
5. Submit one `PreviewJob` (with the paths + sequence info) to `get_preview_queue()`.

3D/geometry (Blender GLB) conversion stays inside `ingest_file` — it is a prerequisite for the DB row and now runs on the `IngestWorker` thread, so it no longer freezes the GUI (resolving C4's "Not Responding during Blender" symptom).

### 4.4 Duplicate-detection correctness (L5) (`src/duplicate_detection.py`)

Tag hashes by kind so MD5 fallbacks are never routed through `imagehash.hex_to_hash`:

- `compute_phash` returns `"p:" + <hex>` on success; the MD5 fallback returns `"m:" + <hex>`.
- `hamming_distance(a, b)`: `0` if equal; if **either** side is `"m:"`-tagged (or untagged/legacy) → return `999` unless exactly equal (exact-equality-only in fallback mode); if **both** `"p:"`-tagged → `imagehash.hex_to_hash(a[2:]) - imagehash.hex_to_hash(b[2:])`.

Because SP1 adds a *fresh* `phash` column (no legacy rows), introducing the tag now is migration-safe. `find_duplicates` is unchanged in shape (it calls `hamming_distance`); it depends on SP1's `db.get_elements_with_phash()`.

### 4.5 Frame-range hardening with Fileseq (L8) (`src/ingestion_core.py`, `src/nuke_bridge.py`)

Add to `ingestion_core.py`:
- Module helper `parse_frame_range(range_str)` → `(first, last, frames_list)` using `fileseq.FrameSet`, with a negative-aware regex fallback when fileseq is unavailable.
- `SequenceDetector._compact_frame_range(frame_numbers)` → compact range string via `fileseq.FrameSet(...).frameRange()` (e.g. `"1-3,5"` for a gapped sequence), falling back to `"min-max"`. `detect_sequence` uses it for the `frame_range` field. Contiguous sets still render `"first-last"`, preserving SP0's characterization contract.

`nuke_bridge.create_read_node` (real mode) replaces `frame_range.split('-')` with `parse_frame_range`, so negative first frames and stepped/missing ranges set `first`/`last` correctly. (`from src.ingestion_core import SequenceDetector` already exists there; add `parse_frame_range`.)

### 4.6 Shared `IngestWorker(QThread)` (C4-part-3) (`src/ingest_worker.py`, new)

One reusable worker replaces the inline `IngestThread` and the two blocking GUI-thread loops.

- Constructor: `IngestWorker(db, config_dict, jobs, copy_policy)` where `jobs` is a list of `(source_path, target_list_id)` tuples and `config_dict` is a plain dict (`Config.get_all()`).
- Signals: `progress(int done, int total, str label)`, `file_done(dict result)`, `ingest_finished(int success, int skipped, int errors)`, `ingest_failed(str message)`.
- `run()` constructs one `IngestionCore(db, config_dict)` and calls `ingest_file` per job, tallying `success`/`skipped`(`duplicate_skipped`)/`error`, emitting `progress` after each and `ingest_finished` at the end. A `cancel()` flag stops the loop between files.

Callers pre-build their DB structure on the GUI thread (fast) and hand a flat job list to `IngestWorker`:
- `MediaDisplayWidget.ingest_dropped_files` — H7 fixes applied; holds `self._ingest_worker` reference until `ingest_finished`.
- `main.perform_ingestion` — replaces the blocking `for` loop; reloads the list on `ingest_finished`.
- `ingest_library_dialog.start_ingestion` — creates stacks/lists first (GUI thread), then feeds `(filepath, list_id)` jobs to `IngestWorker`; progress dialog driven by the `progress` signal instead of the in-loop `setValue`.

### 4.7 `LazyGalleryView` adoption (C4-part-2) (`src/ui/lazy_gallery_view.py`, `src/ui/drag_gallery_view.py`, `src/ui/media_display_widget.py`)

- Add to `LazyGalleryView` an optional **item-loader hook**: `set_item_loader(callable)` / `clear_item_loader()`. `_load_visible` invokes `self._item_loader(item)` for visible items when a loader is set (falling back to the built-in `GalleryItem.load_pixmap` otherwise), and resets far-away items to a placeholder for LRU eviction. This lets a host reuse its own per-item decode (badges, GIF-first-frame) while keeping decode viewport-bounded.
- `DragGalleryView(LazyGalleryView)` — inherits lazy loading, LRU, and `on_preview_ready`; keeps `startDrag`, `insert_to_nuke`, `_resolve_storage_path`. Constructor stays `(db_manager, config, nuke_bridge, parent=None)` and calls `LazyGalleryView.__init__(self, parent=parent)`.
- `MediaDisplayWidget._update_views_with_elements` — builds items with a placeholder icon and stores the element dict on the item (`Qt.UserRole + 1`); registers an item-loader that runs the existing `_load_preview_pixmap`/badge/GIF-first-frame path for a *single* visible item. The synchronous full-page decode loop is removed. `on_preview_ready` (already present, line 847) continues to update a specific item when the worker finishes.

### 4.8 Delete the patch file

`src/ingestion_core_patch.py` is removed — its three "changes" are now applied for real (§4.1–§4.4). No live code imports it (verified: only the never-applied patch constructed `PreviewJob`).

---

## 5. Interfaces & Assumptions (SP0 / SP1 dependencies)

**From SP0 (test harness):** fixtures `stax_db` (real `DatabaseManager` on a temp DB), `stax_config` (real `Config`), `mock_nuke` (fake `nuke` module), `tiny_sequence` (numbered PNGs), headless Qt (`qtbot`, `QT_QPA_PLATFORM=offscreen`), the 3-tier `tests/unit|gui|nuke` layout, and flat imports (`src/` on `sys.path`).

**From SP1 (DB consolidation) — assumed present, exercised by SP2:**
- `elements.phash` column (TEXT, nullable).
- `DatabaseManager.update_element_phash(element_id, phash)` — persists the hash string.
- `DatabaseManager.get_elements_with_phash()` → `list[dict]` rows including at least `element_id`, `phash`, `name`, `format`, `list_fk`.
- SP1's insertion-log write path (used by `log_ingestion`); SP2 does not change logging semantics.

Where SP1 has not yet landed in a given worktree, SP2's dedup **unit** tests use a small in-test fake DB implementing those two methods, so SP2 tests do not block on SP1. The `ingest_file` **integration** test skips gracefully if `stax_db` lacks `update_element_phash`.

---

## 6. Testing Strategy

3-tier, TDD, per the SP0 harness. New tests:

**Unit (`tests/unit/`, no Qt):**
- `test_frame_range_fileseq.py` — `parse_frame_range` on `"1-10"`, `"-5-10"` (negative first), `"1-10x2"` (stepped), `"1-3,5"` (missing); `SequenceDetector._compact_frame_range`.
- `test_duplicate_detection.py` — `hamming_distance`: identical → 0, two `"p:"` phashes → real bit distance, `"m:"` vs `"m:"` non-equal → 999, `"p:"` vs `"m:"` → 999; `find_duplicates` against a fake DB (threshold filtering + `distance` key + sort).
- `test_preview_worker_ffmpeg.py` — monkeypatch `get_ffmpeg()`; assert a sequence `PreviewJob` calls `generate_sequence_thumbnail(ffmpeg_pattern, thumb_path, ...)` with the **real** pattern (not `%04d`) and `start_frame`/`frame_number == first_frame`; assert `preview_ready` emits the exact `thumb_path`.
- `test_ingest_submits_preview_job.py` — monkeypatch the preview queue; assert `ingest_file` submits exactly one `PreviewJob` with matching `thumb_path`/`gif_path`/`video_path` and stores those paths on the element; assert no synchronous ffmpeg/PIL decode occurs.

**GUI (`tests/gui/`, headless):**
- `test_lazy_gallery_item_loader.py` — `LazyGalleryView.set_item_loader` invoked only for visible items; `on_preview_ready` swaps a specific item's icon.
- `test_drag_gallery_is_lazy.py` — `isinstance(DragGalleryView(...), LazyGalleryView)` and `insert_to_nuke` still present.
- `test_ingest_worker.py` — `IngestWorker` over a 2-file job list against `stax_db` emits `progress` per file and `ingest_finished(success, skipped, errors)` with correct tallies (uses `qtbot.waitSignal`).
- `test_media_display_dropingest.py` — H7: monkeypatch `IngestionCore` to capture its `config` arg; assert `ingest_dropped_files` constructs it with a **dict** (`get_all()`), reads `default_copy_policy`, and retains `self._ingest_worker` until finished.

**Nuke (`tests/nuke/`):**
- `test_nuke_bridge_frame_range.py` — real-mode `create_read_node` with `mock_nuke` and a fake node: `frame_range="-5-10"` sets `first=-5`, `last=10`; `"1-10x2"` sets `first=1`, `last=9`.

ffmpeg-dependent assertions are pure argv/mock checks (marked `unit`/`gui`), so CI needs no ffmpeg binaries. SP0's `xfail` C1 smoke tests are untouched.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| DB row stores a preview path before the file exists (async) → gallery shows fallback until `preview_ready` | Deterministic paths + `on_preview_ready` swap; fallback type icon is acceptable transient state; path is correct on next launch once written. |
| `DuplicateDialog` cannot be shown from the `IngestWorker` thread | SP2 wires *detection* + a config-driven skip policy only; no dialog on the worker thread. Interactive dialog deferred to SP6's GUI-triggered path. |
| Subclassing `DragGalleryView` from `LazyGalleryView` changes item-population semantics | Item-loader hook preserves the existing decode/badge/GIF path; only *when* decode runs changes (visible-only). GUI test asserts drag + `insert_to_nuke` survive. |
| fileseq unavailable in a stripped environment | `parse_frame_range`/`_compact_frame_range` fall back to negative-aware regex / `min-max`; behavior degrades gracefully, contiguous ranges unchanged. |
| SP1 not yet merged in the executor's worktree | Dedup unit tests use an in-test fake DB; the ingest integration test skips when `update_element_phash` is absent. |
| Two background threads (IngestWorker + PreviewWorker) | `PreviewWorker` queue is a thread-safe `PriorityQueue`; jobs are plain data; signals auto-marshal to the GUI thread. No shared mutable state between the two. |

---

## 8. Deliverables Checklist
- [ ] `PreviewJob` extended with output paths + sequence info; `PreviewWorker._process` routed through `ffmpeg_wrapper` with real padding (M12).
- [ ] `ingest_file` submits a `PreviewJob` and stores predicted paths; synchronous preview generation removed (C4-1).
- [ ] Duplicate detection wired into `ingest_file`; `hamming_distance`/`compute_phash` MD5 semantics fixed (L5).
- [ ] `parse_frame_range` + `_compact_frame_range` (fileseq); `nuke_bridge` real-mode range parse hardened (L8); `fileseq` added to `pyproject.toml`.
- [ ] Shared `IngestWorker(QThread)`; `perform_ingestion`, `ingest_library_dialog`, and drop-ingest driven by signals — no `processEvents`/blocking loops (C4-3).
- [ ] `DragGalleryView` subclasses `LazyGalleryView` + item-loader hook; `MediaDisplayWidget` decode is viewport-bounded (C4-2).
- [ ] H7 fixed (dict config, `default_copy_policy`, member-held worker).
- [ ] `src/ingestion_core_patch.py` deleted.
- [ ] Unit/gui/nuke tests green; SP0 C1 `xfail`s untouched.

---

## 9. Follow-on
- **SP3** fixes ffmpeg's Windows-only binary names (unblocking previews on Linux) and adds subprocess timeouts / GIF-palette race fixes — SP2's ffmpeg routing benefits immediately.
- **SP6** adds the interactive main-thread `DuplicateDialog` flow and bounds the `QMovie`/icon caches (M5).
- A later optimization can bucket phashes (BK-tree) and adopt OpenImageIO/OCIO for color-correct EXR/DPX previews.
