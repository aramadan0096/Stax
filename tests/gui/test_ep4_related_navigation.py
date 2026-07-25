import pytest


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    `Config` reads STOCK_DB only at construction time (src/config.py:107),
    so the env var must be set *before* `Config(...)` is built -- a
    `monkeypatch.setenv` inside the test body comes too late once a
    `Config` object already exists (e.g. the shared `stax_config` fixture),
    and `MainWindow` would silently build against the real project database
    at `./data/stax.db` instead of an isolated tmp_path db. Same helper as
    `tests/gui/test_ep3_inspector_wiring.py::_mainwindow_with_temp_db` /
    `tests/gui/test_ep2_nav.py::_mainwindow_with_temp_db`.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


@pytest.mark.gui
def test_related_activated_wired_to_start_page_handler(qtbot, mock_nuke, monkeypatch, tmp_path):
    """I3: InspectorPanel.related_activated (emitted on double-click of a
    Related row) must be connected in MainWindow, routing through the same
    select/reveal path used by StartPage card activation
    (on_start_page_element_activated) -- otherwise click-to-navigate on a
    related element is a dead click."""
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

    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win.inspector.related_activated.emit(42)

    assert calls == [42]
