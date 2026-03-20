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
    ):
        self.element_id  = element_id
        self.source_path = source_path
        self.output_dir  = output_dir
        self.asset_type  = asset_type
        self.frame_range = frame_range
        self.config      = config or {}
        self.priority    = priority

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
        import time
        asset_type  = job.asset_type or "2D"
        source      = job.source_path
        out_dir     = job.output_dir
        element_id  = job.element_id
        cfg         = job.config

        os.makedirs(out_dir) if not os.path.isdir(out_dir) else None

        stem = "element_{:06d}".format(element_id)

        # ---- Thumbnail ------------------------------------------------
        thumb_path = self._generate_thumbnail(source, out_dir, stem, cfg)
        if thumb_path:
            self.preview_ready.emit(element_id, thumb_path, "thumbnail")

        # ---- Animated GIF (2D / sequences only) -----------------------
        if asset_type == "2D":
            gif_path = self._generate_gif(
                source, out_dir, stem, job.frame_range, cfg
            )
            if gif_path:
                self.preview_ready.emit(element_id, gif_path, "gif")

            # ---- Low-res video preview --------------------------------
            if cfg.get("generate_video_previews", True):
                vid_path = self._generate_video(
                    source, out_dir, stem, job.frame_range, cfg
                )
                if vid_path:
                    self.preview_ready.emit(element_id, vid_path, "video")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _generate_thumbnail(source, out_dir, stem, cfg):
        """Return path to written thumbnail PNG, or None on failure."""
        try:
            from PIL import Image
            thumb_path = os.path.join(out_dir, stem + "_thumb.png")
            max_size   = cfg.get("thumbnail_size", 256)

            img = Image.open(source)
            img.thumbnail((max_size, max_size), Image.LANCZOS)

            # Normalise 16/32-bit EXR/HDR to 8-bit before saving PNG
            if img.mode in ("F", "I", "RGBA"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img.save(thumb_path, "PNG", optimize=True)
            return thumb_path

        except Exception as exc:
            log.warning("Thumbnail failed for %s: %s", source, exc)
            return None

    @staticmethod
    def _generate_gif(source, out_dir, stem, frame_range, cfg):
        """Generate a short animated GIF preview from a sequence."""
        try:
            import glob
            import re
            from PIL import Image

            gif_path   = os.path.join(out_dir, stem + "_preview.gif")
            max_frames = cfg.get("gif_max_frames", 24)
            fps        = cfg.get("gif_fps", 12)
            max_size   = cfg.get("gif_size", 240)

            # Detect sequence pattern from source path
            dir_name   = os.path.dirname(source)
            base_name  = os.path.basename(source)
            # Replace trailing digits (frame number) with glob wildcard
            pattern    = re.sub(r'\d+(?=\.[^.]+$)', '*', base_name)
            frames_raw = sorted(glob.glob(os.path.join(dir_name, pattern)))

            if not frames_raw:
                frames_raw = [source]

            # Sample evenly across available frames
            step   = max(1, len(frames_raw) // max_frames)
            frames_raw = frames_raw[::step][:max_frames]

            pil_frames = []
            for fp in frames_raw:
                try:
                    img = Image.open(fp).convert("RGBA")
                    img.thumbnail((max_size, max_size), Image.LANCZOS)
                    pil_frames.append(img)
                except Exception:
                    continue

            if not pil_frames:
                return None

            duration_ms = int(1000 / max(1, fps))
            pil_frames[0].save(
                gif_path,
                save_all=True,
                append_images=pil_frames[1:],
                loop=0,
                duration=duration_ms,
                optimize=True,
            )
            return gif_path

        except Exception as exc:
            log.warning("GIF generation failed for %s: %s", source, exc)
            return None

    @staticmethod
    def _generate_video(source, out_dir, stem, frame_range, cfg):
        """Generate low-res MP4 via FFmpeg subprocess."""
        try:
            import subprocess
            import shutil

            ffmpeg = shutil.which("ffmpeg") or cfg.get("ffmpeg_path", "ffmpeg")
            vid_path = os.path.join(out_dir, stem + "_preview.mp4")

            # Build input pattern
            dir_name  = os.path.dirname(source)
            base_name = os.path.basename(source)
            import re
            pattern = re.sub(r'\d+(?=\.[^.]+$)', '%04d', base_name)
            inp = os.path.join(dir_name, pattern)

            start_frame = 1
            if frame_range:
                parts = str(frame_range).split("-")
                if len(parts) == 2:
                    try:
                        start_frame = int(parts[0])
                    except ValueError:
                        pass

            cmd = [
                ffmpeg, "-y",
                "-start_number", str(start_frame),
                "-i", inp,
                "-vf", "scale=480:-2",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-frames:v", "72",
                vid_path,
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            if result.returncode == 0 and os.path.exists(vid_path):
                return vid_path
        except Exception as exc:
            log.debug("Video preview failed for %s: %s", source, exc)
        return None


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
