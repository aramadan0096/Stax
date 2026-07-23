# -*- coding: utf-8 -*-
"""
StaX — Async Preview Worker  (Feature 1)
=========================================
Moves thumbnail / GIF / video preview generation completely off the main
thread so the UI never freezes during ingestion.

Architecture
------------
  PreviewWorker   – QThread subclass that drains a Queue of PreviewJob items.
  PreviewQueue    – Singleton facade used by IngestionCore to submit jobs and
                    by the GUI to subscribe to completion signals.

Signals
-------
  preview_ready(int element_id, str preview_path, str preview_type)
      Emitted on the main thread when a preview has been written to disk.
      preview_type is one of: 'thumbnail', 'gif', 'video'

  job_failed(int element_id, str error_message)
      Emitted when preview generation fails for an element.

  queue_empty()
      Emitted when the worker drains to idle.

Usage
-----
In IngestionCore.ingest_file() — after saving the element to the DB — instead
of calling _generate_previews() inline, do:

    from src.preview_worker import get_preview_queue
    get_preview_queue().submit(PreviewJob(
        element_id  = element_id,
        source_path = filepath,
        output_dir  = previews_dir,
        asset_type  = element_type,   # '2D', '3D', 'Toolset'
        frame_range = frame_range,    # e.g. '1001-1100' or None
        config      = self.config,
    ))

In MainWindow.setup_ui() connect once:

    from src.preview_worker import get_preview_queue
    q = get_preview_queue()
    q.preview_ready.connect(self.media_display.on_preview_ready)
    q.job_failed.connect(self._on_preview_failed)
    q.start()
"""

from __future__ import absolute_import, print_function, unicode_literals

import os
import logging
import traceback

try:
    import queue
except ImportError:                 # Python 2
    import Queue as queue           # noqa: F401

from PySide2 import QtCore

from src.ffmpeg_wrapper import get_ffmpeg

log = logging.getLogger(__name__)

# Sentinel that tells the worker thread to exit cleanly.
_STOP_SENTINEL = None


# ---------------------------------------------------------------------------
# Data class for a single preview job
# ---------------------------------------------------------------------------

class PreviewJob(object):
    """
    Immutable description of one preview-generation task.

    Parameters
    ----------
    element_id  : int
    source_path : str   absolute path to the media file (first frame for seqs)
    output_dir  : str   directory where preview files should be written
    asset_type  : str   '2D', '3D', or 'Toolset'
    frame_range : str or None   e.g. '1001-1100'
    config      : dict  copy of the StaX config dict (thread-safe snapshot)
    priority    : int   lower = higher priority  (default 50)
    """

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

    # Allow PriorityQueue ordering
    def __lt__(self, other):
        return self.priority < other.priority


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class PreviewWorker(QtCore.QThread):
    """
    Background thread that processes PreviewJob items one at a time.

    All signals are emitted from *this* thread but Qt's auto-connection
    mechanism safely marshals them to the main thread.
    """

    preview_ready = QtCore.Signal(int, str, str)   # (element_id, path, type)
    job_failed    = QtCore.Signal(int, str)         # (element_id, message)
    queue_empty   = QtCore.Signal()

    def __init__(self, parent=None):
        super(PreviewWorker, self).__init__(parent)
        self._queue    = queue.PriorityQueue()
        self._running  = False
        self.setObjectName("StaX-PreviewWorker")
        self.daemon = True

    # ------------------------------------------------------------------
    # Public API (called from the main thread)
    # ------------------------------------------------------------------

    def submit(self, job):
        """Enqueue a PreviewJob.  Thread-safe."""
        self._queue.put((job.priority, job))

    def stop(self):
        """Request a clean shutdown after the current job finishes."""
        self._running = False
        # Unblock the queue.get() call
        self._queue.put((_STOP_SENTINEL, _STOP_SENTINEL))

    def pending_count(self):
        """Approximate number of jobs waiting (main-thread estimate)."""
        return self._queue.qsize()

    # ------------------------------------------------------------------
    # QThread.run() — executed on the worker thread
    # ------------------------------------------------------------------

    def run(self):
        self._running = True
        log.debug("PreviewWorker started.")

        while self._running:
            try:
                priority, job = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._queue.empty():
                    self.queue_empty.emit()
                continue

            if job is _STOP_SENTINEL:
                break

            try:
                self._process(job)
            except Exception as exc:
                log.error(
                    "PreviewWorker: job %d failed — %s",
                    job.element_id, exc,
                )
                log.debug(traceback.format_exc())
                self.job_failed.emit(
                    job.element_id,
                    "{}: {}".format(type(exc).__name__, exc),
                )
            finally:
                self._queue.task_done()

            if self._queue.empty():
                self.queue_empty.emit()

        log.debug("PreviewWorker stopped.")

    # ------------------------------------------------------------------
    # Private: actual preview generation logic (mirrors IngestionCore's
    # existing _generate_previews, but runs off-thread)
    # ------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Singleton PreviewQueue facade
# ---------------------------------------------------------------------------

_GLOBAL_WORKER = None   # type: PreviewWorker | None


def get_preview_queue():
    """
    Return the application-wide PreviewWorker singleton.
    Creates and starts it on first call.
    """
    global _GLOBAL_WORKER
    if _GLOBAL_WORKER is None:
        _GLOBAL_WORKER = PreviewWorker()
    return _GLOBAL_WORKER


def shutdown_preview_queue():
    """
    Gracefully stop the worker.  Call from MainWindow.closeEvent().
    """
    global _GLOBAL_WORKER
    if _GLOBAL_WORKER is not None and _GLOBAL_WORKER.isRunning():
        _GLOBAL_WORKER.stop()
        _GLOBAL_WORKER.wait(3000)   # wait up to 3 s
    _GLOBAL_WORKER = None
