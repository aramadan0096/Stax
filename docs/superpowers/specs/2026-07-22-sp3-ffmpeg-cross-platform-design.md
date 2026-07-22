# SP3 — FFmpeg / Media Hardening & Cross-Platform — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). This is the fourth sub-project. It depends only on the SP0 test harness; it is code-independent of SP1 (DB) and SP2 (async pipeline) because `src/ffmpeg_wrapper.py` is a self-contained module, so SP3 may proceed in parallel with SP1/SP2 once SP0 has landed.

---

## 1. Background & Motivation

The StaX audit (`STAX_AUDIT_REPORT.md`) flagged the ffmpeg media layer (`src/ffmpeg_wrapper.py`) as the single biggest cross-platform blocker plus three latent reliability bugs. All four issues live in this one module:

- **H4 — Media processing is Windows-only.** `FFmpegWrapper.__init__` hard-codes the binary names `ffmpeg.exe` / `ffprobe.exe` / `ffplay.exe` (`src/ffmpeg_wrapper.py:35-37`) and then verifies their existence (`:40-45`), raising `RuntimeError` on any platform where the binaries lack a `.exe` suffix. On Linux `get_ffmpeg()` therefore raises on first use, so **every** preview, probe, GIF, and playback path is dead — even though `pyproject.toml` sets `requires-python >=3.9`, `tools/ffmpeg_downloader.py` installs bare-named POSIX binaries (`exe = name + (".exe" if platform.system() == "Windows" else "")`, `tools/ffmpeg_downloader.py:80`), and `tools/run_standalone.ps1` already probes for a Unix `ffmpeg` name (`tools/run_standalone.ps1:94`). This is the headline cross-platform fix; the target is **Windows + Linux**.

- **M8 — GIF palette temp-file race.** Two-pass GIF generation writes its palette to a fixed shared path `os.path.join(tempfile.gettempdir(), 'palette.png')` (`src/ffmpeg_wrapper.py:365`). Concurrent GIF jobs (which SP2's async preview worker will produce) clobber each other's palette, and the three scattered `os.remove(palette_path)` cleanups race.

- **M9 — No subprocess timeouts.** None of the ~10 `subprocess.check_output` calls pass `timeout=` (`:67, 158, 201, 239, 307, 337, 399, 436, 482, 530`). A hung or pathological decode blocks the calling thread forever; some of these run on the GUI thread today (`get_media_info` from selection changes), so one bad file freezes the app.

- **M10 — ffplay PIPE deadlock.** `play_media` starts a background `subprocess.Popen` with `stdout=subprocess.PIPE, stderr=subprocess.PIPE` (`:275-279`) that nothing ever drains; ffplay blocks once its ~64 KB stderr buffer fills. On Windows it also flashes a console window.

SP3 hardens this module in place. Per the locked program decisions, the half-wired features are wired up, not deleted, so `FFmpegWrapper` must keep working for the existing sync callers and for SP2's future off-thread callers.

### Program context (decisions already locked)
- **Target platforms:** Windows + Linux (no macOS). The binary-name logic must be correct on both.
- **Testing:** hybrid 3-tier; SP3's tests are almost entirely **unit** tier (mock `subprocess`, no real ffmpeg, no Qt, no Nuke).
- **Imports** are flat (`from ffmpeg_wrapper import ...`); new code uses `logging`, not `print`.

---

## 2. Goals / Non-Goals

### Goals
- `FFmpegWrapper` constructs and runs on **both Windows and Linux**, selecting binary names by platform and falling back to `shutil.which` when the bundled binaries are absent (H4).
- Every `subprocess.check_output` call carries an explicit `timeout=`, and every method handles `subprocess.TimeoutExpired` with a logged failure instead of hanging (M9).
- Two-pass GIF generation uses a **per-call** temp directory, removed in a `finally` block, so concurrent jobs never collide (M8).
- Background `ffplay` playback uses `DEVNULL` for both streams and, on Windows, `CREATE_NO_WINDOW` (M10).
- A unit test suite (`tests/unit/test_ffmpeg_wrapper.py`) that mocks `subprocess` to assert the constructed `argv`, the platform-correct binary name, the presence of `timeout=`, unique GIF palette paths, and `DEVNULL` usage — **without requiring real ffmpeg in CI**. Any test that shells out to a real binary is marked `@pytest.mark.ffmpeg` and skips when absent.

### Non-Goals (explicitly deferred)
- macOS support (`Darwin` binary handling) — out of program scope, though `shutil.which` will incidentally work there.
- Replacing PIL/ffmpeg thumbnail decode with **OpenImageIO** for EXR/DPX (issue M12) — that is SP2's concern.
- A full `print` → `logging` sweep of the module (issue L4) — deferred to SP8. SP3 uses `logging` only in the **new** code it adds (the `TimeoutExpired` handlers); pre-existing `print` calls in untouched branches are left in place to keep the change surgical.
- Draining ffplay output on a reader thread — `DEVNULL` is sufficient and simpler; a drain-thread is noted only as a rejected alternative.
- Changing any other module (no edits to `nuke_bridge.py`, `ffmpeg_downloader.py`, `run_standalone.ps1`, or `IMPLEMENTATION_PROGRESS.md`).

---

## 3. Approach

Chosen approach: **surgical in-place hardening of `src/ffmpeg_wrapper.py`, TDD-first, one audit issue per task.** Each fix is small, independently testable by mocking `subprocess`, and preserves the existing public method signatures so current callers (`ingestion_core.py`, `video_player_widget.py`, `preview_worker.py`) keep working unchanged.

Key design decisions:

1. **Binary resolution is a pure, testable unit.** A module-level `_binary_name(stem)` maps a tool stem (`"ffmpeg"`) to its platform filename by reading `sys.platform` at call time (so a `monkeypatch.setattr(sys, "platform", "linux")` flips it). A static `FFmpegWrapper._resolve_binary(bin_dir, stem)` prefers the bundled binary, then falls back to `shutil.which`, then returns `None`. `__init__` raises only when a required binary resolves to `None`. Reading `sys.platform` at call time is what makes the platform behavior unit-testable without a second OS.

2. **Timeouts are class constants, passed directly.** Two class attributes — `PROBE_TIMEOUT` (ffprobe metadata/probe calls) and `ENCODE_TIMEOUT` (thumbnail/GIF/video encodes) — are passed as `timeout=` to each `check_output`. No public signatures change. A new `except subprocess.TimeoutExpired` branch precedes the existing `except CalledProcessError` in each method and logs the timeout. (Timeouts were already swallowed by each method's trailing `except Exception`; the explicit branch exists for a clear, logged diagnostic rather than a silent generic catch.)

3. **GIF palette uses `tempfile.mkdtemp` + `finally`.** A per-call directory (`stax_gif_*`) holds `palette.png`; a single `shutil.rmtree(temp_dir, ignore_errors=True)` in `finally` replaces the three scattered `os.remove` cleanups. A directory (not `NamedTemporaryFile`) is used so ffmpeg's `-y` overwrite has an unheld path — avoiding the Windows "file in use by an open handle" problem `NamedTemporaryFile` would introduce.

4. **ffplay uses `DEVNULL` + conditional `creationflags`.** `stdout`/`stderr` become `subprocess.DEVNULL`; on Windows only, `creationflags=CREATE_NO_WINDOW` is added via `getattr(subprocess, 'CREATE_NO_WINDOW', 0)` so the reference is safe to evaluate on Linux (where the constant does not exist).

Rejected alternatives:
- *Rewrite the module around a single `_run()` dispatcher* — larger blast radius; every call site changes shape, complicating review and risking the stable sync callers. In-place edits are lower risk.
- *Add per-call `timeout` parameters to all 8 public methods* — signature churn for little gain; class constants (overridable at class/instance level) are simpler and equally testable.
- *Drain ffplay PIPEs on a reader thread* — more code and a thread to join; `DEVNULL` discards output StaX never consumes.

---

## 4. Detailed Design

All changes are in `src/ffmpeg_wrapper.py`. Tests are new: `tests/unit/test_ffmpeg_wrapper.py`.

### 4.1 Module scaffolding

Add to the import block (`src/ffmpeg_wrapper.py:9-13`):

```python
import shutil
import logging

logger = logging.getLogger(__name__)
```

### 4.2 H4 — cross-platform binary resolution

New module-level helper and a static resolver:

```python
def _binary_name(stem):
    """Return the platform-correct executable filename for an ffmpeg tool stem.

    Appends '.exe' only on Windows (sys.platform starts with 'win'); POSIX
    platforms use the bare stem, matching tools/ffmpeg_downloader.py's install
    convention. Reads sys.platform at call time so tests can monkeypatch it.
    """
    return stem + '.exe' if sys.platform.startswith('win') else stem
```

`_resolve_binary` becomes a `@staticmethod` on `FFmpegWrapper`:

```python
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

`__init__` (`:35-45`) is rewritten to resolve each tool and raise only on a genuine miss:

```python
self.ffmpeg_path = self._resolve_binary(ffmpeg_bin_path, 'ffmpeg')
self.ffprobe_path = self._resolve_binary(ffmpeg_bin_path, 'ffprobe')
self.ffplay_path = self._resolve_binary(ffmpeg_bin_path, 'ffplay')

if not self.ffmpeg_path:
    raise RuntimeError(
        "FFmpeg not found in {} or on PATH".format(ffmpeg_bin_path))
if not self.ffprobe_path:
    raise RuntimeError(
        "FFprobe not found in {} or on PATH".format(ffmpeg_bin_path))
if not self.ffplay_path:
    raise RuntimeError(
        "FFplay not found in {} or on PATH".format(ffmpeg_bin_path))
```

Result: on Linux with bundled bare-named binaries (or a system ffmpeg on PATH), construction succeeds instead of raising — unblocking all downstream media paths.

### 4.3 M9 — subprocess timeouts

Two class attributes on `FFmpegWrapper`:

```python
PROBE_TIMEOUT = 60      # ffprobe metadata / packet-count calls
ENCODE_TIMEOUT = 600    # thumbnail / gif / video encode calls
```

Each of the 10 `subprocess.check_output` sites gains `timeout=<constant>`:

| Method | Line | Timeout |
|---|---|---|
| `get_media_info` | 67 | `PROBE_TIMEOUT` |
| `generate_thumbnail` | 158 | `ENCODE_TIMEOUT` |
| `generate_sequence_thumbnail` | 201 | `ENCODE_TIMEOUT` |
| `generate_video_preview` | 239 | `ENCODE_TIMEOUT` |
| `extract_frame` | 307 | `ENCODE_TIMEOUT` |
| `get_frame_count` | 337 | `PROBE_TIMEOUT` |
| `generate_gif_preview` (palette) | 399 | `ENCODE_TIMEOUT` |
| `generate_gif_preview` (gif) | 436 | `ENCODE_TIMEOUT` |
| `convert_sequence_to_video` | 482 | `ENCODE_TIMEOUT` |
| `generate_sequence_video_preview` | 530 | `ENCODE_TIMEOUT` |

Each method gains an explicit `except subprocess.TimeoutExpired` branch (before its `CalledProcessError`/`Exception` branches) that logs via `logger.error(...)` and returns the method's failure sentinel (`None` for `get_media_info`/`get_frame_count`, `False` for the generators). `get_frame_count`'s bare `except:` (`:339`) is widened to catch `TimeoutExpired` explicitly (log + `return None`) while keeping a fallback bare return.

### 4.4 M8 — per-call GIF palette temp dir

In `generate_gif_preview`, the shared `palette_path` (`:365`) is replaced by:

```python
temp_dir = tempfile.mkdtemp(prefix='stax_gif_')
palette_path = os.path.join(temp_dir, 'palette.png')
```

The body's `try` keeps both ffmpeg passes; the three scattered `os.remove(palette_path)` cleanups (`:438-440, 446-447, 451-452`) are removed and replaced by one `finally`:

```python
finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
```

A `TimeoutExpired` branch is added alongside the existing `CalledProcessError`/`Exception` branches (all now cleanup-free, since `finally` owns cleanup).

### 4.5 M10 — ffplay DEVNULL + no-window

`play_media` (`:273-280`) replaces the PIPE Popen with:

```python
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

`CREATE_NO_WINDOW` is accessed via `getattr` so the code imports and runs on Linux (where the attribute is absent); on Linux the key is simply never added.

---

## 5. Testing Strategy

All SP3 tests are **unit** tier (`tests/unit/test_ffmpeg_wrapper.py`), mocking `subprocess` via `pytest-mock` (`mocker`). No real ffmpeg is required for the gated suite.

**Fixtures / techniques:**
- A local `wrapper` fixture builds a fake bin dir containing dummy files named via `_binary_name(stem)` for the current OS, then constructs `FFmpegWrapper(ffmpeg_bin_path=<dir>)` — so `__init__`'s existence check passes cross-platform without real binaries.
- `monkeypatch.setattr(sys, "platform", "linux"|"win32")` provides a fake platform for the H4 name-selection tests.
- `mocker.patch("ffmpeg_wrapper.subprocess.check_output")` / `.Popen` capture `call_args` to assert `argv[0]` is the resolved tool path, that `timeout` is in `kwargs`, and (for playback) that `stdout`/`stderr` are `subprocess.DEVNULL`.

**Assertions per issue:**
- **H4:** `_binary_name` returns `ffmpeg.exe` under `win32` and `ffmpeg` under `linux`; `_resolve_binary` prefers bundled, falls back to `shutil.which`, returns `None` when absent; a wrapper built against bare-named binaries under a monkeypatched `linux` platform constructs without raising and its `ffmpeg_path` does **not** end in `.exe`.
- **M9:** every probe/encode method passes a non-`None` `timeout=`; a `TimeoutExpired` side-effect yields the method's failure sentinel (not a raised exception).
- **M8:** two consecutive `generate_gif_preview` calls use **distinct** palette paths, each basename `palette.png`, neither equal to the old shared `gettempdir()/palette.png`, and each temp dir is gone after the call returns.
- **M10:** `play_media` calls `Popen` with `stdout`/`stderr` == `DEVNULL`; `creationflags` equals `CREATE_NO_WINDOW` on Windows and is unset (default `0`) on Linux — asserted against the real `sys.platform` so the Windows-only constant is never referenced on Linux.

**Real-binary test:** one optional test marked `@pytest.mark.ffmpeg`, skipped via `shutil.which('ffprobe') is None`, runs a genuine `get_media_info` against a generated file to prove the wiring end-to-end when binaries exist. The `ffmpeg` marker is already registered in `pytest.ini` (SP0, Task 4), so no config change is needed.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `monkeypatch.setattr(sys, "platform", ...)` doesn't affect logic that cached the platform at import | `_binary_name` reads `sys.platform` at call time, never caching — verified by the linux/windows name tests. |
| Referencing `subprocess.CREATE_NO_WINDOW` on Linux raises `AttributeError` | Access via `getattr(subprocess, 'CREATE_NO_WINDOW', 0)`; the M10 test asserts against the real `sys.platform`, never conjuring the constant on Linux. |
| Windows temp-dir cleanup fails if a handle lingers | `shutil.rmtree(temp_dir, ignore_errors=True)` never raises; a directory (not `NamedTemporaryFile`) avoids holding an open handle over the palette path. |
| Timeout constants too aggressive for large 4K/EXR encodes | `ENCODE_TIMEOUT = 600s` (10 min) is generous for previews; constants are class attributes, overridable per deployment without touching call sites. |
| Silent behavior change for existing sync callers | Public signatures and return sentinels are unchanged; only internal kwargs and exception branches are added. Characterization is via the new unit tests. |

---

## 7. Deliverables Checklist
- [ ] `src/ffmpeg_wrapper.py`: `shutil`/`logging` imports + module `logger`.
- [ ] H4: `_binary_name` + `FFmpegWrapper._resolve_binary`; `__init__` resolves per platform and falls back to `shutil.which`.
- [ ] M9: `PROBE_TIMEOUT`/`ENCODE_TIMEOUT` constants; `timeout=` on all 10 `check_output` calls; `TimeoutExpired` handlers.
- [ ] M8: per-call `mkdtemp` palette dir with `finally: shutil.rmtree`.
- [ ] M10: `play_media` uses `DEVNULL` + conditional `CREATE_NO_WINDOW`.
- [ ] `tests/unit/test_ffmpeg_wrapper.py`: mocked-subprocess unit tests for all four issues + one `@pytest.mark.ffmpeg` real-binary test.
- [ ] `pytest -m "not manual"` green on Windows + Linux CI.

---

## 8. Follow-on
SP2 (async pipeline) consumes a hardened `FFmpegWrapper`: its off-thread preview worker benefits directly from the M9 timeouts (a hung decode no longer wedges the worker) and the M8 per-call palette (concurrent GIF jobs no longer collide). SP2's OpenImageIO adoption (M12) for EXR/DPX thumbnail decode is a separate change layered on top of this module and is out of SP3 scope.
