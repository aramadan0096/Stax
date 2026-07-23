import pytest


@pytest.mark.nuke
def test_get_stax_panel_returns_a_singleton(mock_nuke, monkeypatch):
    """H5: menu commands must operate on one live StaXPanel, not spawn a new
    one each call. get_stax_panel() caches a module-level singleton."""
    import nuke_launcher

    created = []

    class _FakePanel(object):
        def __init__(self):
            created.append(self)

    # Substitute a lightweight stub so no real Config/DB/UI is constructed.
    monkeypatch.setattr(nuke_launcher, "StaXPanel", _FakePanel)
    # Ensure a clean slate regardless of test ordering.
    monkeypatch.setattr(nuke_launcher, "_STAX_PANEL_INSTANCE", None, raising=False)

    first = nuke_launcher.get_stax_panel()
    second = nuke_launcher.get_stax_panel()

    assert first is second                 # same live widget
    assert len(created) == 1               # constructed exactly once (no duplicate panel)


@pytest.mark.nuke
def test_get_stax_panel_is_exposed(mock_nuke):
    """The accessor menu.py depends on must exist."""
    import nuke_launcher

    assert hasattr(nuke_launcher, "get_stax_panel")
    assert callable(nuke_launcher.get_stax_panel)
