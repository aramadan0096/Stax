# SP3 — FFmpeg / Media Hardening & Cross-Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow superpowers:test-driven-development: write the failing test first, watch it fail, then implement.

**Goal:** Harden `src/ffmpeg_wrapper.py` so StaX media processing runs on **Windows and Linux** (H4), never hangs on a bad file (M9), never races on the GIF palette (M8), and never deadlocks or flashes a console during playback (M10) — all covered by unit tests that mock `subprocess` and require no real ffmpeg in CI.

**Architecture:** All production changes are in the single self-contained module `src/ffmpeg_wrapper.py`; no other source file is touched. Binary names are selected by `sys.platform` (read at call time so tests can monkeypatch it) with a `shutil.which` fallback. Every `subprocess.check_output` gains a `timeout=` and a `TimeoutExpired` handler. Two-pass GIF generation uses a per-call `mkdtemp` cleaned in `finally`. Background `ffplay` uses `DEVNULL` and, on Windows, `CREATE_NO_WINDOW`. Tests live in `tests/unit/test_ffmpeg_wrapper.py` and mock `subprocess` via `pytest-mock`.

**Tech Stack:** Python 3.9, `subprocess`, `shutil`, `tempfile`, `logging` (stdlib only — no new dependency); pytest, pytest-mock; the SP0 harness (`pytest -m "not manual"`, offscreen Qt not needed for this unit-tier module).

## Global Constraints

- **Platforms:** Windows + Linux only (no macOS). Binary-name logic keys on `sys.platform.startswith('win')`.
- **Scope lock:** edit **only** `src/ffmpeg_wrapper.py` and create `tests/unit/test_ffmpeg_wrapper.py`. Do **not** edit `IMPLEMENTATION_PROGRESS.md`, `nuke_bridge.py`, `tools/ffmpeg_downloader.py`, `tools/run_standalone.ps1`, or any other file.
- **No new dependencies.** stdlib only.
- **Preserve public signatures.** Existing callers (`ingestion_core.py`, `video_player_widget.py`, `preview_worker.py`) must keep working; only internal kwargs and exception branches change.
- **New code uses `logging`, not `print`.** The new `TimeoutExpired` and playback-error handlers log via the module `logger`. A full `print`→`logging` sweep of untouched branches is out of scope (issue L4 / SP8) — leave existing `print` calls as they are.
- **No real ffmpeg in the gated suite.** Mock `subprocess`. Any real-binary test is `@pytest.mark.ffmpeg` and skips when absent.
- **Import convention:** flat — `from ffmpeg_wrapper import FFmpegWrapper, _binary_name`.
- **Commits:** conventional prefixes (`test:`, `fix:`, `feat:`), frequent, one per task. Do **not** commit unless the human asks — this plan's `git commit` steps describe the intended granularity; the executor commits per its session policy.

---

## Key signatures (verified against the codebase)

- `FFmpegWrapper(ffmpeg_bin_path=None)` — defaults `ffmpeg_bin_path` to `<project_root>/bin/ffmpeg/bin`; currently hard-codes `ffmpeg.exe`/`ffprobe.exe`/`ffplay.exe` and raises `RuntimeError` if any is missing (`src/ffmpeg_wrapper.py:22-45`).
- `get_ffmpeg()` — module singleton returning `FFmpegWrapper()` (`:543-548`).
- `get_media_info(filepath)` → dict or `None`; `check_output` at `:67` (`PROBE`).
- `generate_thumbnail(input_path, output_path, max_size=512, frame_time=None, threads=4)` → bool; `check_output` at `:158`.
- `generate_sequence_thumbnail(sequence_pattern, output_path, max_size=512, frame_number=None, threads=4)` → bool; `:201`.
- `generate_video_preview(input_path, output_path, max_size=512, duration=10, threads=4)` → bool; `:239`.
- `play_media(filepath, loop=False, start_time=0)` → `Popen` or `None`; PIPE Popen at `:275-279`.
- `extract_frame(input_path, frame_number, output_path)` → bool; `:307`.
- `get_frame_count(filepath)` → int or `None`; bare-`except` `check_output` at `:337-340` (`PROBE`).
- `generate_gif_preview(input_path, output_path, max_duration=None, size=256, fps=10, threads=4, start_frame=None, is_sequence=False, sequence_fps=24, max_frames=None, loop_forever=True)` → bool; shared palette at `:365`; palette `check_output` `:399`, gif `check_output` `:436`; cleanups `:438-440, 446-447, 451-452`.
- `convert_sequence_to_video(sequence_pattern, output_path, fps=24, start_frame=1)` → bool; `:482`.
- `generate_sequence_video_preview(sequence_pattern, output_path, max_size=512, fps=24, start_frame=1, max_frames=None)` → bool; `:530`.
- Downloader binary-name convention (reference): `exe = name + (".exe" if platform.system() == "Windows" else "")` (`tools/ffmpeg_downloader.py:80`).

---

## Task 1: Cross-platform binary resolution (H4)

**Files:**
- Modify: `src/ffmpeg_wrapper.py` (imports; add `_binary_name`, `FFmpegWrapper._resolve_binary`; rewrite `__init__` name/verify block `:35-45`).
- Create: `tests/unit/test_ffmpeg_wrapper.py`.

**Interfaces:**
- Produces: `_binary_name(stem)` and `FFmpegWrapper._resolve_binary(bin_dir, stem)` used by `__init__`; a `wrapper`-building fixture reused by Tasks 2–5.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing name/resolution tests**

Create `tests/unit/test_ffmpeg_wrapper.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -v`
Expected: ImportError/failures — `_binary_name` and `FFmpegWrapper._resolve_binary` do not exist yet, and `test_constructs_on_linux_with_bare_binaries` fails because `__init__` still hard-codes `.exe`.

- [ ] **Step 3: Add imports + module logger**

In `src/ffmpeg_wrapper.py`, change the import block (`:9-13`) from:

```python
import os
import sys
import subprocess
import json
import tempfile
```

to:

```python
import os
import sys
import subprocess
import json
import tempfile
import shutil
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Add the `_binary_name` module helper**

Insert immediately after the import block (before `class FFmpegWrapper`):

```python
def _binary_name(stem):
    """Return the platform-correct executable filename for an ffmpeg tool stem.

    Appends '.exe' only on Windows (sys.platform starts with 'win'); POSIX
    platforms use the bare stem, matching tools/ffmpeg_downloader.py's install
    convention. Reads sys.platform at call time so tests can monkeypatch it.
    """
    return stem + '.exe' if sys.platform.startswith('win') else stem
```

- [ ] **Step 5: Add the `_resolve_binary` static method and rewrite `__init__`**

In `FFmpegWrapper.__init__`, replace the name assignment + verification block (`:35-45`):

```python
        self.ffmpeg_path = os.path.join(ffmpeg_bin_path, 'ffmpeg.exe')
        self.ffprobe_path = os.path.join(ffmpeg_bin_path, 'ffprobe.exe')
        self.ffplay_path = os.path.join(ffmpeg_bin_path, 'ffplay.exe')
        
        # Verify binaries exist
        if not os.path.exists(self.ffmpeg_path):
            raise RuntimeError("FFmpeg not found at: {}".format(self.ffmpeg_path))
        if not os.path.exists(self.ffprobe_path):
            raise RuntimeError("FFprobe not found at: {}".format(self.ffprobe_path))
        if not os.path.exists(self.ffplay_path):
            raise RuntimeError("FFplay not found at: {}".format(self.ffplay_path))
```

with:

```python
        self.ffmpeg_path = self._resolve_binary(ffmpeg_bin_path, 'ffmpeg')
        self.ffprobe_path = self._resolve_binary(ffmpeg_bin_path, 'ffprobe')
        self.ffplay_path = self._resolve_binary(ffmpeg_bin_path, 'ffplay')

        # Verify binaries resolved (bundled dir or PATH)
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg not found in {} or on PATH".format(ffmpeg_bin_path))
        if not self.ffprobe_path:
            raise RuntimeError("FFprobe not found in {} or on PATH".format(ffmpeg_bin_path))
        if not self.ffplay_path:
            raise RuntimeError("FFplay not found in {} or on PATH".format(ffmpeg_bin_path))

    @staticmethod
    def _resolve_binary(bin_dir, stem):
        """Locate an ffmpeg tool: prefer the bundled bin dir, then PATH via
        shutil.which. Returns an absolute path string, or None if not found."""
        name = _binary_name(stem)
        bundled = os.path.join(bin_dir, name)
        if os.path.exists(bundled):
            return bundled
        on_path = shutil.which(name)
        if on_path:
            return on_path
        return None
```

Note: the `@staticmethod` is placed right after `__init__` ends (before `get_media_info`). Keep the existing 4-space class indentation.

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -v`
Expected: all Task-1 tests PASS (8 passed). If `test_constructs_on_linux_with_bare_binaries` still fails, confirm `_binary_name` reads `sys.platform` (not a cached value) and that `__init__` calls `_resolve_binary`, not the old hard-coded paths.

- [ ] **Step 7: Commit**

```bash
git add src/ffmpeg_wrapper.py tests/unit/test_ffmpeg_wrapper.py
git commit -m "fix(ffmpeg): select binary names by platform + shutil.which fallback (H4)"
```

---

## Task 2: Subprocess timeouts (M9)

**Files:**
- Modify: `src/ffmpeg_wrapper.py` (add `PROBE_TIMEOUT`/`ENCODE_TIMEOUT`; add `timeout=` + `TimeoutExpired` handler to all 10 `check_output` sites).
- Modify: `tests/unit/test_ffmpeg_wrapper.py` (add timeout tests).

**Interfaces:**
- Consumes: the `wrapper` fixture from Task 1.
- Produces: every probe/encode call carries `timeout=` and degrades to its failure sentinel on timeout.

- [ ] **Step 1: Write the failing timeout tests**

Append to `tests/unit/test_ffmpeg_wrapper.py`:

```python
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
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -k timeout -v`
Expected: FAIL — no `PROBE_TIMEOUT`/`ENCODE_TIMEOUT` attribute and no `timeout=` kwarg yet.

- [ ] **Step 3: Add the timeout class constants**

In `src/ffmpeg_wrapper.py`, add two attributes at the top of the class body, immediately after the class docstring (before `def __init__`):

```python
    PROBE_TIMEOUT = 60      # ffprobe metadata / packet-count calls
    ENCODE_TIMEOUT = 600    # thumbnail / gif / video encode calls
```

- [ ] **Step 4: Add `timeout=` + `TimeoutExpired` to `get_media_info` (`:67`)**

Change the `try` at `:66-67` from:

```python
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
```

to:

```python
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                             timeout=self.PROBE_TIMEOUT)
```

and insert a new except branch before `except subprocess.CalledProcessError as e:` (`:115`):

```python
        except subprocess.TimeoutExpired:
            logger.error("FFprobe timed out after %ss: %s", self.PROBE_TIMEOUT, filepath)
            return None
```

- [ ] **Step 5: Add `timeout=` + `TimeoutExpired` to `generate_thumbnail` (`:158`)**

Change `:157-158`:

```python
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
```

to:

```python
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                    timeout=self.ENCODE_TIMEOUT)
```

and insert before `except subprocess.CalledProcessError as e:` (`:160`):

```python
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg thumbnail timed out after %ss: %s",
                         self.ENCODE_TIMEOUT, input_path)
            return False
```

- [ ] **Step 6: Repeat the encode pattern for the remaining encode methods**

Apply the identical two-part change (add `timeout=self.ENCODE_TIMEOUT` to the `check_output` call; insert a `TimeoutExpired` branch returning `False`) to each method below. Use the log message shown:

- `generate_sequence_thumbnail` — call `:201`, insert before `:203`:
  ```python
  except subprocess.TimeoutExpired:
      logger.error("FFmpeg sequence thumbnail timed out after %ss: %s",
                   self.ENCODE_TIMEOUT, sequence_pattern)
      return False
  ```
- `generate_video_preview` — call `:239`, insert before `:241`:
  ```python
  except subprocess.TimeoutExpired:
      logger.error("FFmpeg video preview timed out after %ss: %s",
                   self.ENCODE_TIMEOUT, input_path)
      return False
  ```
- `extract_frame` — call `:307`, insert before `:309`:
  ```python
  except subprocess.TimeoutExpired:
      logger.error("FFmpeg frame extraction timed out after %ss: %s",
                   self.ENCODE_TIMEOUT, input_path)
      return False
  ```
- `convert_sequence_to_video` — call `:482`, insert before `:484`:
  ```python
  except subprocess.TimeoutExpired:
      logger.error("FFmpeg sequence conversion timed out after %ss: %s",
                   self.ENCODE_TIMEOUT, sequence_pattern)
      return False
  ```
- `generate_sequence_video_preview` — call `:530`, insert before `:532`:
  ```python
  except subprocess.TimeoutExpired:
      logger.error("FFmpeg sequence video preview timed out after %ss: %s",
                   self.ENCODE_TIMEOUT, sequence_pattern)
      return False
  ```

- [ ] **Step 7: Add `timeout=` + `TimeoutExpired` to `get_frame_count` (`:337`)**

Change `:336-340`:

```python
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return int(output.decode('utf-8').strip())
        except:
            return None
```

to:

```python
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                             timeout=self.PROBE_TIMEOUT)
            return int(output.decode('utf-8').strip())
        except subprocess.TimeoutExpired:
            logger.error("FFprobe frame count timed out after %ss: %s",
                         self.PROBE_TIMEOUT, filepath)
            return None
        except Exception:
            return None
```

- [ ] **Step 8: Add `timeout=` to the two `generate_gif_preview` calls**

(The `TimeoutExpired` handler for GIF is added in Task 3, which restructures that method's try/except.)

- palette pass `:399`:
  ```python
  subprocess.check_output(palette_cmd, stderr=subprocess.STDOUT)
  ```
  →
  ```python
  subprocess.check_output(palette_cmd, stderr=subprocess.STDOUT,
                          timeout=self.ENCODE_TIMEOUT)
  ```
- gif pass `:436`:
  ```python
  subprocess.check_output(gif_cmd, stderr=subprocess.STDOUT)
  ```
  →
  ```python
  subprocess.check_output(gif_cmd, stderr=subprocess.STDOUT,
                          timeout=self.ENCODE_TIMEOUT)
  ```

- [ ] **Step 9: Run the timeout tests**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -k timeout -v`
Expected: all timeout tests PASS. Then run the whole file: `pytest tests/unit/test_ffmpeg_wrapper.py -v` — all Task 1 + Task 2 tests green.

- [ ] **Step 10: Commit**

```bash
git add src/ffmpeg_wrapper.py tests/unit/test_ffmpeg_wrapper.py
git commit -m "fix(ffmpeg): add subprocess timeouts + TimeoutExpired handling (M9)"
```

---

## Task 3: Per-call GIF palette temp dir (M8)

**Files:**
- Modify: `src/ffmpeg_wrapper.py` (`generate_gif_preview` `:365, 438-453`).
- Modify: `tests/unit/test_ffmpeg_wrapper.py` (add GIF race tests).

**Interfaces:**
- Consumes: the `wrapper` fixture.
- Produces: each GIF call uses a unique, self-cleaning palette path.

- [ ] **Step 1: Write the failing GIF tests**

Append to `tests/unit/test_ffmpeg_wrapper.py`:

```python
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
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -k gif -v`
Expected: FAIL — the palette path is currently the shared `gettempdir()/palette.png`, so `test_gif_uses_unique_palette_per_call` fails (both calls share the path) and `test_gif_cleans_up_temp_dir` fails (dir is `gettempdir()`, still present).

- [ ] **Step 3: Switch to a per-call temp dir**

In `generate_gif_preview`, replace the palette-path line (`:365`):

```python
        # Generate palette first for better quality GIF
        palette_path = os.path.join(tempfile.gettempdir(), 'palette.png')
```

with:

```python
        # Generate palette in a per-call temp dir so concurrent jobs never
        # collide on a shared palette.png (issue M8).
        temp_dir = tempfile.mkdtemp(prefix='stax_gif_')
        palette_path = os.path.join(temp_dir, 'palette.png')
```

- [ ] **Step 4: Replace the scattered cleanups with a single `finally` + a `TimeoutExpired` branch**

Replace the whole trailing exception ladder — from the cleanup after the gif pass through the end of the method (`:437-453`):

```python
            subprocess.check_output(gif_cmd, stderr=subprocess.STDOUT,
                                    timeout=self.ENCODE_TIMEOUT)
            
            # Cleanup palette
            if os.path.exists(palette_path):
                os.remove(palette_path)
            
            return os.path.exists(output_path)
            
        except subprocess.CalledProcessError as e:
            print("FFmpeg GIF generation error: {}".format(str(e)))
            if os.path.exists(palette_path):
                os.remove(palette_path)
            return False
        except Exception as e:
            print("Error generating GIF preview: {}".format(str(e)))
            if os.path.exists(palette_path):
                os.remove(palette_path)
            return False
```

with:

```python
            subprocess.check_output(gif_cmd, stderr=subprocess.STDOUT,
                                    timeout=self.ENCODE_TIMEOUT)

            return os.path.exists(output_path)

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg GIF generation timed out after %ss: %s",
                         self.ENCODE_TIMEOUT, input_path)
            return False
        except subprocess.CalledProcessError as e:
            print("FFmpeg GIF generation error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error generating GIF preview: {}".format(str(e)))
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
```

Note: Step 8 of Task 2 already added `timeout=self.ENCODE_TIMEOUT` to both GIF `check_output` calls; the `gif_cmd` call above is shown with it. If Task 2 Step 8 has not been applied, apply it now.

- [ ] **Step 5: Run the GIF tests**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -k gif -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ffmpeg_wrapper.py tests/unit/test_ffmpeg_wrapper.py
git commit -m "fix(ffmpeg): per-call GIF palette temp dir cleaned in finally (M8)"
```

---

## Task 4: ffplay DEVNULL + no-window (M10)

**Files:**
- Modify: `src/ffmpeg_wrapper.py` (`play_media` `:273-283`).
- Modify: `tests/unit/test_ffmpeg_wrapper.py` (add playback tests).

**Interfaces:**
- Consumes: the `wrapper` fixture.
- Produces: `play_media` no longer deadlocks on unread PIPEs and hides the console on Windows.

- [ ] **Step 1: Write the failing playback tests**

Append to `tests/unit/test_ffmpeg_wrapper.py`:

```python
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
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -k play_media -v`
Expected: FAIL — `play_media` currently passes `stdout=subprocess.PIPE, stderr=subprocess.PIPE`.

- [ ] **Step 3: Rewrite the `play_media` Popen block**

Replace `:273-283`:

```python
        try:
            # Start in background, return process handle
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return process
        except Exception as e:
            print("Error playing media: {}".format(str(e)))
            return None
```

with:

```python
        # Discard output so ffplay never blocks on an unread buffer (M10);
        # hide the console window on Windows.
        popen_kwargs = {
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
        }
        if sys.platform.startswith('win'):
            popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

        try:
            process = subprocess.Popen(cmd, **popen_kwargs)
            return process
        except Exception as e:
            logger.error("Error playing media %s: %s", filepath, e)
            return None
```

- [ ] **Step 4: Run the playback tests**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -k play_media -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ffmpeg_wrapper.py tests/unit/test_ffmpeg_wrapper.py
git commit -m "fix(ffmpeg): DEVNULL ffplay streams + CREATE_NO_WINDOW on Windows (M10)"
```

---

## Task 5: Real-binary smoke test + full-suite verification

**Files:**
- Modify: `tests/unit/test_ffmpeg_wrapper.py` (add one `@pytest.mark.ffmpeg` test).

**Interfaces:**
- Consumes: a real `ffprobe` on PATH when present; skips otherwise.
- Produces: end-to-end confidence that the argv wiring is correct against a genuine binary.

- [ ] **Step 1: Add the real-binary test (skips when ffmpeg is absent)**

Append to `tests/unit/test_ffmpeg_wrapper.py`:

```python
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
```

Add the required import at the top of the test file if not already present: `import shutil`.

- [ ] **Step 2: Run the real test locally (informational)**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -m ffmpeg -v`
Expected: PASS if ffmpeg is installed, otherwise SKIPPED. Either outcome is acceptable — CI runners without ffmpeg simply skip it.

- [ ] **Step 3: Run the full module suite**

Run: `pytest tests/unit/test_ffmpeg_wrapper.py -v`
Expected: all `unit` tests pass; the `ffmpeg` test passes or skips. 0 failed, 0 errored.

- [ ] **Step 4: Run the whole gated suite to confirm no regressions**

Run: `pytest -m "not manual"`
Expected: the new `tests/unit/test_ffmpeg_wrapper.py` tests join the SP0 suite; total is green (existing xfails still xfail; 0 unexpected failures).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_ffmpeg_wrapper.py
git commit -m "test(ffmpeg): optional real-binary smoke test marked ffmpeg (skips when absent)"
```

---

## Self-Review

**1. Spec coverage:**
- H4 cross-platform binary names + `shutil.which` fallback → Task 1 ✓
- M9 timeouts on all 10 `check_output` sites + `TimeoutExpired` handling → Task 2 (+ GIF handler in Task 3) ✓
- M8 per-call GIF palette temp dir cleaned in `finally` → Task 3 ✓
- M10 ffplay `DEVNULL` + `CREATE_NO_WINDOW` on Windows → Task 4 ✓
- Mocked-subprocess unit tests asserting argv / platform name / `timeout=` / `DEVNULL`; real-binary test marked `@pytest.mark.ffmpeg` → Tasks 1–5 ✓
- Fake platform via `monkeypatch` on `sys.platform` → Task 1 Steps 1, 6 ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every code step shows complete before/after text and the exact command + expected output. Fallback guidance (Task 1 Step 6) names the exact thing to check, not a vague "fix it".

**3. Type consistency:** `_binary_name(stem) -> str`; `FFmpegWrapper._resolve_binary(bin_dir, stem) -> str | None`; `PROBE_TIMEOUT`/`ENCODE_TIMEOUT` are ints passed as `timeout=`. Failure sentinels are preserved exactly: `get_media_info`/`get_frame_count` return `None`; all generators return `False`; `play_media` returns a `Popen` or `None`. Test call sites use the verified signatures from the Key-signatures section (e.g. `generate_thumbnail(input, output, frame_time=0.0)`, `extract_frame(input, frame_number, output)`).

**4. Line-reference sanity:** All `:NN` references match the current `src/ffmpeg_wrapper.py` (549 lines): imports `:9-13`, `__init__` names `:35-45`, the 10 `check_output` calls `:67,158,201,239,307,337,399,436,482,530`, `play_media` PIPE `:275-279`, GIF palette `:365`, GIF cleanups `:438-453`.

---

## Notes for the executor
- **Do not touch any file but `src/ffmpeg_wrapper.py` and `tests/unit/test_ffmpeg_wrapper.py`.** In particular, never edit `IMPLEMENTATION_PROGRESS.md` (a separate tracking step owns it).
- **Never weaken a test to make it pass.** If the real code disagrees with a test, fix the code — these are new tests describing the intended hardened behavior, not characterization of legacy quirks.
- If Task 2 and Task 3 are done out of order, note that the two GIF `check_output` calls get their `timeout=` in Task 2 Step 8 and their `TimeoutExpired`/`finally` cleanup in Task 3 Step 4 — apply both regardless of order.
- Run `pytest tests/unit/test_ffmpeg_wrapper.py -v` before each commit; run `pytest -m "not manual"` before the final commit.
