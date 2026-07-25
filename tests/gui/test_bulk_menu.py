import pytest
from PySide2 import QtWidgets

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_bulk_menu_actions_and_admin_gating(qtbot, stax_db, stax_config, mock_nuke):
    w = _widget(qtbot, stax_db, stax_config)

    menu = QtWidgets.QMenu()
    actions = w._populate_bulk_menu(menu, [1, 2, 3], is_admin=True, with_header=False)
    texts = {menu_action.text() for menu_action in menu.actions() if menu_action.text()}
    assert "Add All to Favorites" in texts
    assert "Add All to Playlist..." in texts
    assert "Batch Edit Metadata..." in texts
    assert "Mark All as Deprecated" in texts
    assert "Delete All Selected" in texts
    assert actions['deprecate'].isEnabled() and actions['delete'].isEnabled()

    # Non-admin disables destructive actions
    menu2 = QtWidgets.QMenu()
    actions2 = w._populate_bulk_menu(menu2, [1, 2], is_admin=False, with_header=False)
    assert not actions2['deprecate'].isEnabled()
    assert not actions2['delete'].isEnabled()
    assert actions2['fav'].isEnabled()   # non-destructive stays enabled
    assert actions2['edit'].isEnabled()


@pytest.mark.gui
def test_bulk_menu_header_only_when_requested(qtbot, stax_db, stax_config, mock_nuke):
    w = _widget(qtbot, stax_db, stax_config)

    with_header = QtWidgets.QMenu()
    w._populate_bulk_menu(with_header, [1, 2], is_admin=True, with_header=True)
    without = QtWidgets.QMenu()
    w._populate_bulk_menu(without, [1, 2], is_admin=True, with_header=False)
    # header adds one QWidgetAction + a separator, so more total actions
    assert len(with_header.actions()) == len(without.actions()) + 2


@pytest.mark.gui
def test_dispatch_routes_each_action(qtbot, stax_db, stax_config, mock_nuke, monkeypatch):
    w = _widget(qtbot, stax_db, stax_config)
    calls = []
    for name in ("bulk_add_to_favorites", "bulk_add_to_playlist", "open_batch_edit",
                 "bulk_mark_deprecated", "bulk_delete"):
        monkeypatch.setattr(w, name, lambda ids, _n=name: calls.append((_n, ids)))

    menu = QtWidgets.QMenu()
    actions = w._populate_bulk_menu(menu, [7, 8], is_admin=True, with_header=False)
    for key in ("fav", "playlist", "edit", "deprecate", "delete"):
        w._dispatch_bulk_action(actions[key], actions, [7, 8])

    assert [name for name, _ in calls] == [
        "bulk_add_to_favorites", "bulk_add_to_playlist", "open_batch_edit",
        "bulk_mark_deprecated", "bulk_delete",
    ]
    assert all(ids == [7, 8] for _, ids in calls)


@pytest.mark.gui
def test_dispatch_ignores_a_dismissed_menu(qtbot, stax_db, stax_config, mock_nuke, monkeypatch):
    """menu.exec_() returns None when the user presses Escape."""
    w = _widget(qtbot, stax_db, stax_config)
    called = []
    monkeypatch.setattr(w, "bulk_delete", lambda ids: called.append(ids))

    menu = QtWidgets.QMenu()
    actions = w._populate_bulk_menu(menu, [1, 2], is_admin=True, with_header=False)
    w._dispatch_bulk_action(None, actions, [1, 2])
    assert called == []
