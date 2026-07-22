# SP2 — Async Ingestion & Preview Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make StaX's advertised-but-dead async pipeline real — route ingestion I/O onto a shared `IngestWorker(QThread)`, feed the started-but-unfed `PreviewWorker` real `PreviewJob`s that decode EXR/DPX/sequences through ffmpeg with correct padding, adopt `LazyGalleryView` for viewport-bounded thumbnail loading, wire duplicate detection into ingest, and harden frame-range parsing with Fileseq. Fixes **C4, H7, M12, L8, L5**. Then delete `src/ingestion_core_patch.py`.

**Architecture:** Two cooperating threads. `IngestWorker` runs `IngestionCore.ingest_file` per job (copy, Blender GLB, DB insert, phash/dedup). `ingest_file` enqueues one `PreviewJob` — carrying the deterministic preview output paths it already computes plus detected sequence info — to the long-lived singleton `PreviewWorker`, which renders thumbnail/GIF/MP4 via `ffmpeg_wrapper` and emits `preview_ready`. The gallery (`DragGalleryView` now subclassing `LazyGalleryView`) swaps icons in place, decoding only visible items.

**Tech Stack:** Python 3.9, PySide2 (offscreen in tests), pytest / pytest-qt / pytest-mock, ffmpeg (via `get_ffmpeg()`), `fileseq`, `imagehash`/Pillow (existing).

## Global Constraints

- **Depends on SP0** (fixtures `stax_db`, `stax_config`, `mock_nuke`, `tiny_sequence`; headless Qt; 3-tier `tests/unit|gui|nuke`) and **SP1** (`elements.phash` column; `DatabaseManager.update_element_phash(element_id, phash)` and `get_elements_with_phash()`; insertion-log write path). SP1's DB methods are treated as interfaces — dedup unit tests use an in-test fake DB so SP2 does not block on SP1.
- **Wire up, don't delete.** The only file deleted is `src/ingestion_core_patch.py` (Task 8).
- **Windows + Linux.** Do **not** touch ffmpeg binary resolution (SP3 owns the `.exe` fix); route through `get_ffmpeg()`.
- **Imports:** *test* files use flat imports (`from ingestion_core import ...`) — SP0 puts both repo root and `src/` on `sys.path`. *Source-file edits* preserve each file's existing convention: `main.py`, `ingestion_core.py`, `nuke_bridge.py`, and `ui/*` already use `from src.<module> import ...` — new imports added to those files follow that `src.`-prefixed style.
- **`logging` not `print`** in all new code (`log = logging.getLogger(__name__)`).
- **TDD + conventional commits**, one commit per task minimum. Run the relevant tests before each commit.
- **Deterministic-path contract:** `ingest_file` computes preview output paths, stores them in the DB row, and passes the *same* paths to the `PreviewJob`; the worker writes to exactly those paths. Never let the worker choose its own filenames.

---

## Key signatures (verified against the codebase)

- `PreviewJob(element_id, source_path, output_dir, asset_type="2D", frame_range=None, config=None, priority=50)`; `__slots__`; `__lt__` by priority (`src/preview_worker.py:73`).
- `PreviewWorker(QtCore.QThread)`; signals `preview_ready(int, str, str)`, `job_failed(int, str)`, `queue_empty()`; `.submit(job)`, `.stop()`, `.pending_count()`, `.run()` (`src/preview_worker.py:120`). Singleton via `get_preview_queue()` / `shutdown_preview_queue()`.
- `IngestionCore(db_manager, config)` — `config` is a **dict** (`self.config.get(...)`); `ingest_file(source_path, target_list_id, copy_policy='soft', comment=None, tags=None, pre_hook=None, post_hook=None)` → dict with `success`/`element_id`/`message`/`is_sequence`/`frame_range`/`sequence_files` (`src/ingestion_core.py:369,552`).
- `SequenceDetector.detect_sequence(filepath, pattern_key=None, auto_detect=True)` → dict incl. `ffmpeg_pattern`, `frame_range`, `first_frame`, `padding`, `frame_count`; `get_sequence_path(info)` → full padded pattern path (`src/ingestion_core.py:52,147`).
- `FFmpegWrapper` via `get_ffmpeg()`: `generate_thumbnail(input_path, output_path, max_size=512, frame_time=None, threads=4)`; `generate_sequence_thumbnail(sequence_pattern, output_path, max_size=512, frame_number=None, threads=4)`; `generate_gif_preview(input_path, output_path, max_duration=None, size=256, fps=10, threads=4, start_frame=None, is_sequence=False, sequence_fps=24, max_frames=None, loop_forever=True)`; `generate_video_preview(input_path, output_path, max_size=512, duration=10, threads=4)`; `generate_sequence_video_preview(sequence_pattern, output_path, max_size=512, fps=24, start_frame=1, max_frames=None)` (`src/ffmpeg_wrapper.py`).
- `compute_phash(path)` → str/None; `find_duplicates(db, phash, threshold=8, exclude_id=None)` → list[dict]+`distance`; `hamming_distance(a, b)`; `DuplicateDialog` (`src/duplicate_detection.py:59,99,115`).
- `LazyGalleryView(thumb_w=160, thumb_h=120, parent=None)`; `set_elements(elements, thumb_w=None, thumb_h=None)`; `on_preview_ready(element_id, preview_path, preview_type)`; signals `element_clicked(int)`, `element_double_clicked(int)`, `selection_changed(list)`; `_load_visible()`; `visualItemRect(item)` from `QListWidget` (`src/ui/lazy_gallery_view.py:179`).
- `DragGalleryView(db_manager, config, nuke_bridge, parent=None)`; `startDrag`, `insert_to_nuke(element_ids)`, `_resolve_storage_path` (`src/ui/drag_gallery_view.py:14`).
- `MediaDisplayWidget`: gallery built line 164; `ingest_dropped_files(file_paths)` line 320; `_update_views_with_elements(elements)` line 607; `_load_preview_pixmap(element, icon_size)` line 723; `on_preview_ready` line 847; `self.config` is a **`Config` object**; `self.db`, `self.current_list_id`, `self.element_items`, `self.element_flags`.
- `NukeBridge.create_read_node(filepath, frame_range=None, node_name=None)` real-mode parses range at `src/nuke_bridge.py:95`; imports `from src.ingestion_core import SequenceDetector`.
- `main.py`: `self.ingestion = IngestionCore(self.db, self.config.get_all())` (line 96); `perform_ingestion(files, target_list_id)` (line 714); `_start_preview_worker` connects `pw.preview_ready → self.media_display.on_preview_ready` (line 129).
- `Config`: `.get(key, default=None)`, `.set(key, value)`, `.get_all()` (dict copy), `.resolve_path(path)` (`src/config.py`). Key is `default_copy_policy` (`src/config.py:57`).
- `DatabaseManager.create_element(list_id, name, element_type, **kwargs)` → element_id; `get_list_by_id`, `get_stack_by_id`, `create_stack(name, path)`, `create_list(stack_id, name, parent_list_id=None)`, `is_favorite(element_id, ...)`, `get_element_by_id(id)`.

---

## Task 1: Frame-range hardening with Fileseq (L8)

**Files:**
- Modify: `pyproject.toml`, `src/ingestion_core.py`, `src/nuke_bridge.py`
- Create: `tests/unit/test_frame_range_fileseq.py`

**Interfaces:**
- Produces: `parse_frame_range(range_str)` and `SequenceDetector._compact_frame_range(frame_numbers)` in `ingestion_core`; hardened `nuke_bridge.create_read_node` real mode.

- [ ] **Step 1: Add `fileseq` to dependencies**

Edit `pyproject.toml`, adding to the `dependencies` list (keep it sorted):

```toml
    "fileseq>=1.15.0",
```

Then install:
```bash
uv pip install "fileseq>=1.15.0"
```
Expected: `Successfully installed fileseq-...`.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_frame_range_fileseq.py`:

```python
import pytest

from ingestion_core import parse_frame_range, SequenceDetector


@pytest.mark.unit
def test_simple_contiguous_range():
    first, last, frames = parse_frame_range("1-10")
    assert (first, last) == (1, 10)
    assert frames == list(range(1, 11))


@pytest.mark.unit
def test_negative_first_frame():
    first, last, frames = parse_frame_range("-5-10")
    assert first == -5
    assert last == 10
    assert frames[0] == -5


@pytest.mark.unit
def test_stepped_range():
    first, last, frames = parse_frame_range("1-10x2")
    assert first == 1
    assert last == 9
    assert frames == [1, 3, 5, 7, 9]


@pytest.mark.unit
def test_missing_frames_range():
    first, last, frames = parse_frame_range("1-3,5")
    assert first == 1
    assert last == 5
    assert 4 not in frames


@pytest.mark.unit
def test_single_frame_and_blank():
    assert parse_frame_range("7") == (7, 7, [7])
    assert parse_frame_range("") is None
    assert parse_frame_range(None) is None


@pytest.mark.unit
def test_compact_frame_range_contiguous_matches_first_last():
    # Contiguous must still render "first-last" so SP0's characterization holds.
    assert SequenceDetector._compact_frame_range([1, 2, 3, 4]) == "1-4"


@pytest.mark.unit
def test_compact_frame_range_with_gap():
    assert SequenceDetector._compact_frame_range([1, 2, 3, 5]) == "1-3,5"
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `pytest tests/unit/test_frame_range_fileseq.py -v`
Expected: ImportError / AttributeError — `parse_frame_range` and `_compact_frame_range` do not exist yet.

- [ ] **Step 4: Implement in `src/ingestion_core.py`**

At the top of the file, after the existing `import time` and the `from src.glb_converter import (...)` block, add:

```python
import logging

log = logging.getLogger(__name__)

try:
    import fileseq
    _HAS_FILESEQ = True
except ImportError:                       # graceful degradation
    _HAS_FILESEQ = False


def parse_frame_range(range_str):
    """Parse a frame-range string into (first, last, frames_list).

    Uses Fileseq when available so negative frames ('-5-10'), stepped
    ranges ('1-10x2'), and missing frames ('1-3,5') all parse correctly.
    Falls back to a negative-aware regex for the common 'a-b' case.
    Returns None for empty/invalid input.
    """
    if range_str is None:
        return None
    text = str(range_str).strip()
    if not text:
        return None

    if _HAS_FILESEQ:
        try:
            fs = fileseq.FrameSet(text)
            frames = list(fs)
            if frames:
                return frames[0], frames[-1], frames
        except Exception as exc:          # noqa: BLE001 - fall through to regex
            log.debug("fileseq failed to parse %r: %s", text, exc)

    match = re.match(r'^(-?\d+)-(-?\d+)$', text)
    if match:
        a, b = int(match.group(1)), int(match.group(2))
        lo, hi = (a, b) if a <= b else (b, a)
        return lo, hi, list(range(lo, hi + 1))
    try:
        v = int(text)
        return v, v, [v]
    except ValueError:
        return None
```

Then add a classmethod-free static helper inside `class SequenceDetector` (place it just above `get_sequence_path`):

```python
    @staticmethod
    def _compact_frame_range(frame_numbers):
        """Compact a list of frame numbers into a range string.

        Uses Fileseq so gapped sequences render '1-3,5' rather than a
        misleading '1-5'. Contiguous sets render 'first-last'.
        """
        if not frame_numbers:
            return ''
        ordered = sorted(set(frame_numbers))
        if _HAS_FILESEQ:
            try:
                return str(fileseq.FrameSet(ordered).frameRange())
            except Exception as exc:      # noqa: BLE001
                log.debug("fileseq compact failed for %s: %s", ordered, exc)
        return '{}-{}'.format(ordered[0], ordered[-1])
```

In `detect_sequence`, replace the `'frame_range'` line in the returned dict:

```python
                'frame_range': '{}-{}'.format(frame_numbers[0], frame_numbers[-1]),
```
with:
```python
                'frame_range': cls._compact_frame_range(frame_numbers),
```

- [ ] **Step 5: Harden `nuke_bridge.create_read_node` real mode**

In `src/nuke_bridge.py`, change the import line 16:
```python
from src.ingestion_core import SequenceDetector
```
to:
```python
from src.ingestion_core import SequenceDetector, parse_frame_range
```

Replace the real-mode block (lines ~93-100):
```python
            if frame_range:
                # Parse frame range
                parts = frame_range.split('-')
                if len(parts) == 2:
                    first = int(parts[0])
                    last = int(parts[1])
                    node['first'].setValue(first)
                    node['last'].setValue(last)
```
with:
```python
            if frame_range:
                parsed = parse_frame_range(frame_range)
                if parsed:
                    first, last, _frames = parsed
                    node['first'].setValue(first)
                    node['last'].setValue(last)
```

- [ ] **Step 6: Run tests + SP0 characterization (no regression)**

Run: `pytest tests/unit/test_frame_range_fileseq.py tests/unit/test_sequence_detector.py -v`
Expected: all PASS. In particular `test_detects_dot_padded_sequence` still asserts `frame_range == "1-4"` (contiguous → unchanged).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ingestion_core.py src/nuke_bridge.py tests/unit/test_frame_range_fileseq.py
git commit -m "fix: harden frame-range parsing with fileseq (L8)"
```

---

## Task 2: Route PreviewWorker decode through ffmpeg with real padding (M12)

**Files:**
- Modify: `src/preview_worker.py`
- Create: `tests/unit/test_preview_worker_ffmpeg.py`

**Interfaces:**
- Produces: `PreviewJob` with `thumb_path`/`gif_path`/`video_path`/`is_sequence`/`ffmpeg_pattern`/`first_frame`; `PreviewWorker._process` that calls `get_ffmpeg()` and writes to the job's exact paths.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_preview_worker_ffmpeg.py`:

```python
import pytest

import preview_worker
from preview_worker import PreviewJob, PreviewWorker


class _FakeFFmpeg(object):
    def __init__(self):
        self.calls = []

    def generate_sequence_thumbnail(self, pattern, out, max_size=512,
                                    frame_number=None, threads=4):
        self.calls.append(("seq_thumb", pattern, out, frame_number))
        return True

    def generate_thumbnail(self, src, out, max_size=512, frame_time=None, threads=4):
        self.calls.append(("thumb", src, out))
        return True

    def generate_gif_preview(self, *a, **k):
        self.calls.append(("gif", a, k))
        return True

    def generate_sequence_video_preview(self, *a, **k):
        self.calls.append(("seq_video", a, k))
        return True

    def generate_video_preview(self, *a, **k):
        self.calls.append(("video", a, k))
        return True


@pytest.mark.unit
def test_sequence_thumbnail_uses_real_pattern_and_start_frame(monkeypatch):
    fake = _FakeFFmpeg()
    monkeypatch.setattr(preview_worker, "get_ffmpeg", lambda: fake, raising=False)

    emitted = []
    worker = PreviewWorker()
    worker.preview_ready.connect(lambda eid, p, t: emitted.append((eid, p, t)))

    job = PreviewJob(
        element_id=7,
        source_path="/plates/shot.1001.exr",
        output_dir="/prev",
        asset_type="2D",
        frame_range="1001-1100",
        config={"generate_previews": True, "generate_video_previews": False},
        thumb_path="/prev/7_ab.png",
        gif_path=None,
        video_path=None,
        is_sequence=True,
        ffmpeg_pattern="/plates/shot.%04d.exr",
        first_frame=1001,
    )
    worker._process(job)

    kinds = [c[0] for c in fake.calls]
    assert "seq_thumb" in kinds
    seq = next(c for c in fake.calls if c[0] == "seq_thumb")
    # real pattern, NOT a hardcoded %04d guess, and the real start frame
    assert seq[1] == "/plates/shot.%04d.exr"
    assert seq[2] == "/prev/7_ab.png"
    assert seq[3] == 1001
    assert (7, "/prev/7_ab.png", "thumbnail") in emitted


@pytest.mark.unit
def test_single_image_thumbnail_routes_through_ffmpeg_not_pil(monkeypatch):
    fake = _FakeFFmpeg()
    monkeypatch.setattr(preview_worker, "get_ffmpeg", lambda: fake, raising=False)

    worker = PreviewWorker()
    job = PreviewJob(
        element_id=1,
        source_path="/imgs/pic.dpx",     # PIL can't read DPX; ffmpeg can
        output_dir="/prev",
        asset_type="2D",
        config={"generate_previews": True, "generate_video_previews": False},
        thumb_path="/prev/1_x.png",
        is_sequence=False,
    )
    worker._process(job)
    assert any(c[0] == "thumb" and c[1] == "/imgs/pic.dpx" for c in fake.calls)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_preview_worker_ffmpeg.py -v`
Expected: FAIL — `PreviewJob` rejects `thumb_path`/`is_sequence`/`ffmpeg_pattern` kwargs, and `_process` still uses PIL.

- [ ] **Step 3: Extend `PreviewJob` (`src/preview_worker.py`)**

Replace the `__slots__` tuple and `__init__` of `PreviewJob`:

```python
    __slots__ = (
        "element_id", "source_path", "output_dir",
        "asset_type", "frame_range", "config", "priority",
        "thumb_path", "gif_path", "video_path",
        "is_sequence", "ffmpeg_pattern", "first_frame",
    )

    def __init__(
        self,
        element_id,
        source_path,
        output_dir,
        asset_type="2D",
        frame_range=None,
        config=None,
        priority=50,
        thumb_path=None,
        gif_path=None,
        video_path=None,
        is_sequence=False,
        ffmpeg_pattern=None,
        first_frame=1,
    ):
        self.element_id     = element_id
        self.source_path    = source_path
        self.output_dir     = output_dir
        self.asset_type     = asset_type
        self.frame_range    = frame_range
        self.config         = config or {}
        self.priority       = priority
        self.thumb_path     = thumb_path
        self.gif_path       = gif_path
        self.video_path     = video_path
        self.is_sequence    = is_sequence
        self.ffmpeg_pattern = ffmpeg_pattern
        self.first_frame    = first_frame if first_frame is not None else 1
```

- [ ] **Step 4: Add the ffmpeg import and rewrite `_process`**

Near the top of `src/preview_worker.py` (after `from PySide2 import QtCore`), add:
```python
from src.ffmpeg_wrapper import get_ffmpeg
```

Replace the entire `_process` method and the three `_generate_*` static helpers with:

```python
    def _process(self, job):
        cfg = job.config or {}
        if job.output_dir and not os.path.isdir(job.output_dir):
            try:
                os.makedirs(job.output_dir)
            except OSError:
                pass

        try:
            ffmpeg = get_ffmpeg()
        except Exception as exc:           # ffmpeg not available (e.g. SP3 pending on this OS)
            log.warning("PreviewWorker: ffmpeg unavailable — %s", exc)
            return

        try:
            max_size = int(cfg.get("preview_size", 512))
        except (TypeError, ValueError):
            max_size = 512

        # ---- Thumbnail (all 2D; ffmpeg reads EXR/DPX/MXF, unlike PIL) ----
        if cfg.get("generate_previews", True) and job.thumb_path:
            ok = False
            try:
                if job.is_sequence and job.ffmpeg_pattern:
                    ok = ffmpeg.generate_sequence_thumbnail(
                        job.ffmpeg_pattern, job.thumb_path,
                        max_size=max_size, frame_number=job.first_frame,
                    )
                else:
                    ok = ffmpeg.generate_thumbnail(
                        job.source_path, job.thumb_path, max_size=max_size,
                    )
            except Exception as exc:
                log.warning("Thumbnail failed for element %s: %s", job.element_id, exc)
            if ok:
                self.preview_ready.emit(job.element_id, job.thumb_path, "thumbnail")

        if job.asset_type != "2D":
            return

        first, _last, start_frame = self._range_bounds(job)

        # ---- Animated GIF ----
        if job.gif_path:
            gif_input = job.ffmpeg_pattern if (job.is_sequence and job.ffmpeg_pattern) else job.source_path
            try:
                gif_size = int(cfg.get("gif_size", 256))
            except (TypeError, ValueError):
                gif_size = 256
            try:
                gif_fps = int(cfg.get("gif_fps", 10))
            except (TypeError, ValueError):
                gif_fps = 10
            try:
                seq_fps = int(cfg.get("sequence_preview_fps", 24))
            except (TypeError, ValueError):
                seq_fps = 24
            gif_ok = False
            try:
                gif_ok = ffmpeg.generate_gif_preview(
                    gif_input, job.gif_path,
                    max_duration=cfg.get("gif_duration", 3.0),
                    size=gif_size, fps=gif_fps,
                    start_frame=start_frame if job.is_sequence else None,
                    is_sequence=job.is_sequence,
                    sequence_fps=seq_fps,
                )
            except Exception as exc:
                log.warning("GIF failed for element %s: %s", job.element_id, exc)
            if gif_ok:
                self.preview_ready.emit(job.element_id, job.gif_path, "gif")

        # ---- Low-res MP4 (sequences only) ----
        if job.video_path and job.is_sequence and job.ffmpeg_pattern \
                and cfg.get("generate_video_previews", True):
            try:
                seq_fps = int(cfg.get("sequence_preview_fps", 24))
            except (TypeError, ValueError):
                seq_fps = 24
            vid_ok = False
            try:
                vid_ok = ffmpeg.generate_sequence_video_preview(
                    job.ffmpeg_pattern, job.video_path,
                    max_size=512, fps=seq_fps, start_frame=start_frame,
                )
            except Exception as exc:
                log.warning("Video failed for element %s: %s", job.element_id, exc)
            if vid_ok:
                self.preview_ready.emit(job.element_id, job.video_path, "video")

    @staticmethod
    def _range_bounds(job):
        """(first, last, start_frame) — start_frame defaults to job.first_frame."""
        start = job.first_frame if job.first_frame is not None else 1
        return start, start, start
```

Remove the now-dead `import glob` / `import re` / PIL usage that lived only inside the old helpers (they were local imports inside the deleted methods, so nothing else needs changing).

- [ ] **Step 5: Run the test**

Run: `pytest tests/unit/test_preview_worker_ffmpeg.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/preview_worker.py tests/unit/test_preview_worker_ffmpeg.py
git commit -m "fix: route preview worker decode through ffmpeg with real sequence padding (M12)"
```

---

## Task 3: Fix duplicate-detection semantics (L5, part A)

**Files:**
- Modify: `src/duplicate_detection.py`
- Create: `tests/unit/test_duplicate_detection.py`

**Interfaces:**
- Produces: tagged hashes (`"p:"`/`"m:"`) and an MD5-safe `hamming_distance`; `find_duplicates` unchanged in shape.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_duplicate_detection.py`:

```python
import pytest

import duplicate_detection as dd
from duplicate_detection import hamming_distance, find_duplicates


@pytest.mark.unit
def test_identical_hashes_zero_distance():
    assert hamming_distance("p:ffff0000ffff0000", "p:ffff0000ffff0000") == 0


@pytest.mark.unit
def test_two_phashes_use_bit_distance():
    d = hamming_distance("p:ffffffffffffffff", "p:fffffffffffffff0")
    assert 0 < d <= 64


@pytest.mark.unit
def test_md5_fallback_nonequal_is_far_not_hexdecoded():
    # Two different MD5 fallbacks must NEVER be hex_to_hash'd; non-equal => far.
    assert hamming_distance("m:0123456789abcdef", "m:fedcba9876543210") == 999


@pytest.mark.unit
def test_md5_equal_is_zero():
    assert hamming_distance("m:0123456789abcdef", "m:0123456789abcdef") == 0


@pytest.mark.unit
def test_mixed_kinds_never_compared_as_phash():
    assert hamming_distance("p:ffffffffffffffff", "m:ffffffffffffffff") == 999


class _FakeDB(object):
    def __init__(self, rows):
        self._rows = rows

    def get_elements_with_phash(self):
        return self._rows


@pytest.mark.unit
def test_find_duplicates_filters_by_threshold_and_sorts():
    rows = [
        {"element_id": 1, "phash": "p:ffffffffffffffff", "name": "a"},
        {"element_id": 2, "phash": "p:0000000000000000", "name": "b"},  # far
        {"element_id": 3, "phash": "", "name": "c"},                     # no hash
    ]
    dupes = find_duplicates(_FakeDB(rows), "p:ffffffffffffffff", threshold=4)
    ids = [d["element_id"] for d in dupes]
    assert ids == [1]
    assert dupes[0]["distance"] == 0
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_duplicate_detection.py -v`
Expected: FAIL — `hamming_distance("m:...", "m:...")` currently routes through `imagehash.hex_to_hash` and returns a bogus small distance.

- [ ] **Step 3: Implement the tagged-hash semantics**

In `src/duplicate_detection.py`, add constants after `log = logging.getLogger(__name__)`:

```python
_PHASH_PREFIX = "p:"
_MD5_PREFIX = "m:"
```

Change `compute_phash` — the success `return` and the ImportError fallback:

```python
        h    = imagehash.phash(img)
        return _PHASH_PREFIX + str(h)   # tagged perceptual hash
```
and in the `except ImportError:` branch:
```python
        return _md5_hash(path)
```
Update `_md5_hash` to tag its result:
```python
def _md5_hash(path):
    """Fallback: 'm:' + first 16 chars of the file's MD5."""
    try:
        import hashlib
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return _MD5_PREFIX + h.hexdigest()[:16]
    except Exception:
        return None
```

Replace `hamming_distance` entirely:

```python
def hamming_distance(hash_a, hash_b):
    """Hamming distance between two tagged hashes. 0 = identical.

    MD5-fallback ('m:') hashes are compared by exact equality ONLY — they are
    never routed through imagehash.hex_to_hash (which would yield garbage).
    Only two perceptual ('p:') hashes get a true bit distance.
    """
    if hash_a == hash_b:
        return 0
    if not hash_a or not hash_b:
        return 999
    a_is_p = hash_a.startswith(_PHASH_PREFIX)
    b_is_p = hash_b.startswith(_PHASH_PREFIX)
    if not (a_is_p and b_is_p):
        # any MD5 / untagged / mixed pair: exact-equality already failed above
        return 999
    try:
        import imagehash
        return imagehash.hex_to_hash(hash_a[len(_PHASH_PREFIX):]) \
            - imagehash.hex_to_hash(hash_b[len(_PHASH_PREFIX):])
    except Exception:
        return 999
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/unit/test_duplicate_detection.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/duplicate_detection.py tests/unit/test_duplicate_detection.py
git commit -m "fix: MD5-safe duplicate-hash distance semantics via tagged hashes (L5)"
```

---

## Task 4: Wire PreviewJob + dedup into `ingest_file` (C4-part-1, L5 part B)

**Files:**
- Modify: `src/ingestion_core.py`
- Create: `tests/unit/test_ingest_submits_preview_job.py`

**Interfaces:**
- Consumes: `get_preview_queue`, `PreviewJob`, `compute_phash`, `find_duplicates`, SP1's `db.update_element_phash`.
- Produces: `ingest_file` that stores predicted preview paths, checks/stores phash, and submits exactly one `PreviewJob` (no synchronous preview decode).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ingest_submits_preview_job.py`:

```python
import os
import pytest

import ingestion_core
from ingestion_core import IngestionCore


class _FakeQueue(object):
    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)

    def isRunning(self):
        return True


class _FakeDB(object):
    def __init__(self, previews_dir):
        self._pd = previews_dir
        self.phash_calls = []
        self._next = 42

    def get_list_by_id(self, list_id):
        return {"id": list_id, "name": "L", "stack_fk": 1}

    def get_stack_by_id(self, stack_id):
        return {"id": stack_id, "name": "S", "path": self._pd}

    def create_element(self, list_id, name, element_type, **kwargs):
        self.created = dict(kwargs)
        self.created["name"] = name
        return self._next

    def log_ingestion(self, **kwargs):
        pass

    def get_elements_with_phash(self):
        return []

    def update_element_phash(self, element_id, phash):
        self.phash_calls.append((element_id, phash))


@pytest.mark.unit
def test_ingest_submits_one_preview_job_and_stores_paths(tmp_path, monkeypatch, tiny_png):
    queue = _FakeQueue()
    monkeypatch.setattr(ingestion_core, "get_preview_queue", lambda: queue, raising=False)
    # Make sure NO synchronous ffmpeg/PIL decode happens.
    monkeypatch.setattr(ingestion_core, "get_ffmpeg",
                        lambda: (_ for _ in ()).throw(AssertionError("sync decode!")),
                        raising=False)

    db = _FakeDB(str(tmp_path))
    cfg = {"previews_path": str(tmp_path / "prev"),
           "generate_previews": True, "dedup_enabled": True}
    core = IngestionCore(db, cfg)

    result = core.ingest_file(tiny_png, target_list_id=1, copy_policy="soft")

    assert result["success"] is True
    assert len(queue.jobs) == 1
    job = queue.jobs[0]
    assert job.element_id == 42
    assert job.thumb_path == db.created.get("preview_path")
    assert job.thumb_path and job.thumb_path.endswith(".png")
    # phash stored after insert
    assert db.phash_calls and db.phash_calls[0][0] == 42
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/unit/test_ingest_submits_preview_job.py -v`
Expected: FAIL — `ingest_file` still decodes synchronously (hits the `get_ffmpeg` AssertionError) and never submits a job.

- [ ] **Step 3: Add imports to `src/ingestion_core.py`**

After the fileseq import block added in Task 1, add:

```python
from src.preview_worker import get_preview_queue, PreviewJob
from src.duplicate_detection import compute_phash, find_duplicates
```

- [ ] **Step 4: Replace the synchronous preview block in `ingest_file`**

In `ingest_file`, the block from `preview_path = None` (line ~710) through the end of the MP4 generation (`video_preview_path = None ... video_preview_path = None`, line ~849) computes deterministic paths *and* generates the files synchronously. Keep the **path computation**, drop the **generation**, and add dedup + async submission. Replace that whole span with:

```python
            # ---- Compute deterministic preview output paths ----
            preview_path = gif_preview_path = video_preview_path = None
            if self.config.get('generate_previews', True):
                preview_path = os.path.normpath(os.path.join(
                    self.preview_dir, "{}_{}.png".format(target_list_id, element_hash)))
            if is_video or (is_sequence and asset_type == '2D'):
                gif_preview_path = os.path.normpath(os.path.join(
                    self.preview_dir, "{}_{}.gif".format(target_list_id, element_hash)))
            if is_sequence and asset_type == '2D':
                video_preview_path = os.path.normpath(os.path.join(
                    self.preview_dir, "{}_{}.mp4".format(target_list_id, element_hash)))

            # ---- Duplicate detection (before DB insert) ----
            phash = None
            if self.config.get('dedup_enabled', True):
                phash = compute_phash(filepath_soft or source_path)
                if phash:
                    dupes = find_duplicates(
                        self.db, phash,
                        threshold=int(self.config.get('dedup_threshold', 8)))
                    if dupes and self.config.get('dedup_skip_duplicates', False):
                        self.db.log_ingestion(
                            action='ingest', source_path=source_path,
                            target_list=target_list['name'], status='skipped',
                            message='Duplicate of element {}'.format(dupes[0].get('element_id')))
                        return {'success': False, 'reason': 'duplicate_skipped',
                                'message': 'Skipped — duplicate of existing asset.'}
```

Next, `create_element` currently passes `preview_path=preview_db_path` where `preview_db_path` was gated on file existence. Change it to store the **predicted** path (the file arrives shortly after, async):

Replace:
```python
            preview_db_path = preview_path if (preview_path and os.path.exists(preview_path)) else None

            element_id = self.db.create_element(
```
with:
```python
            element_id = self.db.create_element(
```
and change the `preview_path=preview_db_path,` argument inside that call to:
```python
                preview_path=preview_path,
```

Immediately **after** `element_id = self.db.create_element(...)` returns and before `self.db.log_ingestion(...)`, add:

```python
            # ---- Store phash (SP1: update_element_phash) ----
            if phash and hasattr(self.db, 'update_element_phash'):
                try:
                    self.db.update_element_phash(element_id, phash)
                except Exception as exc:
                    log.debug("update_element_phash failed for %s: %s", element_id, exc)

            # ---- Submit async preview job (replaces synchronous generation) ----
            if self.config.get('generate_previews', True):
                ffmpeg_pattern = sequence_pattern_path if is_sequence else None
                first_frame = 1
                if is_sequence and sequence_info:
                    first_frame = sequence_info.get('first_frame') \
                        or sequence_info.get('start_frame') or 1
                get_preview_queue().submit(PreviewJob(
                    element_id=element_id,
                    source_path=filepath_soft or source_path,
                    output_dir=self.preview_dir,
                    asset_type=asset_type,
                    frame_range=frame_range,
                    config=self.config,
                    thumb_path=preview_path,
                    gif_path=gif_preview_path,
                    video_path=video_preview_path,
                    is_sequence=bool(is_sequence),
                    ffmpeg_pattern=ffmpeg_pattern,
                    first_frame=first_frame,
                ))
```

(The `PreviewGenerator` class and its methods remain in the module — unused by `ingest_file` now but harmless and still referenced by tests/other callers; "wire up, don't delete".)

- [ ] **Step 5: Run the test + regression**

Run: `pytest tests/unit/test_ingest_submits_preview_job.py tests/unit/test_sequence_detector.py -v`
Expected: PASS. The AssertionError guard proves no synchronous decode runs.

- [ ] **Step 6: Commit**

```bash
git add src/ingestion_core.py tests/unit/test_ingest_submits_preview_job.py
git commit -m "feat: ingest_file submits async PreviewJob and wires duplicate detection (C4, L5)"
```

---

## Task 5: Shared `IngestWorker(QThread)` (C4-part-3)

**Files:**
- Create: `src/ingest_worker.py`, `tests/gui/test_ingest_worker.py`

**Interfaces:**
- Produces: `IngestWorker(db, config_dict, jobs, copy_policy)` with signals `progress`, `file_done`, `ingest_finished`, `ingest_failed`, and `cancel()`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ingest_worker.py`:

```python
import pytest

from ingest_worker import IngestWorker


class _FakeCore(object):
    """Stand-in for IngestionCore used by IngestWorker."""
    instances = []

    def __init__(self, db, config):
        self.config = config
        _FakeCore.instances.append(self)

    def ingest_file(self, source_path, target_list_id, copy_policy='soft'):
        if "bad" in source_path:
            return {"success": False, "message": "boom"}
        if "dup" in source_path:
            return {"success": False, "reason": "duplicate_skipped"}
        return {"success": True, "element_id": 1}


@pytest.mark.gui
def test_ingest_worker_tallies_and_emits_finished(qtbot, monkeypatch):
    import ingest_worker
    monkeypatch.setattr(ingest_worker, "IngestionCore", _FakeCore, raising=True)

    jobs = [("/a/ok.png", 1), ("/a/dup.png", 1), ("/a/bad.png", 1)]
    worker = IngestWorker(db=object(), config={"k": "v"}, jobs=jobs, copy_policy="soft")

    with qtbot.waitSignal(worker.ingest_finished, timeout=5000) as blocker:
        worker.start()
    assert blocker.args == [1, 1, 1]     # success, skipped, errors
    worker.wait(2000)


@pytest.mark.gui
def test_ingest_worker_passes_dict_config(qtbot, monkeypatch):
    import ingest_worker
    _FakeCore.instances = []
    monkeypatch.setattr(ingest_worker, "IngestionCore", _FakeCore, raising=True)

    worker = IngestWorker(db=object(), config={"k": "v"}, jobs=[("/a/ok.png", 1)],
                          copy_policy="soft")
    with qtbot.waitSignal(worker.ingest_finished, timeout=5000):
        worker.start()
    worker.wait(2000)
    assert _FakeCore.instances[0].config == {"k": "v"}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/gui/test_ingest_worker.py -v`
Expected: FAIL — `ingest_worker` module does not exist.

- [ ] **Step 3: Implement `src/ingest_worker.py`**

```python
# -*- coding: utf-8 -*-
"""Shared background ingestion worker for StaX.

Runs IngestionCore.ingest_file over a flat list of (source_path, list_id)
jobs off the GUI thread, reporting progress and a final tally via signals.
Replaces the in-loop GUI-thread ingestion and QApplication.processEvents().
"""

import logging

from PySide2 import QtCore

from src.ingestion_core import IngestionCore

log = logging.getLogger(__name__)


class IngestWorker(QtCore.QThread):
    """QThread that ingests a list of (source_path, target_list_id) jobs.

    Signals
    -------
    progress(int done, int total, str label)
    file_done(dict result)
    ingest_finished(int success, int skipped, int errors)
    ingest_failed(str message)
    """

    progress        = QtCore.Signal(int, int, str)
    file_done       = QtCore.Signal(dict)
    ingest_finished = QtCore.Signal(int, int, int)
    ingest_failed   = QtCore.Signal(str)

    def __init__(self, db, config, jobs, copy_policy="soft", parent=None):
        super(IngestWorker, self).__init__(parent)
        self.db = db
        self.config = config          # MUST be a plain dict (Config.get_all())
        self.jobs = list(jobs)
        self.copy_policy = copy_policy
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import os
        success = skipped = errors = 0
        total = len(self.jobs)
        try:
            core = IngestionCore(self.db, self.config)
            for i, (source_path, list_id) in enumerate(self.jobs, start=1):
                if self._cancelled:
                    break
                label = os.path.basename(source_path)
                self.progress.emit(i, total, label)
                result = core.ingest_file(source_path, list_id,
                                          copy_policy=self.copy_policy)
                if isinstance(result, dict):
                    self.file_done.emit(result)
                    if result.get("success"):
                        success += 1
                    elif result.get("reason") == "duplicate_skipped":
                        skipped += 1
                    else:
                        errors += 1
                else:
                    errors += 1
            self.ingest_finished.emit(success, skipped, errors)
        except Exception as exc:               # noqa: BLE001
            log.exception("IngestWorker crashed")
            self.ingest_failed.emit(str(exc))
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/gui/test_ingest_worker.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ingest_worker.py tests/gui/test_ingest_worker.py
git commit -m "feat: shared IngestWorker QThread for signal-driven ingestion (C4)"
```

---

## Task 6: Drive `perform_ingestion` and library ingest via `IngestWorker` (C4-part-3)

**Files:**
- Modify: `main.py`, `src/ui/ingest_library_dialog.py`

**Interfaces:**
- Consumes: `IngestWorker`. Removes the GUI-thread blocking `for` loops.

- [ ] **Step 1: Refactor `main.perform_ingestion`**

Add near the other imports in `main.py` (with the `from src.` group):
```python
from src.ingest_worker import IngestWorker
```

Replace `perform_ingestion` (lines ~714-743) with a signal-driven version that holds a member reference to the worker:

```python
    def perform_ingestion(self, files, target_list_id):
        jobs = [(f, target_list_id) for f in files]
        progress = QtWidgets.QProgressDialog(
            "Ingesting files...", "Cancel", 0, len(jobs), self
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)

        worker = IngestWorker(
            self.db, self.config.get_all(), jobs,
            copy_policy=self.config.get("default_copy_policy"),
        )
        self._ingest_worker = worker            # keep a reference alive

        worker.progress.connect(
            lambda done, total, label: (
                progress.setValue(done - 1),
                progress.setLabelText("Ingesting: {}".format(label)),
            )
        )
        progress.canceled.connect(worker.cancel)
        worker.ingest_finished.connect(
            lambda s, k, e: self._on_perform_ingestion_done(progress, s, k, e)
        )
        worker.ingest_failed.connect(
            lambda msg: self._on_perform_ingestion_failed(progress, msg)
        )
        worker.start()
        progress.exec_()

    def _on_perform_ingestion_done(self, progress, success, skipped, errors):
        progress.reset()
        msg = "Ingested {} file(s) successfully.".format(success)
        if skipped:
            msg += "\n{} skipped (duplicates).".format(skipped)
        if errors:
            msg += "\n{} error(s).".format(errors)
        QtWidgets.QMessageBox.information(self, "Ingestion Complete", msg)
        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)

    def _on_perform_ingestion_failed(self, progress, message):
        progress.reset()
        QtWidgets.QMessageBox.critical(self, "Ingestion Error", message)
```

- [ ] **Step 2: Refactor `ingest_library_dialog.start_ingestion`**

The current `start_ingestion` (lines ~365-476) interleaves DB structure creation with a blocking ingest loop. Split it: build the structure on the GUI thread, collect a flat job list, then hand it to an `IngestWorker`.

Add to the imports at the top of `src/ui/ingest_library_dialog.py`:
```python
from src.ingest_worker import IngestWorker
```

Replace `start_ingestion` and its `_ingest_lists_recursive` helper (lines ~365-476) with:

```python
    def start_ingestion(self):
        """Build the Stacks/Lists structure, then ingest files off-thread."""
        if not self.scanned_structure:
            QtWidgets.QMessageBox.warning(self, "No Structure", "Please scan a folder first.")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Ingestion",
            "Start bulk ingestion?\n\nThis will create Stacks/Lists and ingest all media files.\n"
            "This operation may take several minutes.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        # --- Build DB structure (fast, GUI thread) and collect ingest jobs ---
        jobs = []
        try:
            for stack_name, stack_data in self.scanned_structure.items():
                stack_id = self.db.create_stack(stack_name, stack_data['path'])
                if stack_data['files'] and not stack_data['lists']:
                    root_list_id = self.db.create_list(stack_id, "_root")
                    for filepath in stack_data['files']:
                        jobs.append((filepath, root_list_id))
                self._collect_list_jobs(stack_id, None, stack_data['lists'], jobs)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Ingestion Error", "Failed: {}".format(str(exc)))
            return

        if not jobs:
            QtWidgets.QMessageBox.information(self, "Nothing to Ingest", "No media files found.")
            return

        copy_policy = self.copy_policy_combo.currentText()
        progress = QtWidgets.QProgressDialog("Ingesting library...", "Cancel", 0, len(jobs), self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)

        config_dict = self.config.get_all() if hasattr(self.config, "get_all") else self.config
        worker = IngestWorker(self.db, config_dict, jobs, copy_policy=copy_policy)
        self._ingest_worker = worker

        worker.progress.connect(
            lambda done, total, label: (
                progress.setValue(done - 1),
                progress.setLabelText("Ingesting: {}".format(label)),
            )
        )
        progress.canceled.connect(worker.cancel)
        worker.ingest_finished.connect(
            lambda s, k, e: self._on_library_ingest_done(progress, s, k, e)
        )
        worker.ingest_failed.connect(
            lambda msg: (progress.reset(),
                         QtWidgets.QMessageBox.critical(self, "Ingestion Error", msg))
        )
        worker.start()
        progress.exec_()

    def _collect_list_jobs(self, stack_id, parent_list_id, lists_dict, jobs):
        """Recursively create lists and append (filepath, list_id) jobs."""
        for list_name, list_data in lists_dict.items():
            list_id = self.db.create_list(stack_id, list_name, parent_list_id=parent_list_id)
            for filepath in list_data['files']:
                jobs.append((filepath, list_id))
            self._collect_list_jobs(stack_id, list_id, list_data['sub_lists'], jobs)

    def _on_library_ingest_done(self, progress, success, skipped, errors):
        progress.reset()
        QtWidgets.QMessageBox.information(
            self, "Ingestion Complete",
            "Library ingested!\n\n{} files ingested\n{} skipped\n{} errors".format(
                success, skipped, errors)
        )
        self.accept()
```

- [ ] **Step 3: Verify no blocking loops / processEvents remain in these paths**

Run:
```bash
grep -n "processEvents" main.py src/ui/ingest_library_dialog.py
```
Expected: no matches in these two files. (`grep` may exit non-zero when nothing matches — that is the success case here.)

- [ ] **Step 4: Smoke-construct MainWindow (headless) to confirm no import/wiring break**

Run: `pytest tests/gui/test_mainwindow_smoke.py -v`
Expected: PASS (or the pre-existing SP0 status for that test — it must not newly ERROR on import of `IngestWorker`).

- [ ] **Step 5: Commit**

```bash
git add main.py src/ui/ingest_library_dialog.py
git commit -m "refactor: drive perform_ingestion and library ingest via IngestWorker signals (C4)"
```

---

## Task 7: Adopt LazyGalleryView + fix drop-ingest (C4-part-2, H7)

**Files:**
- Modify: `src/ui/lazy_gallery_view.py`, `src/ui/drag_gallery_view.py`, `src/ui/media_display_widget.py`
- Create: `tests/gui/test_drag_gallery_is_lazy.py`, `tests/gui/test_media_display_dropingest.py`

**Interfaces:**
- Produces: `DragGalleryView` subclassing `LazyGalleryView` with an item-loader hook; H7-correct `ingest_dropped_files` using `IngestWorker`.

- [ ] **Step 1: Add the item-loader hook to `LazyGalleryView`**

In `src/ui/lazy_gallery_view.py`, in `LazyGalleryView.__init__`, after `self._element_index = {}`, add:
```python
        self._item_loader = None       # optional host callback: fn(item) -> loads icon
```

Add two methods (place after `set_elements`):
```python
    def set_item_loader(self, loader):
        """Register a host callback fn(item) that loads a single item's icon.

        When set, _load_visible calls it for visible items instead of the
        built-in GalleryItem.load_pixmap, so a host can keep its own decode
        (badges, GIF first-frame) while staying viewport-bounded.
        """
        self._item_loader = loader

    def clear_item_loader(self):
        self._item_loader = None
```

In `_load_visible`, replace the per-item load/evict body. Change:
```python
            if expanded.intersects(rect):
                item.load_pixmap()
            elif item._loaded and not evict_zone.intersects(rect):
```
to:
```python
            if expanded.intersects(rect):
                if self._item_loader is not None:
                    self._item_loader(item)
                elif isinstance(item, GalleryItem):
                    item.load_pixmap()
            elif getattr(item, "_loaded", False) and not evict_zone.intersects(rect):
```
and keep the existing eviction block that resets the icon to a placeholder and sets `item._loaded = False`. Also relax the top guard `if not isinstance(item, GalleryItem): continue` to allow plain items when a loader is set:
```python
            item = self.item(i)
            if item is None:
                continue
            if self._item_loader is None and not isinstance(item, GalleryItem):
                continue
```

- [ ] **Step 2: Make `DragGalleryView` subclass `LazyGalleryView`**

In `src/ui/drag_gallery_view.py`, change the import and class declaration/constructor. Replace:
```python
from PySide2 import QtWidgets, QtCore, QtGui

from src.ingestion_core import SequenceDetector


class DragGalleryView(QtWidgets.QListWidget):
    """Custom QListWidget with drag & drop support for Nuke integration."""

    def __init__(self, db_manager, config, nuke_bridge, parent=None):
        super(DragGalleryView, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.nuke_bridge = nuke_bridge
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.setDragEnabled(True)
        self.setAcceptDrops(False)  # We don't accept drops, only drag out
```
with:
```python
from PySide2 import QtWidgets, QtCore, QtGui

from src.ingestion_core import SequenceDetector
from src.ui.lazy_gallery_view import LazyGalleryView


class DragGalleryView(LazyGalleryView):
    """Lazy-loading gallery with drag & drop support for Nuke integration."""

    def __init__(self, db_manager, config, nuke_bridge, parent=None):
        super(DragGalleryView, self).__init__(parent=parent)
        self.db = db_manager
        self.config = config
        self.nuke_bridge = nuke_bridge
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.setDragEnabled(True)
        self.setAcceptDrops(False)  # We don't accept drops, only drag out
```
(`startDrag`, `insert_to_nuke`, `_resolve_storage_path` are unchanged and inherited-compatible.)

- [ ] **Step 3: Defer MediaDisplayWidget decode to the lazy loader**

In `src/ui/media_display_widget.py`, `_update_views_with_elements` (line 607): the per-item block currently decodes every static preview synchronously (`self._load_preview_pixmap(...)`, lines ~662-667). Replace that `if not has_gif:` block:
```python
            if not has_gif:
                static_pixmap = self._load_preview_pixmap(element, icon_size)
                if static_pixmap:
                    item.setIcon(QtGui.QIcon(static_pixmap))
                else:
                    item.setIcon(self._get_default_icon_for_type(element.get('type'), icon_size))
```
with a placeholder + stash of the element for lazy loading:
```python
            if not has_gif:
                # Defer decode to the lazy loader; show the type fallback now.
                item.setIcon(self._get_default_icon_for_type(element.get('type'), icon_size))
                item.setData(QtCore.Qt.UserRole + 1, element)
```

At the end of `_update_views_with_elements`, register the item-loader (once) so visible items decode on demand. After the gallery/table population loops, add:
```python
        if hasattr(self.gallery_view, "set_item_loader"):
            self.gallery_view.set_item_loader(self._lazy_load_gallery_item)
```

Add the loader method to `MediaDisplayWidget` (near `_load_preview_pixmap`):
```python
    def _lazy_load_gallery_item(self, item):
        """Decode a single gallery item's static preview when it becomes visible."""
        if item is None or item.data(QtCore.Qt.UserRole + 1) is None:
            return
        element = item.data(QtCore.Qt.UserRole + 1)
        icon_size = self.gallery_view.iconSize()
        pixmap = self._load_preview_pixmap(element, icon_size)
        if pixmap:
            item.setIcon(QtGui.QIcon(pixmap))
        # Loaded once — drop the stash so we don't redecode.
        item.setData(QtCore.Qt.UserRole + 1, None)
```

(GIF items keep their existing first-frame handling; only the static-preview page-decode is deferred. `on_preview_ready`, line 847, still updates a specific item when the worker finishes.)

- [ ] **Step 4: Fix drop-ingest (H7) to use `IngestWorker`**

Replace `ingest_dropped_files` (lines ~320-411) with a member-held `IngestWorker` that passes `config.get_all()` and `default_copy_policy`:

```python
    def ingest_dropped_files(self, file_paths):
        """Ingest dropped files into the current list, off the GUI thread."""
        from src.ui.dialogs import IngestProgressDialog
        from src.ingest_worker import IngestWorker

        if not self.current_list_id:
            QtWidgets.QMessageBox.information(
                self, "No List Selected", "Select a list before ingesting.")
            return

        jobs = [(p, self.current_list_id) for p in file_paths]
        dialog = IngestProgressDialog(self)
        dialog.setWindowTitle("Ingesting Files...")

        # H7: pass a dict (get_all), correct key (default_copy_policy).
        config_dict = self.config.get_all() if hasattr(self.config, "get_all") else self.config
        copy_policy = (config_dict.get("default_copy_policy", "soft")
                       if isinstance(config_dict, dict) else "soft")

        worker = IngestWorker(self.db, config_dict, jobs, copy_policy=copy_policy)
        self._ingest_worker = worker      # H7: hold a member reference until finished

        worker.progress.connect(
            lambda done, total, label: dialog.update_progress(done, total, label))
        worker.ingest_finished.connect(
            lambda s, k, e: self._on_ingest_complete(dialog))
        worker.ingest_failed.connect(
            lambda err: self._on_ingest_failed(dialog, err))
        dialog.rejected.connect(worker.cancel)

        worker.start()
        dialog.exec_()
```

Update the two completion handlers (lines ~413-430) to match the new signatures (they previously took a `thread` arg):
```python
    def _on_ingest_complete(self, dialog):
        """Handle successful ingestion completion."""
        dialog.accept()
        if self.current_list_id:
            self.load_elements(self.current_list_id)

    def _on_ingest_failed(self, dialog, error_message):
        """Handle ingestion failure."""
        dialog.reject()
        QtWidgets.QMessageBox.critical(self, "Ingestion Error", error_message)
```

- [ ] **Step 5: Write the tests**

Create `tests/gui/test_drag_gallery_is_lazy.py`:
```python
import pytest

from ui.drag_gallery_view import DragGalleryView
from ui.lazy_gallery_view import LazyGalleryView


@pytest.mark.gui
def test_drag_gallery_is_a_lazy_gallery(qtbot, stax_config):
    from nuke_bridge import NukeBridge
    view = DragGalleryView(db_manager=None, config=stax_config,
                           nuke_bridge=NukeBridge(mock_mode=True))
    qtbot.addWidget(view)
    assert isinstance(view, LazyGalleryView)
    assert hasattr(view, "insert_to_nuke")
    assert hasattr(view, "on_preview_ready")
    assert hasattr(view, "set_item_loader")
```

Create `tests/gui/test_media_display_dropingest.py`:
```python
import pytest


@pytest.mark.gui
def test_drop_ingest_passes_dict_config_and_default_copy_policy(
        qtbot, stax_db, stax_config, monkeypatch):
    import ingest_worker

    captured = {}

    class _SpyWorker(ingest_worker.IngestWorker):
        def __init__(self, db, config, jobs, copy_policy="soft", parent=None):
            captured["config"] = config
            captured["copy_policy"] = copy_policy
            super(_SpyWorker, self).__init__(db, config, jobs, copy_policy, parent)

        def start(self):
            # don't actually run a thread in the test
            self.ingest_finished.emit(0, 0, 0)

    monkeypatch.setattr(ingest_worker, "IngestWorker", _SpyWorker, raising=True)

    from ui.media_display_widget import MediaDisplayWidget
    from nuke_bridge import NukeBridge

    stax_config.set("default_copy_policy", "hard")
    widget = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(widget)
    widget.current_list_id = 1

    # IngestProgressDialog.exec_ would block; stub it.
    monkeypatch.setattr("ui.dialogs.IngestProgressDialog.exec_", lambda self: 0)

    widget.ingest_dropped_files(["/some/file.png"])

    assert isinstance(captured["config"], dict)          # H7: dict, not Config
    assert captured["copy_policy"] == "hard"             # H7: default_copy_policy
    assert getattr(widget, "_ingest_worker", None) is not None  # H7: member ref
```

> If `MediaDisplayWidget.__init__`'s real signature differs from `(db, config, nuke_bridge)`, read `src/ui/media_display_widget.py` around line 17 and adjust the construction in the test only — do not change the widget. If constructing the full widget pulls in unavailable services, narrow the test to call `ingest_dropped_files` on a minimally-built instance via `MediaDisplayWidget.__new__` with the attributes it reads (`db`, `config`, `current_list_id`), and note the reduction in the commit message.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/gui/test_drag_gallery_is_lazy.py tests/gui/test_media_display_dropingest.py -v`
Expected: PASS (2 files). If `test_media_display_dropingest` reveals the widget eagerly hits an SP1-missing DB method during construction, mark it `@pytest.mark.xfail(reason="depends on SP1 DB method", strict=False)` and record it — do not fix a DB defect here.

- [ ] **Step 7: Commit**

```bash
git add src/ui/lazy_gallery_view.py src/ui/drag_gallery_view.py src/ui/media_display_widget.py tests/gui/test_drag_gallery_is_lazy.py tests/gui/test_media_display_dropingest.py
git commit -m "feat: adopt LazyGalleryView in gallery and fix drop-ingest config/thread (C4, H7)"
```

---

## Task 8: Delete the orphaned patch + integration pass

**Files:**
- Delete: `src/ingestion_core_patch.py`
- Create: `tests/nuke/test_nuke_bridge_frame_range.py`

**Interfaces:**
- Consumes everything above.

- [ ] **Step 1: Confirm nothing imports the patch**

Run:
```bash
grep -rn "ingestion_core_patch" --include="*.py" .
```
Expected: no matches (the patch was never imported — only Task 4 replaced its intent). If a match appears, stop and reconcile before deleting.

- [ ] **Step 2: Delete it**

```bash
git rm src/ingestion_core_patch.py
```

- [ ] **Step 3: Add the nuke-tier frame-range regression test**

Create `tests/nuke/test_nuke_bridge_frame_range.py`:
```python
import pytest

from nuke_bridge import NukeBridge


class _Knob(object):
    def __init__(self):
        self.v = None
    def setValue(self, v):
        self.v = v


class _Node(dict):
    def __init__(self):
        super(_Node, self).__init__()
        self["first"] = _Knob()
        self["last"] = _Knob()
    def setName(self, n):
        pass


@pytest.mark.nuke
@pytest.mark.parametrize("rng,first,last", [
    ("-5-10", -5, 10),      # negative first frame (old split('-') broke here)
    ("1-10x2", 1, 9),       # stepped range
    ("1001-1100", 1001, 1100),
])
def test_real_mode_frame_range_parsing(mock_nuke, rng, first, last):
    node = _Node()
    mock_nuke.nodes.Read = lambda **kw: node

    bridge = NukeBridge(mock_mode=False)
    bridge.nuke = mock_nuke
    bridge.create_read_node("/plates/shot.%04d.exr", frame_range=rng, node_name="R")

    assert node["first"].v == first
    assert node["last"].v == last
```

- [ ] **Step 4: Run the full SP2 surface + the whole suite**

Run:
```bash
pytest tests/unit/test_frame_range_fileseq.py tests/unit/test_preview_worker_ffmpeg.py tests/unit/test_duplicate_detection.py tests/unit/test_ingest_submits_preview_job.py tests/gui/test_ingest_worker.py tests/gui/test_drag_gallery_is_lazy.py tests/nuke/test_nuke_bridge_frame_range.py -v
```
Expected: all PASS.

Then the full gate:
```bash
pytest -m "not manual"
```
Expected: **0 failed, 0 errored**; SP0's C1 `xfail`s remain `xfail` (untouched). Note the xfail/pass counts.

- [ ] **Step 5: Commit**

```bash
git add tests/nuke/test_nuke_bridge_frame_range.py
git commit -m "test: nuke-tier frame-range regression; remove applied ingestion_core_patch (C4)"
```

---

## Self-Review

**1. Spec coverage:**
- C4-1 (feed PreviewWorker) → Task 4 (ingest_file submits PreviewJob) ✓
- C4-2 (instantiate LazyGalleryView) → Task 7 (DragGalleryView subclasses LazyGalleryView; viewport-bounded decode) ✓
- C4-3 (ingestion off GUI thread, replace processEvents/blocking loops) → Tasks 5–6 (IngestWorker; perform_ingestion + library ingest) + Task 7 (drop-ingest) ✓
- C4 (delete ingestion_core_patch.py) → Task 8 ✓
- H7 (dict config, default_copy_policy, member-held worker) → Task 7 Step 4 + test ✓
- M12 (ffmpeg decode for EXR/DPX; real padding) → Task 2 ✓
- L8 (fileseq frame-range; nuke_bridge parse) → Task 1 ✓
- L5 (wire dedup into ingest; MD5-safe distance) → Task 3 (semantics) + Task 4 (wiring: compute before insert, store after) ✓
- `fileseq` added to pyproject → Task 1 Step 1 ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every step shows complete code and exact commands. Fallback instructions (widget-construction variance in Task 7, xfail guidance) specify the exact alternative and forbid fixing product defects outside scope.

**3. Type consistency:**
- `IngestWorker(db, config, jobs, copy_policy)` — `config` is a **dict** everywhere it is constructed (`self.config.get_all()` in main/library/drop-ingest); Task 5 tests assert the dict is passed through (H7). `jobs` is `list[(str, int)]`.
- `PreviewJob` new kwargs (`thumb_path`, `gif_path`, `video_path`, `is_sequence`, `ffmpeg_pattern`, `first_frame`) defined in Task 2 and populated by `ingest_file` in Task 4 with matching names; the worker reads the same names in `_process`.
- Deterministic-path contract: `ingest_file` stores `preview_path` in `create_element` **and** passes it as the job's `thumb_path` (Task 4); Task 4's test asserts `job.thumb_path == db.created["preview_path"]`.
- `hamming_distance` returns `int` (0 / bit-distance / 999); `find_duplicates` adds a `distance` key and sorts — matched in Task 3's test and consumed by `DuplicateDialog`'s existing `distance/64.0` similarity math.
- `parse_frame_range` → `(int, int, list[int])` or `None`; consumed by `nuke_bridge.create_read_node` (unpacks `first, last, _`) — verified in Task 1 + Task 8 tests.
- `SequenceDetector.detect_sequence` dict keys (`ffmpeg_pattern`, `first_frame`, `frame_range`) match `src/ingestion_core.py`; contiguous `frame_range` stays `"first-last"` so SP0's `test_detects_dot_padded_sequence` is not regressed (asserted in Task 1 Step 6).
- `get_ffmpeg()` methods (`generate_thumbnail`, `generate_sequence_thumbnail`, `generate_gif_preview`, `generate_sequence_video_preview`, `generate_video_preview`) match `src/ffmpeg_wrapper.py` signatures used in Task 2.

**4. Dependency ordering:** Task 1 (fileseq/parse) → Task 2 (worker) → Task 3 (dedup semantics) → Task 4 (ingest_file consumes 2+3) → Task 5 (IngestWorker consumes ingest_file) → Task 6 (callers consume 5) → Task 7 (gallery + drop-ingest consume 5) → Task 8 (delete + integration). No forward references.

---

## Notes for the executor
- **SP1 is a dependency.** If `stax_db` lacks `update_element_phash`/`get_elements_with_phash`, the dedup **unit** tests still pass (they use an in-test fake DB); the ingest integration test's `_FakeDB` provides them. Do not add DB methods here — that is SP1's job.
- **Never weaken a test to make CI pass.** If a GUI-tier test reveals an unfixed SP1 defect during widget construction, mark it `xfail` with the issue id and move on.
- Run the relevant `pytest` selection before every commit; run `pytest -m "not manual"` before the final commit of Task 8.
- Keep `PreviewGenerator` and the `DuplicateDialog` class in place (unused-by-ingest but not dead program-wide) — "wire up, don't delete".
- Do **not** touch ffmpeg binary naming (SP3), the `QMovie`/icon caches (SP6), or `IMPLEMENTATION_PROGRESS.md`.
