# -*- coding: utf-8 -*-
"""UI chrome polish: tab-label room, dock title-bar icons, stepper arrows.

Covers the three defects fixed alongside the layout-scaling pass:

* Tab bars elided their labels ("Ingest Automa...") and had no reachable
  overflow control -- SettingsPanel carries 15 tabs inside a dock.
* QDockWidget declared ``titlebar-close-icon: none`` / ``titlebar-normal-icon:
  none``, so the float and close buttons were invisible (but still clickable).
* QComboBox / QSpinBox styled their drop-down and stepper sub-controls without
  giving them an ``image``, which suppresses Fusion's own arrow -- the
  controls shipped with no affordance at all.
"""

import os

import pytest
from PySide2 import QtCore, QtGui, QtWidgets

from qss_loader import read_stylesheet
from ui.widget_polish import install_widget_polish, polish_existing, polish_tab_bar

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STYLE_QSS = os.path.join(PROJECT_ROOT, "resources", "style.qss")

_TAB_LABELS = [
    "General", "Ingestion", "Preview Media", "Network Performance",
    "Processors", "Security", "Labels", "Search", "Accessibility",
    "Metadata Fields", "Automation", "Ingest Automation", "AI", "Roles",
    "Sync",
]


@pytest.fixture
def styled_app(qapp):
    """The real application stylesheet + widget polish, restored afterwards."""
    original = qapp.styleSheet()
    qapp.setStyleSheet(read_stylesheet(STYLE_QSS))
    install_widget_polish(qapp)
    yield qapp
    qapp.setStyleSheet(original)


def _crowded_tabs(qtbot):
    tabs = QtWidgets.QTabWidget()
    for label in _TAB_LABELS:
        tabs.addTab(QtWidgets.QWidget(), label)
    qtbot.addWidget(tabs)
    tabs.resize(420, 400)   # far too narrow for 15 tabs
    tabs.show()
    qtbot.waitExposed(tabs)
    return tabs


@pytest.mark.gui
def test_tab_bars_never_elide_and_can_scroll(styled_app, qtbot):
    """Every QTabBar is polished the moment Qt polishes it -- no per-call-site
    opt-in, so dialogs added later inherit the fix."""
    bar = _crowded_tabs(qtbot).tabBar()
    assert bar.elideMode() == QtCore.Qt.ElideNone
    assert bar.usesScrollButtons() is True
    assert bar.expanding() is False


@pytest.mark.gui
def test_every_tab_is_wide_enough_for_its_own_label(styled_app, qtbot):
    bar = _crowded_tabs(qtbot).tabBar()
    metrics = QtGui.QFontMetrics(bar.font())
    cramped = [
        (bar.tabText(i), metrics.horizontalAdvance(bar.tabText(i)), bar.tabRect(i).width())
        for i in range(bar.count())
        if bar.tabRect(i).width() < metrics.horizontalAdvance(bar.tabText(i))
    ]
    assert not cramped, "tabs narrower than their label: {}".format(cramped)


@pytest.mark.gui
def test_overflow_tabs_get_styled_scroll_buttons(styled_app, qtbot):
    bar = _crowded_tabs(qtbot).tabBar()
    scrollers = bar.findChildren(QtWidgets.QToolButton)
    assert len(scrollers) >= 2


@pytest.mark.gui
def test_polish_tab_bar_is_safe_on_an_orphan_bar(qtbot):
    """`polish_existing` runs over already-built trees; it must not care
    whether the bar belongs to a QTabWidget."""
    bar = QtWidgets.QTabBar()
    qtbot.addWidget(bar)
    bar.addTab("Only")
    polish_tab_bar(bar)
    assert bar.elideMode() == QtCore.Qt.ElideNone


@pytest.mark.gui
def test_dock_titlebar_shows_float_and_close_icons(styled_app, qtbot):
    win = QtWidgets.QMainWindow()
    qtbot.addWidget(win)
    dock = QtWidgets.QDockWidget("Ingest Automation", win)
    dock.setWidget(QtWidgets.QLabel("content"))
    win.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    win.resize(600, 400)
    win.show()
    qtbot.waitExposed(win)

    buttons = [
        b for b in dock.findChildren(QtWidgets.QAbstractButton)
        if b.objectName().startswith("qt_dockwidget_")
    ]
    assert len(buttons) == 2, [b.objectName() for b in buttons]
    for button in buttons:
        assert not button.icon().isNull(), button.objectName()
        assert not button.icon().pixmap(16, 16).isNull(), button.objectName()

    # Both anchor top-right, so the float button must be offset off the close
    # button rather than stacked underneath it.
    left, right = sorted((b.geometry() for b in buttons), key=lambda r: r.x())
    assert not left.intersects(right), (left.getRect(), right.getRect())


@pytest.mark.gui
def test_combobox_arrow_has_room_and_does_not_overlap_the_text(styled_app, qtbot):
    combo = QtWidgets.QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["Nearest neighbour", "Bilinear"])
    combo.resize(240, 28)
    combo.show()
    qtbot.waitExposed(combo)

    option = QtWidgets.QStyleOptionComboBox()
    option.initFrom(combo)
    option.subControls = QtWidgets.QStyle.SC_All
    style = combo.style()
    arrow = style.subControlRect(
        QtWidgets.QStyle.CC_ComboBox, option, QtWidgets.QStyle.SC_ComboBoxArrow, combo)
    field = style.subControlRect(
        QtWidgets.QStyle.CC_ComboBox, option, QtWidgets.QStyle.SC_ComboBoxEditField, combo)

    assert arrow.width() > 0 and arrow.height() > 0
    assert field.right() <= arrow.left() + 1, (field.getRect(), arrow.getRect())


@pytest.mark.gui
@pytest.mark.parametrize("factory", [QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox])
def test_spinbox_steppers_are_stacked_and_sized(styled_app, qtbot, factory):
    spin = factory()
    qtbot.addWidget(spin)
    spin.resize(200, 30)
    spin.show()
    qtbot.waitExposed(spin)

    option = QtWidgets.QStyleOptionSpinBox()
    option.initFrom(spin)
    option.subControls = QtWidgets.QStyle.SC_All
    style = spin.style()
    up = style.subControlRect(
        QtWidgets.QStyle.CC_SpinBox, option, QtWidgets.QStyle.SC_SpinBoxUp, spin)
    down = style.subControlRect(
        QtWidgets.QStyle.CC_SpinBox, option, QtWidgets.QStyle.SC_SpinBoxDown, spin)

    assert up.height() > 0 and down.height() > 0
    assert up.top() < down.top()
    assert not up.intersects(down)


def _main_window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    win = MainWindow(config=Config(config_path=str(tmp_path / "config.json")))
    qtbot.addWidget(win)
    win.resize(1400, 900)
    win.show()
    qtbot.waitExposed(win)
    return win


def _rect_in(widget, ancestor):
    top_left = widget.mapTo(ancestor, QtCore.QPoint(0, 0))
    return QtCore.QRect(top_left, widget.size())


@pytest.mark.gui
def test_media_frame_fills_its_column(qtbot, mock_nuke, monkeypatch, tmp_path):
    """The action tray reserves its row height while hidden. Parented as a
    sibling of the content stack, that reserved strip sat outside the bordered
    media frame and left a permanent dead band under it."""
    win = _main_window(qtbot, monkeypatch, tmp_path)
    media = win.media_display
    views_page = media.content_stack.widget(1)
    media.content_stack.setCurrentIndex(1)
    media.pagination.setVisible(True)
    qtbot.wait(20)

    assert media.action_tray.parentWidget() is views_page
    assert media.action_tray.isVisible() is False

    stack_rect = _rect_in(media.content_stack, media)
    assert media.height() - stack_rect.bottom() <= 3, (
        media.height(), stack_rect.bottom())

    # ...and nothing empty is reserved between the pagination row and the
    # bottom of the frame while no selection is active.
    pagination = _rect_in(media.pagination, media)
    assert stack_rect.bottom() - pagination.bottom() <= 3, (
        stack_rect.bottom(), pagination.bottom())


@pytest.mark.gui
def test_focus_button_floats_inside_the_media_view(qtbot, mock_nuke, monkeypatch, tmp_path):
    """It must sit inside the grid -- not straddling the frame border and the
    pagination row, which is what anchoring to the panel rect produced once a
    chip bar and an action tray were added to the column."""
    win = _main_window(qtbot, monkeypatch, tmp_path)
    media = win.media_display
    media.content_stack.setCurrentIndex(1)
    media.pagination.setVisible(True)
    qtbot.wait(20)

    button = _rect_in(media.focus_mode_button, media)
    view = _rect_in(media.view_stack, media)
    pagination = _rect_in(media.pagination, media)

    assert view.contains(button), (button.getRect(), view.getRect())
    assert not button.intersects(pagination)
    assert media.width() - button.right() >= 8
    # Deeper bottom inset than side inset, so the disc reads as floating over
    # the grid rather than resting on the pagination row.
    assert view.bottom() - button.bottom() >= 24, view.bottom() - button.bottom()


@pytest.mark.gui
def test_focus_button_reanchors_without_a_panel_resize(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    """Switching between the empty page and the views page changes which rect
    the button hangs off without ever resizing the panel. Without an explicit
    hook the button kept its old position -- computed against the content
    stack, whose bottom is *below* the pagination row -- and sat on top of it.
    """
    win = _main_window(qtbot, monkeypatch, tmp_path)
    media = win.media_display
    media.content_stack.setCurrentIndex(0)
    media.pagination.setVisible(True)
    qtbot.wait(20)
    before = media.focus_mode_button.pos().y()

    media.content_stack.setCurrentIndex(1)   # no resize of `media` at all
    qtbot.wait(20)
    after = media.focus_mode_button.pos().y()

    assert after < before, (before, after)
    button = _rect_in(media.focus_mode_button, media)
    assert not button.intersects(_rect_in(media.pagination, media))

    # Hiding pagination grows the view stack; the button follows it back down.
    media.pagination.setVisible(False)
    qtbot.wait(20)
    assert media.focus_mode_button.pos().y() > after


@pytest.mark.gui
def test_search_row_buttons_are_uniform_icon_only_targets(
    qtbot, mock_nuke, monkeypatch, tmp_path
):
    win = _main_window(qtbot, monkeypatch, tmp_path)
    media = win.media_display
    buttons = [media.ai_search_toggle, media.color_search_btn, media.save_search_btn,
               media.gallery_btn, media.list_btn]

    assert len({(b.width(), b.height()) for b in buttons}) == 1
    for button in buttons:
        assert button.text() == ""
        assert not button.icon().isNull()
        # Icon-only controls need an accessible name; the tooltip supplies it.
        assert button.toolTip()
        assert button.property('class') == 'toolicon'


@pytest.mark.gui
def test_nav_add_buttons_have_gutters(qtbot, mock_nuke, monkeypatch, tmp_path):
    win = _main_window(qtbot, monkeypatch, tmp_path)
    nav = win.stacks_panel

    assert nav.add_playlist_btn.text() == ""
    assert not nav.add_playlist_btn.icon().isNull()
    assert nav.add_playlist_btn.toolTip()

    stack, lst = nav.add_stack_btn.geometry(), nav.add_list_btn.geometry()
    assert lst.left() - stack.right() >= 6          # gap between them
    assert stack.left() >= 4                        # left gutter
    assert nav.width() - lst.right() >= 4           # right gutter
    assert nav.add_stack_btn.height() == nav.add_list_btn.height()


@pytest.mark.gui
def test_tree_paints_an_expand_indicator(qtbot, mock_nuke, monkeypatch, tmp_path):
    """Styling QTreeView::branch hands branch painting to the stylesheet
    engine, which draws nothing without an explicit image -- the Stacks &
    Lists tree had no expand/collapse affordance at all."""
    win = _main_window(qtbot, monkeypatch, tmp_path)
    stack_id = win.db.create_stack("branch-probe", str(tmp_path))
    win.db.create_list(stack_id, "child")
    win.stacks_panel.load_data()
    win.stacks_panel.tree.expandAll()
    qtbot.wait(20)

    tree = win.stacks_panel.tree
    root = tree.model().index(0, 0)
    row = tree.visualRect(root)
    image = tree.grab().toImage()
    background = QtGui.QColor("#191a1a")

    painted = 0
    for x in range(0, max(1, row.left())):
        for y in range(max(0, row.top()), min(image.height(), row.bottom() + 1)):
            colour = image.pixelColor(x, y)
            delta = (abs(colour.red() - background.red())
                     + abs(colour.green() - background.green())
                     + abs(colour.blue() - background.blue()))
            if delta > 40:
                painted += 1
    assert painted > 8, "no branch indicator pixels in the indentation strip"


@pytest.mark.gui
def test_main_toolbar_buttons_have_no_box_border(qtbot, mock_nuke, monkeypatch, tmp_path):
    """Section 10's generic 1px border used to include QToolButton, which drew
    a box around every action in the top toolbar."""
    win = _main_window(qtbot, monkeypatch, tmp_path)
    button = win.toolbar.findChildren(QtWidgets.QToolButton)[0]
    image = button.grab().toImage()

    edge = []
    for x in range(image.width()):
        edge.append(image.pixelColor(x, 0).name())
        edge.append(image.pixelColor(x, image.height() - 1).name())
    for y in range(image.height()):
        edge.append(image.pixelColor(0, y).name())
        edge.append(image.pixelColor(image.width() - 1, y).name())

    assert edge.count("#3c3c3c") == 0, "toolbar button still draws an edge border"


@pytest.mark.gui
def test_settings_panel_tabs_are_readable(qtbot, mock_nuke, monkeypatch, tmp_path):
    """The real 15-tab SettingsPanel: MainWindow.setup_ui polishes the trees it
    just built, so this holds even when the app-wide filter wasn't installed
    (tests, embedded Nuke panel)."""
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from config import Config
    from main import MainWindow

    win = MainWindow(config=Config(config_path=str(tmp_path / "config.json")))
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    polish_existing(win)

    bar = win.settings_panel.tab_widget.tabBar()
    assert bar.count() >= 10
    assert bar.elideMode() == QtCore.Qt.ElideNone
    assert bar.usesScrollButtons() is True
