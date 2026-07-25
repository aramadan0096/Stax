# -*- coding: utf-8 -*-
"""PySide2's shiboken2 binding (built against NumPy 1.x) prints a C-level
"A module that was compiled using NumPy 1.x" notice straight to stderr on import
when NumPy 2 is installed. It is not a Python warning (warnings filters can't
touch it) and is unavoidable (no NumPy version satisfies both PySide2 and the
NumPy-2-built opencv). It's non-fatal noise; main.py silences it at the fd level
around the first Qt import.
"""

import os
import subprocess
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.gui
def test_numpy_abi_notice_not_printed_on_import():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("STAX_BOOTSTRAP_DONE", None)
    proc = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=_REPO, env=env, capture_output=True, text=True, timeout=300,
    )
    assert "compiled using NumPy 1.x" not in proc.stderr, (
        "NumPy ABI notice leaked to stderr:\n" + proc.stderr[-1500:])
