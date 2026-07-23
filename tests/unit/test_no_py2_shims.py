import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Banned in first-party .py files. The app is Python-3 only.
_BANNED = ("Python 2.7", "unicode = str", "urllib2")

# Vendored / generated / doc / test trees are not first-party source.
_SKIP_DIRS = {".git", "lib", "dependencies", "docs", "tests", "examples", "bin",
              "__pycache__", ".venv", "venv"}


def _iter_source_files():
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
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
