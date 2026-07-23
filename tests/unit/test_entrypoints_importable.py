"""Guard: every entry point must import in a *fresh* interpreter.

The in-process test suite cannot catch this. `src/ui/__init__.py` eagerly
imports `src.ui.drag_gallery_view`, which imports the flat `ui` package —
whichever of `ui` / `src.ui` is loaded first decides whether that resolves or
raises a circular-import ImportError. Once any earlier test has imported `ui`
flatly, every later `src.ui` import in the same process succeeds, so a broken
entry point stays invisible until a user actually runs the app.
"""

import os
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _import_in_subprocess(module_name):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    # A real launch is a cold process: dependency_bootstrap must actually run and
    # put src/ on sys.path. Any earlier in-process test that called bootstrap()
    # leaves this flag in os.environ, which the child would otherwise inherit.
    env.pop("STAX_BOOTSTRAP_DONE", None)
    return subprocess.run(
        [sys.executable, "-c", "import {}".format(module_name)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.unit
@pytest.mark.parametrize("module_name", ["main", "nuke_launcher"])
def test_entry_point_imports_in_a_fresh_interpreter(module_name):
    proc = _import_in_subprocess(module_name)
    assert proc.returncode == 0, "`import {}` failed:\n{}".format(
        module_name, proc.stderr[-3000:]
    )
