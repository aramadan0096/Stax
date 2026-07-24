# -*- coding: utf-8 -*-
"""EP2 Task 9: saved searches + smart collections surfaced in the nav panel.

`StacksListsPanel` gains a "Saved Searches" list (personal, scoped by the
current user) and a "Smart Collections" list (team-shared), both driven by
the EP2 cluster 2B DB methods. Selecting an item emits `filter_selected`
with the item's stored `FilterSpec`, which `main.py` routes to
`MediaDisplayWidget.apply_filter`. A "Save search..." button on
`MediaDisplayWidget`'s toolbar captures the widget's active filter as a new
saved search.
"""

import pytest
from PySide2 import QtWidgets

from nuke_bridge import NukeBridge


class _FakeMain(object):
    """Minimal main-window stand-in exposing what StacksListsPanel/
    MediaDisplayWidget actually read: `current_user` and
    `check_admin_permission`. Matches the real MainWindow shape, not the
    brief's placeholder."""

    def __init__(self, username="alice", admin=True):
        self.current_user = {"username": username, "role": "admin" if admin else "user"}

    def check_admin_permission(self, action_name="this action"):
        return True


# ---------------------------------------------------------------------------
# StacksListsPanel: Saved Searches (personal) + Smart Collections (shared)
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_selecting_saved_search_emits_filter(qtbot, stax_db, stax_config):
    stax_db.create_saved_search("Fire", {"tags_any": ["fire"]}, "alice")
    from ui.stacks_lists_panel import StacksListsPanel

    panel = StacksListsPanel(stax_db, stax_config, main_window=_FakeMain(username="alice"))
    qtbot.addWidget(panel)
    panel.refresh_saved_searches()

    with qtbot.waitSignal(panel.filter_selected, timeout=1000) as blocker:
        panel.saved_searches_list.setCurrentRow(0)
        panel._on_saved_search_activated(panel.saved_searches_list.item(0))

    assert blocker.args == [{"tags_any": ["fire"]}]


@pytest.mark.gui
def test_selecting_smart_collection_emits_filter(qtbot, stax_db, stax_config):
    stax_db.create_smart_collection("Recent 3D", {"types": ["3D"]}, created_by="alice")
    from ui.stacks_lists_panel import StacksListsPanel

    panel = StacksListsPanel(stax_db, stax_config, main_window=_FakeMain(username="alice"))
    qtbot.addWidget(panel)
    panel.refresh_smart_collections()

    with qtbot.waitSignal(panel.filter_selected, timeout=1000) as blocker:
        panel.smart_collections_list.setCurrentRow(0)
        panel._on_smart_collection_activated(panel.smart_collections_list.item(0))

    assert blocker.args == [{"types": ["3D"]}]


@pytest.mark.gui
def test_saved_searches_scoped_to_current_user(qtbot, stax_db, stax_config):
    stax_db.create_saved_search("Alice's", {"text": "a"}, "alice")
    stax_db.create_saved_search("Bob's", {"text": "b"}, "bob")
    from ui.stacks_lists_panel import StacksListsPanel

    panel = StacksListsPanel(stax_db, stax_config, main_window=_FakeMain(username="alice"))
    qtbot.addWidget(panel)

    names = [panel.saved_searches_list.item(i).text() for i in range(panel.saved_searches_list.count())]
    assert names == ["Alice's"]


@pytest.mark.gui
def test_nav_lists_populate_on_construction(qtbot, stax_db, stax_config):
    """Both lists must be populated as a side effect of construction --
    no explicit refresh call required -- so the nav shows saved state
    immediately on panel creation (fact 3)."""
    stax_db.create_saved_search("Fire", {"tags_any": ["fire"]}, "alice")
    stax_db.create_smart_collection("Recent 3D", {"types": ["3D"]})
    from ui.stacks_lists_panel import StacksListsPanel

    panel = StacksListsPanel(stax_db, stax_config, main_window=_FakeMain(username="alice"))
    qtbot.addWidget(panel)

    assert panel.saved_searches_list.count() == 1
    assert panel.smart_collections_list.count() == 1


@pytest.mark.gui
def test_nav_lists_populate_without_main_window(qtbot, stax_db, stax_config):
    """No main_window at all (embedded/degraded case) must not crash and
    must fall back to a 'guest' user scope rather than raising."""
    from ui.stacks_lists_panel import StacksListsPanel

    panel = StacksListsPanel(stax_db, stax_config, main_window=None)
    qtbot.addWidget(panel)

    assert panel.saved_searches_list.count() == 0
    assert panel._current_user_name() == "guest"


# ---------------------------------------------------------------------------
# MediaDisplayWidget: "Save search..." button
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_save_search_button_persists_current_filter(qtbot, stax_db, stax_config, monkeypatch):
    from ui.media_display_widget import MediaDisplayWidget

    monkeypatch.setattr(
        QtWidgets.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("My Fire Search", True)),
    )

    main_window = _FakeMain(username="alice")
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=main_window)
    qtbot.addWidget(w)
    w.current_filter = {"tags_any": ["fire"]}

    with qtbot.waitSignal(w.saved_search_created, timeout=1000):
        w._on_save_search_clicked()

    saved = stax_db.get_saved_searches("alice")
    assert [s["name"] for s in saved] == ["My Fire Search"]
    assert saved[0]["filter"] == {"tags_any": ["fire"]}


@pytest.mark.gui
def test_save_search_button_cancelled_creates_nothing(qtbot, stax_db, stax_config, monkeypatch):
    from ui.media_display_widget import MediaDisplayWidget

    monkeypatch.setattr(
        QtWidgets.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("", False)),
    )

    w = MediaDisplayWidget(
        stax_db, stax_config, NukeBridge(mock_mode=True),
        main_window=_FakeMain(username="alice"),
    )
    qtbot.addWidget(w)
    w.current_filter = {"tags_any": ["fire"]}

    w._on_save_search_clicked()

    assert stax_db.get_saved_searches("alice") == []


# ---------------------------------------------------------------------------
# main.py wiring: StacksListsPanel.filter_selected -> MediaDisplayWidget.apply_filter
# and MediaDisplayWidget.saved_search_created -> StacksListsPanel.refresh_saved_searches
# ---------------------------------------------------------------------------

def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    """Construct a MainWindow backed by a throwaway DB.

    `Config` reads STOCK_DB only at construction time (src/config.py:107),
    so the env var must be set *before* `Config(...)` is built. Reusing the
    shared `stax_config` fixture here would NOT work: that fixture's Config
    object is already constructed (with STOCK_DB deleted) by the time a
    test body gets a chance to set the env var, so MainWindow would
    silently fall back to the real project database at './data/stax.db'
    instead of an isolated tmp_path db.
    """
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    return win


@pytest.mark.gui
def test_mainwindow_wires_filter_selected_to_apply_filter(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win.stacks_panel.filter_selected.emit({"tags_any": ["fire"]})

    assert win.media_display.current_filter["tags_any"] == ["fire"]


@pytest.mark.gui
def test_mainwindow_wires_saved_search_created_to_nav_refresh(qtbot, mock_nuke, monkeypatch, tmp_path):
    """MainWindow has no logged-in user by default, so the save path scopes
    to 'guest'; emitting `saved_search_created` must make the nav panel pick
    up a saved search created straight through the DB in the meantime."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)

    win.db.create_saved_search("New One", {"text": "x"}, "guest")
    assert win.stacks_panel.saved_searches_list.count() == 0

    win.media_display.saved_search_created.emit()

    assert win.stacks_panel.saved_searches_list.count() == 1
