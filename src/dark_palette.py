# -*- coding: utf-8 -*-
"""
src/dark_palette.py  —  Place this file at src/dark_palette.py in the repo.
=====================
Sets a fully dark QPalette on the QApplication.

WHY THIS IS NECESSARY
---------------------
QSS `background-color` rules cannot override QPalette for:
  QAbstractItemView   uses QPalette::Base        (tree/list/table fills)
  QWidget             uses QPalette::Window      (panel fills)
  QPushButton         uses QPalette::Button
  QGroupBox           uses QPalette::Window
On Windows with Fusion style these palette roles are white by default.
QSS cannot reach them. setPalette() is the only fix.

CALL ORDER in main()
--------------------
  app.setStyle('Fusion')           # 1. must come first
  apply_dark_palette(app)          # 2. palette before any widget exists
  app.setStyleSheet(stylesheet)    # 3. QSS on top for fine-grained rules
  window = MainWindow(...)         # 4. widgets after both are applied
"""

from PySide2 import QtGui, QtWidgets


def apply_dark_palette(app):
    c = QtGui.QColor
    pal = QtGui.QPalette()

    pal.setColor(QtGui.QPalette.Window,          c("#0e0e0e"))
    pal.setColor(QtGui.QPalette.WindowText,      c("#e7e5e4"))
    pal.setColor(QtGui.QPalette.Base,            c("#0e0e0e"))
    pal.setColor(QtGui.QPalette.AlternateBase,   c("#191a1a"))
    pal.setColor(QtGui.QPalette.Button,          c("#262626"))
    pal.setColor(QtGui.QPalette.ButtonText,      c("#e7e5e4"))
    pal.setColor(QtGui.QPalette.Text,            c("#e7e5e4"))
    pal.setColor(QtGui.QPalette.BrightText,      c("#ffffff"))
    pal.setColor(QtGui.QPalette.PlaceholderText, c("#acabaa"))
    pal.setColor(QtGui.QPalette.Highlight,       c("#71d7cd"))
    pal.setColor(QtGui.QPalette.HighlightedText, c("#003e39"))
    pal.setColor(QtGui.QPalette.Link,            c("#71d7cd"))
    pal.setColor(QtGui.QPalette.LinkVisited,     c("#0a8b82"))
    pal.setColor(QtGui.QPalette.ToolTipBase,     c("#2c2c2c"))
    pal.setColor(QtGui.QPalette.ToolTipText,     c("#e7e5e4"))
    pal.setColor(QtGui.QPalette.Light,           c("#2c2c2c"))
    pal.setColor(QtGui.QPalette.Midlight,        c("#1f2020"))
    pal.setColor(QtGui.QPalette.Mid,             c("#191a1a"))
    pal.setColor(QtGui.QPalette.Dark,            c("#131313"))
    pal.setColor(QtGui.QPalette.Shadow,          c("#0e0e0e"))

    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Window,      c("#131313"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText,  c("#484848"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Base,        c("#131313"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text,        c("#484848"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Button,      c("#1f2020"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText,  c("#484848"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Highlight,   c("#0a8b82"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.HighlightedText, c("#acabaa"))

    app.setPalette(pal)
    QtWidgets.QToolTip.setPalette(pal)