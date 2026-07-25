import pytest


@pytest.mark.gui
def test_related_activated_wired_to_start_page_handler(qtbot, stax_config, mock_nuke, monkeypatch, tmp_path):
    """I3: InspectorPanel.related_activated (emitted on double-click of a
    Related row) must be connected in MainWindow, routing through the same
    select/reveal path used by StartPage card activation
    (on_start_page_element_activated) -- otherwise click-to-navigate on a
    related element is a dead click."""
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from main import MainWindow

    calls = []
    # Patch the CLASS method before construction: the signal connection is
    # made during __init__ with `self.on_start_page_element_activated`,
    # which is resolved (and bound) at attribute-access time -- patching
    # the class here means the bound method captured by connect() is the
    # replacement, unlike patching the instance attribute after the fact.
    monkeypatch.setattr(
        MainWindow, "on_start_page_element_activated",
        lambda self, element_id: calls.append(element_id))

    win = MainWindow(config=stax_config)
    qtbot.addWidget(win)

    win.inspector.related_activated.emit(42)

    assert calls == [42]
