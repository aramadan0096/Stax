# -*- coding: utf-8 -*-
"""App-launch smoke: the 570 unit/gui tests mock Nuke and construct widgets, but
none proves the app actually comes up as a user sees it. These check that the
MainWindow displays a real titled window, and that the app boots through its true
import path in a fresh interpreter (stronger than test_entrypoints_importable,
which only imports the module).
"""

import os
import subprocess
import sys

import pytest
from PySide2 import QtWidgets

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.gui
def test_mainwindow_shows_a_titled_window(qtbot, stax_config, mock_nuke, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from main import MainWindow

    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)
    win.show()
    for _ in range(5):
        QtWidgets.QApplication.processEvents()

    assert win.isVisible()              # the window actually came up
    assert win.windowTitle()            # ...with a title
    assert win.centralWidget() is not None   # ...and its 3-pane body


_LAUNCH_SCRIPT = """
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = {root}
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(root, "src"))
os.environ["STOCK_DB"] = {db}
from PySide2 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from config import Config
from main import MainWindow
win = MainWindow(config=Config(config_path={cfg}))
win.show()
for _ in range(5):
    app.processEvents()
ok = bool(win.isVisible() and win.windowTitle())
sys.stdout.write("LAUNCH_OK" if ok else "LAUNCH_FAIL")
sys.stdout.flush()
os._exit(0)   # skip the PySide2/Windows native shutdown crash after we've verified
"""


@pytest.mark.gui
def test_app_launches_in_a_fresh_process(tmp_path):
    script = _LAUNCH_SCRIPT.format(
        root=repr(_REPO_ROOT),
        db=repr(str(tmp_path / "app.db")),
        cfg=repr(str(tmp_path / "config.json")),
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("STAX_BOOTSTRAP_DONE", None)   # a real cold launch
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert "LAUNCH_OK" in proc.stdout, (
        "app did not launch:\nSTDOUT:\n{}\nSTDERR:\n{}".format(
            proc.stdout[-2000:], proc.stderr[-3000:]))
