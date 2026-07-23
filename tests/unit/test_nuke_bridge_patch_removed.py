import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.unit
def test_nuke_bridge_patch_is_deleted():
    """L3: the orphaned apply-by-hand skeleton must not exist. It referenced
    nonexistent NukeBridge.paste_toolset and documented an uncalled analytics
    hook."""
    stale = os.path.join(_REPO_ROOT, "src", "nuke_bridge_patch.py")
    assert not os.path.exists(stale), "src/nuke_bridge_patch.py should be deleted"
