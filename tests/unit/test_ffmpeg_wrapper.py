# -*- coding: utf-8 -*-
"""Unit tests for src/ffmpeg_wrapper.py (SP3 hardening).

All tests mock subprocess; no real ffmpeg is required except the one test
marked @pytest.mark.ffmpeg, which skips when binaries are absent.
"""

import os
import shutil
import sys
import subprocess

import pytest

from ffmpeg_wrapper import FFmpegWrapper, _binary_name


def _make_fake_bindir(tmp_path):
    """Create a bin dir with dummy ffmpeg/ffprobe/ffplay named for THIS OS."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for stem in ("ffmpeg", "ffprobe", "ffplay"):
        (bin_dir / _binary_name(stem)).write_text("dummy")
    return str(bin_dir)


@pytest.fixture
def wrapper(tmp_path):
    """A FFmpegWrapper built against dummy binaries (no real ffmpeg needed)."""
    return FFmpegWrapper(ffmpeg_bin_path=_make_fake_bindir(tmp_path))


# --- H4: platform-correct binary names -------------------------------------

@pytest.mark.unit
def test_binary_name_appends_exe_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert _binary_name("ffmpeg") == "ffmpeg.exe"
    assert _binary_name("ffprobe") == "ffprobe.exe"


@pytest.mark.unit
def test_binary_name_is_bare_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert _binary_name("ffmpeg") == "ffmpeg"
    assert _binary_name("ffplay") == "ffplay"


@pytest.mark.unit
def test_resolve_prefers_bundled(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    p = bin_dir / _binary_name("ffmpeg")
    p.write_text("x")
    assert FFmpegWrapper._resolve_binary(str(bin_dir), "ffmpeg") == str(p)


@pytest.mark.unit
def test_resolve_falls_back_to_which(tmp_path, mocker):
    mocker.patch("ffmpeg_wrapper.shutil.which", return_value="/usr/bin/ffmpeg")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert FFmpegWrapper._resolve_binary(str(empty), "ffmpeg") == "/usr/bin/ffmpeg"


@pytest.mark.unit
def test_resolve_returns_none_when_missing(tmp_path, mocker):
    mocker.patch("ffmpeg_wrapper.shutil.which", return_value=None)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert FFmpegWrapper._resolve_binary(str(empty), "ffmpeg") is None


@pytest.mark.unit
def test_constructs_on_linux_with_bare_binaries(tmp_path, monkeypatch):
    """The headline H4 fix: on Linux, bare-named binaries must NOT raise."""
    monkeypatch.setattr(sys, "platform", "linux")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for stem in ("ffmpeg", "ffprobe", "ffplay"):
        (bin_dir / stem).write_text("x")  # bare names, no .exe
    w = FFmpegWrapper(ffmpeg_bin_path=str(bin_dir))
    assert w.ffmpeg_path.endswith("ffmpeg")
    assert not w.ffmpeg_path.endswith(".exe")


@pytest.mark.unit
def test_constructs_on_windows_with_exe_binaries(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for stem in ("ffmpeg", "ffprobe", "ffplay"):
        (bin_dir / (stem + ".exe")).write_text("x")
    w = FFmpegWrapper(ffmpeg_bin_path=str(bin_dir))
    assert w.ffmpeg_path.endswith("ffmpeg.exe")


@pytest.mark.unit
def test_missing_binaries_raise_runtimeerror(tmp_path, mocker):
    mocker.patch("ffmpeg_wrapper.shutil.which", return_value=None)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError):
        FFmpegWrapper(ffmpeg_bin_path=str(empty))


# --- M9: subprocess timeouts ------------------------------------------------

@pytest.mark.unit
def test_get_media_info_passes_timeout(wrapper, mocker):
    m = mocker.patch("ffmpeg_wrapper.subprocess.check_output",
                     return_value=b'{"format": {}, "streams": []}')
    wrapper.get_media_info("/tmp/clip.mp4")
    args, kwargs = m.call_args
    assert args[0][0] == wrapper.ffprobe_path
    assert kwargs.get("timeout") == wrapper.PROBE_TIMEOUT


@pytest.mark.unit
def test_get_media_info_handles_timeout(wrapper, mocker):
    mocker.patch("ffmpeg_wrapper.subprocess.check_output",
                 side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=1))
    assert wrapper.get_media_info("/tmp/clip.mp4") is None


@pytest.mark.unit
def test_get_frame_count_handles_timeout(wrapper, mocker):
    mocker.patch("ffmpeg_wrapper.subprocess.check_output",
                 side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=1))
    assert wrapper.get_frame_count("/tmp/clip.mp4") is None


@pytest.mark.unit
@pytest.mark.parametrize("method,posargs", [
    ("generate_thumbnail", ("/in.mp4", "/out.png")),
    ("generate_sequence_thumbnail", ("/in.%04d.exr", "/out.png")),
    ("generate_video_preview", ("/in.mp4", "/out.mp4")),
    ("extract_frame", ("/in.mp4", 5, "/out.png")),
    ("convert_sequence_to_video", ("/in.%04d.exr", "/out.mp4")),
    ("generate_sequence_video_preview", ("/in.%04d.exr", "/out.mp4")),
])
def test_encode_methods_pass_timeout(wrapper, mocker, method, posargs):
    m = mocker.patch("ffmpeg_wrapper.subprocess.check_output", return_value=b"")
    # generate_thumbnail calls get_media_info first when frame_time is None;
    # pass frame_time to avoid a second probe muddying call_args.
    if method == "generate_thumbnail":
        getattr(wrapper, method)(*posargs, frame_time=0.0)
    else:
        getattr(wrapper, method)(*posargs)
    _, kwargs = m.call_args  # last check_output call
    assert kwargs.get("timeout") == wrapper.ENCODE_TIMEOUT


@pytest.mark.unit
def test_encode_method_returns_false_on_timeout(wrapper, mocker):
    mocker.patch("ffmpeg_wrapper.subprocess.check_output",
                 side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1))
    assert wrapper.generate_video_preview("/in.mp4", "/out.mp4") is False


# --- M8: per-call GIF palette temp dir --------------------------------------

@pytest.mark.unit
def test_gif_uses_unique_palette_per_call(wrapper, tmp_path, mocker):
    import tempfile
    captured = []

    def fake(cmd, **kw):
        captured.append(list(cmd))
        return b""

    mocker.patch("ffmpeg_wrapper.subprocess.check_output", side_effect=fake)

    wrapper.generate_gif_preview("/in.mp4", str(tmp_path / "a.gif"))
    wrapper.generate_gif_preview("/in.mp4", str(tmp_path / "b.gif"))

    palette_paths = [c[-1] for c in captured
                     if os.path.basename(c[-1]) == "palette.png"]
    assert len(palette_paths) == 2                    # one palette pass per call
    assert len(set(palette_paths)) == 2               # both unique
    shared = os.path.join(tempfile.gettempdir(), "palette.png")
    assert shared not in palette_paths                # not the old shared path


@pytest.mark.unit
def test_gif_cleans_up_temp_dir(wrapper, tmp_path, mocker):
    captured = []

    def fake(cmd, **kw):
        captured.append(list(cmd))
        return b""

    mocker.patch("ffmpeg_wrapper.subprocess.check_output", side_effect=fake)
    wrapper.generate_gif_preview("/in.mp4", str(tmp_path / "a.gif"))

    palette_path = next(c[-1] for c in captured
                        if os.path.basename(c[-1]) == "palette.png")
    # finally: shutil.rmtree removed the per-call temp dir
    assert not os.path.exists(os.path.dirname(palette_path))


@pytest.mark.unit
def test_gif_returns_false_on_timeout(wrapper, tmp_path, mocker):
    mocker.patch("ffmpeg_wrapper.subprocess.check_output",
                 side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1))
    assert wrapper.generate_gif_preview("/in.mp4", str(tmp_path / "a.gif")) is False


# --- M10: ffplay DEVNULL + no-window ----------------------------------------

@pytest.mark.unit
def test_play_media_uses_devnull(wrapper, mocker):
    popen = mocker.patch("ffmpeg_wrapper.subprocess.Popen")
    wrapper.play_media("/tmp/clip.mp4")
    args, kwargs = popen.call_args
    assert args[0][0] == wrapper.ffplay_path
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


@pytest.mark.unit
def test_play_media_no_pipe(wrapper, mocker):
    popen = mocker.patch("ffmpeg_wrapper.subprocess.Popen")
    wrapper.play_media("/tmp/clip.mp4")
    _, kwargs = popen.call_args
    assert kwargs["stdout"] is not subprocess.PIPE
    assert kwargs["stderr"] is not subprocess.PIPE


@pytest.mark.unit
def test_play_media_creationflags_match_platform(wrapper, mocker):
    """CREATE_NO_WINDOW only on Windows; default (unset -> 0) elsewhere.

    Asserts against the real sys.platform so the Windows-only constant is
    never referenced on Linux.
    """
    popen = mocker.patch("ffmpeg_wrapper.subprocess.Popen")
    wrapper.play_media("/tmp/clip.mp4")
    _, kwargs = popen.call_args
    if sys.platform.startswith("win"):
        assert kwargs.get("creationflags", 0) == subprocess.CREATE_NO_WINDOW
    else:
        assert kwargs.get("creationflags", 0) == 0


# --- Optional real-binary smoke (skipped when ffmpeg is not installed) ------

@pytest.mark.ffmpeg
@pytest.mark.skipif(shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
                    reason="ffmpeg/ffprobe not on PATH")
def test_real_get_media_info_reads_generated_clip(tmp_path):
    import shutil as _sh  # local alias to build wrapper against PATH binaries
    # Build a wrapper that resolves ffmpeg/ffprobe/ffplay from PATH.
    bin_dir = tmp_path / "empty_bin"
    bin_dir.mkdir()
    w = FFmpegWrapper(ffmpeg_bin_path=str(bin_dir))  # falls back to shutil.which

    # Generate a 1s test clip with the real ffmpeg.
    clip = str(tmp_path / "test.mp4")
    subprocess.check_call([
        w.ffmpeg_path, "-y", "-f", "lavfi",
        "-i", "testsrc=duration=1:size=64x64:rate=10",
        "-pix_fmt", "yuv420p", clip,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)

    info = w.get_media_info(clip)
    assert info is not None
    assert info["width"] == 64
    assert info["height"] == 64
