import os
import re

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel):
    with open(os.path.join(_REPO_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.unit
def test_pyinstaller_definitions_are_deleted():
    assert not os.path.exists(os.path.join(_REPO_ROOT, "StaX.spec"))
    assert not os.path.exists(os.path.join(_REPO_ROOT, "tools", "build_installer.py"))


@pytest.mark.unit
def test_setup_freeze_has_no_absolute_drive_paths():
    text = _read("setup_freeze.py")
    # e.g. D:/... or C:\...  — none may survive; all paths derive from __file__.
    assert re.search(r"[A-Za-z]:[\\/]", text) is None


@pytest.mark.unit
def test_setup_freeze_uses_ico_icon():
    text = _read("setup_freeze.py")
    assert "logo.ico" in text
    assert "logo.png" not in text  # icon must not point at a PNG


@pytest.mark.unit
def test_pyproject_declares_cxfreeze_not_pyinstaller():
    text = _read("pyproject.toml")
    assert "pyinstaller" not in text.lower()
    assert "cx-freeze" in text.lower()
