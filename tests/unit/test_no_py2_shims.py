import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Banned in first-party .py files. The app is Python-3 only.
_BANNED = ("Python 2.7", "unicode = str", "urllib2")

# Vendored / generated / doc / test trees are not first-party source.
# `build`/`dist` are frozen build outputs (cx_Freeze/PyInstaller) that bundle
# vendored libs and a pre-build snapshot of src/ — generated, not maintained here.
_SKIP_DIRS = {".git", "lib", "dependencies", "docs", "tests", "examples", "bin",
              "__pycache__", ".venv", "venv", "build", "dist"}


def _is_skipped(name):
    """Third-party / generated trees are never first-party source.

    Covers sibling virtualenvs (`.venv-dev`, `.venvPy3`, ...) and any vendored
    `site-packages` tree, which legitimately still ship Py2 compat shims.
    """
    return name in _SKIP_DIRS or name.startswith(".venv") or name == "site-packages"


def _iter_source_files():
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):
        dirnames[:] = [d for d in dirnames if not _is_skipped(d)]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


@pytest.mark.unit
def test_no_python2_claims_or_shims_remain():
    """L7: no 'Python 2.7' claims and no dead Py2 shims in first-party source."""
    offenders = []
    for path in _iter_source_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        for token in _BANNED:
            if token in text:
                offenders.append("{}: {!r}".format(os.path.relpath(path, _REPO_ROOT), token))
    assert not offenders, "Python-2 shims/claims remain:\n" + "\n".join(offenders)
