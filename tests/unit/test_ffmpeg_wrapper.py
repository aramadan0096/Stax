# -*- coding: utf-8 -*-
"""Unit tests for src/ffmpeg_wrapper.py (SP3 hardening).

All tests mock subprocess; no real ffmpeg is required except the one test
marked @pytest.mark.ffmpeg, which skips when binaries are absent.
"""

import os
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
