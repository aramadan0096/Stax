# -*- coding: utf-8 -*-
"""The standalone app ships a curated PySide2/Qt in the repo's ``lib/`` (matching
Qt DLLs, plugins, QtWebEngine). dependency_bootstrap.bootstrap() prepends
``lib/`` to sys.path so the FIRST ``import PySide2`` resolves to that bundled
copy. Anything that imports PySide2 *before* bootstrap runs silently binds the
app to a different Qt (e.g. a pip-installed one in a virtualenv), whose Qt
runtime can crash the standalone launch during Qt init -- a silent native exit
(code 120) with no Python traceback.

Regression: main.py's NumPy-notice shim imported PySide2 at module top, before
bootstrap, switching the app from lib/PySide2 to .venv/site-packages/PySide2.
main must not import PySide2 until after bootstrap has put lib/ on the path.
"""

import os
import subprocess
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LIB_PYSIDE2 = os.path.join(_REPO, "lib", "PySide2")


@pytest.mark.gui
@pytest.mark.skipif(not os.path.isdir(_LIB_PYSIDE2),
                    reason="no bundled lib/PySide2 in this checkout")
def test_import_main_resolves_pyside2_from_bundled_lib():
    script = (
        "import os, sys\n"
        "sys.path.insert(0, os.getcwd())\n"
        "import main\n"
        "import PySide2\n"
        "sys.stdout.write(os.path.normcase(os.path.abspath(PySide2.__file__)))\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("STAX_BOOTSTRAP_DONE", None)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO, env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, "import main failed:\n" + proc.stderr[-2000:]
    loaded = proc.stdout.strip()
    bundled = os.path.normcase(_LIB_PYSIDE2)
    assert loaded.startswith(bundled), (
        "standalone must load the bundled Qt, not a site-packages copy.\n"
        "loaded: {}\nexpected under: {}".format(loaded, bundled))
