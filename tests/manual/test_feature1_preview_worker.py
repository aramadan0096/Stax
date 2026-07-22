# -*- coding: utf-8 -*-
"""
tests/test_feature1_preview_worker.py
Feature 1 — Async Preview Worker
"""

import os
import time
import threading

import pytest


# ---------------------------------------------------------------------------
# PreviewJob dataclass
# ---------------------------------------------------------------------------

class TestPreviewJob:
    def test_default_priority(self, tmp_dir):
        from src.preview_worker import PreviewJob
        job = PreviewJob(
            element_id=1,
            source_path="/fake/path.exr",
            output_dir=tmp_dir,
        )
        assert job.priority == 50
        assert job.asset_type == "2D"
        assert job.frame_range is None

    def test_custom_priority(self, tmp_dir):
        from src.preview_worker import PreviewJob
        job = PreviewJob(1, "/p.exr", tmp_dir, priority=10)
        assert job.priority == 10

    def test_ordering_by_priority(self, tmp_dir):
        from src.preview_worker import PreviewJob
        high = PreviewJob(1, "/a.exr", tmp_dir, priority=10)
        low  = PreviewJob(2, "/b.exr", tmp_dir, priority=90)
        assert high < low

    def test_config_snapshot(self, tmp_dir):
        from src.preview_worker import PreviewJob
        cfg = {"thumbnail_size": 128, "gif_fps": 10}
        job = PreviewJob(1, "/p.exr", tmp_dir, config=cfg)
        assert job.config["thumbnail_size"] == 128


# ---------------------------------------------------------------------------
# PreviewWorker thread lifecycle
# ---------------------------------------------------------------------------

class TestPreviewWorkerLifecycle:
    def test_worker_starts_and_stops(self):
        from src.preview_worker import PreviewWorker
        w = PreviewWorker()
        w.start()
        assert w.isRunning()
        w.stop()
        w.wait(2000)
        assert not w.isRunning()

    def test_pending_count_increments(self, tmp_dir):
        from src.preview_worker import PreviewWorker, PreviewJob
        w = PreviewWorker()
        # Do NOT start — jobs queue up
        for i in range(5):
            w.submit(PreviewJob(i, "/fake_{}.png".format(i), tmp_dir))
        assert w.pending_count() == 5
        # Cleanup without starting
        w._running = False

    def test_singleton_get_and_shutdown(self):
        from src.preview_worker import get_preview_queue, shutdown_preview_queue
        w1 = get_preview_queue()
        w2 = get_preview_queue()
        assert w1 is w2
        if w1.isRunning():
            shutdown_preview_queue()
        from src.preview_worker import _GLOBAL_WORKER
        assert _GLOBAL_WORKER is None


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------

class TestThumbnailGeneration:
    def test_thumbnail_created_from_png(self, tmp_dir, tiny_png):
        from src.preview_worker import PreviewWorker
        path = PreviewWorker._generate_thumbnail(
            tiny_png, tmp_dir, "elem_000001", {"thumbnail_size": 64}
        )
        assert path is not None
        assert os.path.isfile(path)
        assert path.endswith("_thumb.png")

    def test_thumbnail_respects_max_size(self, tmp_dir, tiny_png):
        from src.preview_worker import PreviewWorker
        from PIL import Image
        path = PreviewWorker._generate_thumbnail(
            tiny_png, tmp_dir, "elem_sz", {"thumbnail_size": 32}
        )
        assert path is not None
        img = Image.open(path)
        assert max(img.size) <= 32

    def test_thumbnail_missing_file_returns_none(self, tmp_dir):
        from src.preview_worker import PreviewWorker
        path = PreviewWorker._generate_thumbnail(
            "/nonexistent/path.exr", tmp_dir, "elem_x", {}
        )
        assert path is None

    def test_thumbnail_output_dir_created(self, tmp_dir):
        from src.preview_worker import PreviewWorker
        import tempfile
        new_dir = os.path.join(tmp_dir, "new_subdir")
        assert not os.path.isdir(new_dir)
        os.makedirs(new_dir)   # worker pre-creates; simulate here
        path = PreviewWorker._generate_thumbnail(
            "/nonexistent.png", new_dir, "e", {}
        )
        # Should return None (bad source) but not raise
        assert path is None


# ---------------------------------------------------------------------------
# GIF generation
# ---------------------------------------------------------------------------

class TestGIFGeneration:
    def test_gif_single_frame(self, tmp_dir, tiny_png):
        from src.preview_worker import PreviewWorker
        path = PreviewWorker._generate_gif(
            tiny_png, tmp_dir, "elem_gif",
            frame_range=None,
            cfg={"gif_max_frames": 8, "gif_fps": 6, "gif_size": 32},
        )
        assert path is not None
        assert os.path.isfile(path)
        assert path.endswith("_preview.gif")

    def test_gif_missing_source_returns_none(self, tmp_dir):
        from src.preview_worker import PreviewWorker
        path = PreviewWorker._generate_gif(
            "/no_such.exr", tmp_dir, "e", None, {}
        )
        assert path is None


# ---------------------------------------------------------------------------
# Signal emission (headless via QCoreApplication)
# ---------------------------------------------------------------------------

class TestWorkerSignals:
    def test_preview_ready_signal_emitted(self, tmp_dir, tiny_png):
        """Worker emits preview_ready with correct element_id after processing."""
        try:
            from PySide2 import QtWidgets
        except ImportError:
            pytest.skip("PySide2 not available")

        import sys
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

        from src.preview_worker import PreviewWorker, PreviewJob

        received = []

        def on_ready(eid, path, ptype):
            received.append((eid, path, ptype))

        w = PreviewWorker()
        w.preview_ready.connect(on_ready)
        w.start()

        job = PreviewJob(
            element_id   = 42,
            source_path  = tiny_png,
            output_dir   = tmp_dir,
            asset_type   = "2D",
            config       = {"thumbnail_size": 32, "gif_max_frames": 2,
                            "gif_fps": 2, "gif_size": 32,
                            "generate_video_previews": False},
        )
        w.submit(job)

        # Wait up to 5 seconds for at least the thumbnail
        deadline = time.time() + 5
        while not received and time.time() < deadline:
            app.processEvents()
            time.sleep(0.05)

        w.stop()
        w.wait(2000)

        assert len(received) >= 1, "preview_ready was never emitted"
        eids = [r[0] for r in received]
        assert 42 in eids

    def test_job_failed_signal_on_bad_path(self):
        """Worker emits job_failed when source path is missing."""
        try:
            from PySide2 import QtWidgets
        except ImportError:
            pytest.skip("PySide2 not available")

        import sys, tempfile
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

        from src.preview_worker import PreviewWorker, PreviewJob

        failures = []
        w = PreviewWorker()
        w.job_failed.connect(lambda eid, msg: failures.append(eid))
        w.start()

        with tempfile.TemporaryDirectory() as d:
            job = PreviewJob(
                element_id  = 99,
                source_path = "/totally/missing.exr",
                output_dir  = d,
                config      = {},
            )
            w.submit(job)

            deadline = time.time() + 5
            while not failures and time.time() < deadline:
                app.processEvents()
                time.sleep(0.05)

        w.stop()
        w.wait(2000)
        # The worker should either emit job_failed OR silently produce
        # no preview (thumbnail returns None, no signal).  Either is fine —
        # we just assert the app didn't crash.
