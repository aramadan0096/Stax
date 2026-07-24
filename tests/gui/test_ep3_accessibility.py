# -*- coding: utf-8 -*-
"""EP3 Task 9: accessibility application (font scale / high-contrast / focus QSS)
and the Settings > Accessibility tab.

apply_accessibility() mutates process-global QApplication state (font +
stylesheet). Every test here goes through the `a11y_app` fixture, which
pins the app to a deterministic starting font/stylesheet, resets
accessibility.py's per-app baseline cache so each test gets a fresh
baseline, and restores the app's real original font/stylesheet plus
clears the cache again on teardown -- so nothing leaks into unrelated
tests in the same pytest-qt session.
"""

import pytest
from PySide2 import QtGui, QtWidgets

from ui import accessibility
from ui.accessibility import apply_accessibility, scaled_point_size

_BASE_QSS = "QWidget { color: red; }"  # stand-in for the real resources/style.qss


@pytest.fixture
def a11y_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    true_original_font = QtGui.QFont(app.font())
    true_original_qss = app.styleSheet()

    # Deterministic starting point, independent of platform default fonts.
    base_font = QtGui.QFont(true_original_font)
    base_font.setPointSize(10)
    app.setFont(base_font)
    app.setStyleSheet(_BASE_QSS)
    accessibility.reset_cache(app)

    yield app

    app.setFont(true_original_font)
    app.setStyleSheet(true_original_qss)
    accessibility.reset_cache(app)


def _set_a11y(config, high_contrast=False, text_scale=100, focus_assist=False):
    config.update({
        "a11y_high_contrast": high_contrast,
        "a11y_text_scale": text_scale,
        "a11y_focus_assist": focus_assist,
    })


@pytest.mark.gui
def test_apply_scales_font_from_base(a11y_app, stax_config):
    _set_a11y(stax_config, text_scale=150)
    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == scaled_point_size(10, 150)


@pytest.mark.gui
def test_qss_layers_are_appended_not_replacing_base(a11y_app, stax_config):
    _set_a11y(stax_config, high_contrast=True, focus_assist=True)
    apply_accessibility(a11y_app, stax_config)
    qss = a11y_app.styleSheet()
    assert qss.startswith(_BASE_QSS)
    assert accessibility._HIGH_CONTRAST_QSS in qss
    assert accessibility._FOCUS_QSS in qss


@pytest.mark.gui
def test_apply_150_high_contrast_twice_is_idempotent(a11y_app, stax_config):
    """Applying the same settings twice must not compound the font scale or
    duplicate the appended QSS layer -- the specific bug the base-value
    cache exists to prevent."""
    _set_a11y(stax_config, high_contrast=True, text_scale=150)
    apply_accessibility(a11y_app, stax_config)
    pt_after_first = a11y_app.font().pointSize()
    qss_after_first = a11y_app.styleSheet()

    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == pt_after_first
    assert a11y_app.styleSheet() == qss_after_first
    assert qss_after_first.count(accessibility._HIGH_CONTRAST_QSS) == 1


@pytest.mark.gui
def test_100_to_150_to_100_round_trips_exactly(a11y_app, stax_config):
    original_pt = a11y_app.font().pointSize()
    original_qss = a11y_app.styleSheet()

    _set_a11y(stax_config, high_contrast=False, text_scale=100, focus_assist=False)
    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == original_pt
    assert a11y_app.styleSheet() == original_qss

    _set_a11y(stax_config, high_contrast=True, text_scale=150, focus_assist=True)
    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == scaled_point_size(original_pt, 150)
    assert a11y_app.styleSheet() != original_qss
    assert a11y_app.styleSheet().startswith(original_qss)

    _set_a11y(stax_config, high_contrast=False, text_scale=100, focus_assist=False)
    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == original_pt
    assert a11y_app.styleSheet() == original_qss


@pytest.mark.gui
def test_apply_accessibility_tolerates_missing_app(stax_config):
    apply_accessibility(None, stax_config)


@pytest.mark.gui
def test_apply_accessibility_clamps_out_of_range_text_scale(a11y_app, stax_config):
    """Final whole-branch review 'also fix': only the Settings spinbox
    range (100-150) bounded a11y_text_scale -- a hand-edited or corrupted
    config value outside that range (e.g. 1000) made the app font
    unusable and would never self-correct. apply_accessibility() must
    clamp on read."""
    _set_a11y(stax_config, text_scale=1000)
    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == scaled_point_size(10, 150)

    accessibility.reset_cache(a11y_app)
    a11y_app.setFont(QtGui.QFont(a11y_app.font().family(), 10))
    _set_a11y(stax_config, text_scale=1)
    apply_accessibility(a11y_app, stax_config)
    assert a11y_app.font().pointSize() == scaled_point_size(10, 100)


class _FakeMain(object):
    """Minimal main_window stand-in; accessibility must not require admin."""
    def __init__(self):
        self.is_admin = False
        self.current_user = None

    def check_admin_permission(self, action_name="this action"):
        raise AssertionError("Accessibility is a user preference, not an admin action")


@pytest.mark.gui
def test_accessibility_tab_loads_existing_config_values(a11y_app, stax_config, stax_db):
    stax_config.update({
        "a11y_high_contrast": True,
        "a11y_text_scale": 130,
        "a11y_focus_assist": True,
    })
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain())
    try:
        assert panel.a11y_high_contrast_checkbox.isChecked() is True
        assert panel.a11y_text_scale_spin.value() == 130
        assert panel.a11y_focus_assist_checkbox.isChecked() is True
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_accessibility_tab_is_not_admin_gated(a11y_app, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain())
    try:
        assert panel.a11y_high_contrast_checkbox.isEnabled() is True
        assert panel.a11y_text_scale_spin.isEnabled() is True
        assert panel.a11y_focus_assist_checkbox.isEnabled() is True
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_accessibility_tab_writes_config_and_applies_on_change(a11y_app, stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain())
    try:
        panel.a11y_high_contrast_checkbox.setChecked(True)
        panel.a11y_text_scale_spin.setValue(150)
        panel.a11y_focus_assist_checkbox.setChecked(True)

        assert stax_config.get("a11y_high_contrast") is True
        assert stax_config.get("a11y_text_scale") == 150
        assert stax_config.get("a11y_focus_assist") is True

        # Applied immediately to the live QApplication, not just persisted.
        assert a11y_app.font().pointSize() == scaled_point_size(10, 150)
        assert accessibility._HIGH_CONTRAST_QSS in a11y_app.styleSheet()
        assert accessibility._FOCUS_QSS in a11y_app.styleSheet()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_accessibility_tab_present(stax_config, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_config, stax_db, main_window=_FakeMain())
    try:
        titles = [panel.tab_widget.tabText(i) for i in range(panel.tab_widget.count())]
        assert "Accessibility" in titles
    finally:
        panel.deleteLater()
