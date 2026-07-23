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
