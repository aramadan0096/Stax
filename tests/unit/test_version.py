import os
import re

import pytest

import version  # flat import: src/ is on sys.path (conftest)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PYPROJECT = os.path.join(_REPO_ROOT, "pyproject.toml")


@pytest.mark.unit
def test_version_is_semver_and_consistent():
    assert re.match(r"^\d+\.\d+\.\d+$", version.__version__), version.__version__
    assert version.get_version() == version.__version__


@pytest.mark.unit
def test_pyproject_version_is_single_sourced():
    text = open(_PYPROJECT, encoding="utf-8").read()
    # Version must be derived from src/version.py, not hardcoded.
    assert 'dynamic = ["version"]' in text
    # No literal  version = "x.y.z"  under [project]  (hatch uses  path = ...  instead).
    assert re.search(r'^\s*version\s*=\s*["\']', text, re.MULTILINE) is None
