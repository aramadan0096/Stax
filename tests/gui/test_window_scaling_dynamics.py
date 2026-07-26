# -*- coding: utf-8 -*-
"""Regression tests for widget-scaling / layout-dynamics bugs.

Primary bug: selecting a single element grew the whole main window. Showing
the (previously hidden) preview pane folded the right column's large content
minimum -- dominated by the InspectorPanel's ~500px unscrolled height -- into
the top-level window's minimum, and both splitters being non-collapsible,
Qt enlarged the window (800 -> ~1108px tall) to satisfy it.

Fixes verified here:
* InspectorPanel hosts its form in a QScrollArea, so its minimum height no
  longer drives the window height.
* expand_preview_pane() floors the preview column at the pane's own
  minimum width, so the column (not the window) absorbs it.
* Inspector read-only value labels wrap instead of widening the column.

The `_mainwindow_with_temp_db` helper mirrors the one in
`tests/gui/test_ep3_layout_apply.py` (kept self-contained per this suite's
convention). `STOCK_DB` is set before `Config(...)` so no test here touches
the real project database.
"""

import pytest

from PySide2 import QtWidgets


def _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    cfg = Config(config_path=str(tmp_path / "config.json"))
    win = MainWindow(config=cfg)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


@pytest.mark.gui
def test_expanding_preview_pane_does_not_grow_main_window(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """The single-selection layout reaction (`expand_preview_pane()` shows
    `video_player_pane`) must not push the window's own minimum size beyond
    its current size in either dimension -- that minimum is exactly what Qt
    grows the top-level window to satisfy."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    win.resize(1400, 800)
    qtbot.wait(20)

    win.expand_preview_pane()  # runs on every single-element selection
    qtbot.wait(20)

    assert win.video_player_pane.isVisible() is True
    # The preview column is at least the pane's own effective minimum width,
    # so the column -- not the window -- absorbs it.
    assert (
        win.main_splitter.sizes()[2]
        >= win.video_player_pane.minimumSizeHint().width()
    )
    # The window's minimum size still fits inside its current size: nothing
    # forces it to grow. (Pre-fix the height minimum was ~1108 > 800.)
    min_hint = win.minimumSizeHint()
    assert min_hint.height() <= win.height()
    assert min_hint.width() <= win.width()


@pytest.mark.gui
def test_inspector_form_is_hosted_in_a_scroll_area(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """The inspector's tall content must live inside a resizable QScrollArea
    so its minimum height cannot drive the window height."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    scrolls = win.inspector.findChildren(QtWidgets.QScrollArea)
    assert scrolls, "InspectorPanel must contain a QScrollArea"
    assert any(s.widgetResizable() for s in scrolls)


@pytest.mark.gui
def test_inspector_readonly_labels_wrap(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Long Format/Size/Frames strings must wrap instead of widening the
    whole right column."""
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    for label in win.inspector.readonly_labels.values():
        assert label.wordWrap() is True


@pytest.mark.gui
def test_action_tray_collapses_without_widening_window(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """The multi-select tray must collapse to zero height while hidden -- it
    used to reserve its row height, which left a permanently empty band under
    the media frame in the (normal) no-selection state.

    Its wide 8-button row must still NOT be folded into the window's minimum
    width -- hence the Ignored horizontal policy, which is unrelated to the
    height reservation and must stay.
    """
    win = _mainwindow_with_temp_db(qtbot, tmp_path, monkeypatch)
    sp = win.media_display.action_tray.sizePolicy()
    assert sp.retainSizeWhenHidden() is False
    assert sp.horizontalPolicy() == QtWidgets.QSizePolicy.Ignored


@pytest.mark.gui
def test_quicklook_overlay_rescales_preview_on_resize(
    qtbot, tmp_path
):
    """The spacebar QuickLook preview must re-fit to the overlay's size when
    it is resized, not stay frozen at its first-shown size."""
    from PySide2 import QtGui
    from ui.quicklook_overlay import QuickLookOverlay

    png = str(tmp_path / "big.png")
    pm = QtGui.QPixmap(800, 600)
    pm.fill(QtGui.QColor("red"))
    pm.save(png)

    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.resize(500, 400)
    ov.show_element({"name": "x"}, png, "image")
    qtbot.wait(10)
    small = ov.image_label.pixmap().size()

    ov.resize(1000, 800)
    qtbot.wait(10)
    big = ov.image_label.pixmap().size()

    assert big.width() > small.width()
    assert big.height() > small.height()
