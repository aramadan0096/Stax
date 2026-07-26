# -*- coding: utf-8 -*-
"""Application-wide widget behaviour polish.

QSS can size and colour a tab, but three things that decide whether a tab's
*text* is actually readable are Qt properties, not stylesheet properties:

* ``QTabBar.elideMode`` -- defaults to ``Qt::ElideRight`` for tab bars inside a
  QTabWidget, so as soon as the tabs don't fit, labels are cut to
  "Ingest Automa...". No amount of padding fixes that.
* ``QTabBar.usesScrollButtons`` -- the scroll arrows are what make the
  non-elided overflow reachable.
* ``QTabBar.expanding`` -- when true (the default) Qt stretches tabs to fill
  the bar, which fights the per-tab padding/min-width in the stylesheet.

SettingsPanel alone carries 15 tabs inside a dock, so this is not academic.
Rather than patch each construction site (and miss every dialog added later),
`install_widget_polish` puts one event filter on the QApplication and fixes
every QTabBar in the process the moment Qt polishes it -- including tab bars
created by third-party/dialog code.

The filter is deliberately cheap: it compares an int event type before doing
anything else, so the app-wide filter costs a comparison per delivered event.
"""

import logging

from PySide2 import QtCore, QtWidgets

log = logging.getLogger(__name__)

_TAB_BAR_MIN_HEIGHT = 30

_filter_instance = None


def polish_tab_bar(bar):
    """Make *bar* show its full tab text, scrolling instead of eliding."""
    try:
        bar.setElideMode(QtCore.Qt.ElideNone)
        bar.setUsesScrollButtons(True)
        bar.setExpanding(False)
        bar.setDrawBase(False)
        # The stylesheet's per-tab padding drives the width; the height floor
        # keeps the label off the tab's own border on dense dock panels.
        if bar.minimumHeight() < _TAB_BAR_MIN_HEIGHT:
            bar.setMinimumHeight(_TAB_BAR_MIN_HEIGHT)
    except Exception:
        log.debug("Could not polish tab bar %r", bar, exc_info=True)


def polish_tab_widget(widget):
    """Polish a QTabWidget's bar and give every tab a tooltip fallback."""
    polish_tab_bar(widget.tabBar())
    for index in range(widget.count()):
        if not widget.tabToolTip(index):
            widget.setTabToolTip(index, widget.tabText(index))


def polish_existing(root):
    """Apply the tab polish to everything already built under *root*.

    `install_widget_polish` only catches widgets polished *after* it is
    installed; call this once for any widget tree that already exists.
    """
    for tabs in root.findChildren(QtWidgets.QTabWidget):
        polish_tab_widget(tabs)
    for bar in root.findChildren(QtWidgets.QTabBar):
        polish_tab_bar(bar)


class _WidgetPolishFilter(QtCore.QObject):
    """Applies `polish_tab_bar` to every QTabBar Qt polishes."""

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Polish and isinstance(obj, QtWidgets.QTabBar):
            polish_tab_bar(obj)
        return False


def install_widget_polish(app):
    """Install the app-wide polish filter (idempotent). Returns the filter."""
    global _filter_instance
    if app is None:
        return None
    if _filter_instance is None:
        _filter_instance = _WidgetPolishFilter()
    else:
        app.removeEventFilter(_filter_instance)
    _filter_instance.setParent(app)
    app.installEventFilter(_filter_instance)
    return _filter_instance
