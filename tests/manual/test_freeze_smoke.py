"""Real cx_Freeze build smoke test. Slow; excluded from the default gate.

Run explicitly:
    pytest tests/manual/test_freeze_smoke.py -m slow --override-ini="testpaths=tests/manual"
"""

import os
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.slow
def test_cx_freeze_build_produces_executables(tmp_path):
    pytest.importorskip("cx_Freeze")
    env = dict(os.environ, STAX_BUILD_OUT=str(tmp_path / "StaX-build"))
    proc = subprocess.run(
        [sys.executable, "setup_freeze.py", "build_exe"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = tmp_path / "StaX-build"
    names = {p.name.lower() for p in out.iterdir()}
    exe = ".exe" if sys.platform.startswith("win") else ""
    assert ("stax" + exe) in names
    assert ("stax_nuke_launcher" + exe) in names
