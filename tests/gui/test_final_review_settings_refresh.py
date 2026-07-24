# -*- coding: utf-8 -*-
"""Final whole-branch review (exec/ep1-ep2), Finding 2.

`SettingsPanel.settings_changed` fires when an admin edits a label (Labels
tab) or a synonym/smart-collection (Search tab), but neither shell's
`on_settings_changed` used to consume it beyond rebuilding the
`ProcessorManager` -- an open gallery's `_label_color_cache` went stale and
a deleted smart collection stayed in the nav until the next full reload.

Constructing a real `main.MainWindow` / `nuke_launcher.StaXPanel` against the
default `Config` is forbidden here (it would migrate the real
`./data/stax.db`), and building one against an isolated `STOCK_DB`-backed
`Config` (the `_mainwindow_with_temp_db` pattern in test_ep2_nav.py) is
heavier than this fix needs. Instead these tests call each shell's *actual*
(unbound) `on_settings_changed` -- the exact method shipped in `main.py` /
`nuke_launcher.py`, not a hand-mirrored copy of it -- against a minimal
stand-in `self` that wraps the same three real, directly-constructed widgets
(`SettingsPanel`, `MediaDisplayWidget`, `StacksListsPanel`) the shells wire
together. `import main` / `import nuke_launcher` alone do no I/O (Config/DB
construction happens inside `MainWindow.__init__` / `StaXPanel.__init__`,
which these tests never call), so this is safe against the default config.
"""
import pytest

from nuke_bridge import NukeBridge
from ui.settings_panel import SettingsPanel
from ui.media_display_widget import MediaDisplayWidget
from ui.stacks_lists_panel import StacksListsPanel


class _FakeMain(object):
    """Admin stand-in for SettingsPanel's Labels/Search tab admin gating."""

    def __init__(self, admin=True):
        self.is_admin = admin
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        return self.is_admin


class _FakeStatusBar(object):
    def showMessage(self, *a, **k):
        pass


def _build_trio(qtbot, stax_db, stax_config):
    """Construct the three real widgets the shells wire together, without
    constructing a MainWindow/StaXPanel at all."""
    fake_main = _FakeMain(admin=True)

    settings_panel = SettingsPanel(stax_config, stax_db, main_window=fake_main)
    qtbot.addWidget(settings_panel)

    media_display = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(media_display)

    stacks_panel = StacksListsPanel(stax_db, stax_config, main_window=fake_main)
    qtbot.addWidget(stacks_panel)

    return settings_panel, media_display, stacks_panel


@pytest.mark.gui
def test_main_window_on_settings_changed_refreshes_gallery_and_nav(qtbot, stax_db, stax_config):
    """Runs the real `main.MainWindow.on_settings_changed` body."""
    from main import MainWindow

    stax_db.create_smart_collection("Recent Fire", {"tags_any": ["fire"]})
    settings_panel, media_display, stacks_panel = _build_trio(qtbot, stax_db, stax_config)

    assert stacks_panel.smart_collections_list.count() == 1

    # Populate the label color cache the way a normal paint pass would.
    media_display._label_lookup()
    assert media_display._label_color_cache is not None

    class _FakeSelf(object):
        def statusBar(self):
            return _FakeStatusBar()

    fake_self = _FakeSelf()
    fake_self.config = stax_config
    fake_self.media_display = media_display
    fake_self.stacks_panel = stacks_panel

    # Delete the smart collection through the real Search-tab handler.
    settings_panel.collections_table.selectRow(0)
    settings_panel._on_delete_collection()
    assert stax_db.get_smart_collections() == []
    # Nav must NOT have refreshed yet -- proves the refresh below comes from
    # on_settings_changed, not from _on_delete_collection itself.
    assert stacks_panel.smart_collections_list.count() == 1

    MainWindow.on_settings_changed(fake_self)

    assert stacks_panel.smart_collections_list.count() == 0
    assert media_display._label_color_cache is None


@pytest.mark.gui
def test_staxpanel_on_settings_changed_refreshes_gallery_and_nav(qtbot, stax_db, stax_config):
    """Runs the real `nuke_launcher.StaXPanel.on_settings_changed` body (the
    embedded-Nuke shell): no `statusBar()`, uses `show_status()` and the
    module-level `logger` global instead of main.py's `log`."""
    import nuke_launcher

    stax_db.create_smart_collection("Recent Fire", {"tags_any": ["fire"]})
    settings_panel, media_display, stacks_panel = _build_trio(qtbot, stax_db, stax_config)

    assert stacks_panel.smart_collections_list.count() == 1
    media_display._label_lookup()
    assert media_display._label_color_cache is not None

    class _FakeSelf(object):
        def show_status(self, *a, **k):
            pass

    fake_self = _FakeSelf()
    fake_self.config = stax_config
    fake_self.media_display = media_display
    fake_self.stacks_panel = stacks_panel

    settings_panel.collections_table.selectRow(0)
    settings_panel._on_delete_collection()
    assert stax_db.get_smart_collections() == []
    assert stacks_panel.smart_collections_list.count() == 1

    nuke_launcher.StaXPanel.on_settings_changed(fake_self)

    assert stacks_panel.smart_collections_list.count() == 0
    assert media_display._label_color_cache is None


@pytest.mark.gui
def test_on_settings_changed_noop_safe_with_nothing_loaded(qtbot, stax_db, stax_config):
    """Guard requirement: refreshing must not raise when no list/elements are
    loaded yet (the state right after construction)."""
    from main import MainWindow

    _, media_display, stacks_panel = _build_trio(qtbot, stax_db, stax_config)
    assert media_display.current_list_id is None
    assert media_display.current_elements == []

    class _FakeSelf(object):
        def statusBar(self):
            return _FakeStatusBar()

    fake_self = _FakeSelf()
    fake_self.config = stax_config
    fake_self.media_display = media_display
    fake_self.stacks_panel = stacks_panel

    MainWindow.on_settings_changed(fake_self)  # must not raise


@pytest.mark.gui
def test_on_settings_changed_noop_safe_without_stacks_panel(qtbot, stax_db, stax_config):
    """Embedded-mode / construction-order guard: must not crash when `self`
    has no `stacks_panel` attribute (yet)."""
    from main import MainWindow

    _, media_display, _stacks_panel = _build_trio(qtbot, stax_db, stax_config)

    class _FakeSelf(object):
        def statusBar(self):
            return _FakeStatusBar()

    fake_self = _FakeSelf()
    fake_self.config = stax_config
    fake_self.media_display = media_display
    # Deliberately no stacks_panel attribute.

    MainWindow.on_settings_changed(fake_self)  # must not raise
