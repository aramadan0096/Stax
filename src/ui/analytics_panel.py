# -*- coding: utf-8 -*-
"""
StaX — Usage Analytics Panel  (Feature 6)
==========================================
Tracks every asset insertion and surfaces usage statistics so VFX supervisors
and library managers can see which assets are actually being used.

The module is split into two layers:
  • log_insertion()   — pure Python, no Qt, safe to call from any thread
                        including pipeline scripts and background workers.
  • _BarChart         — PySide2 widget (only defined when Qt is available)
  • AnalyticsPanel    — PySide2 widget (only defined when Qt is available)

Integration
-----------
1. In NukeBridge / NukeIntegration.insert_element() on success:

       from src.ui.analytics_panel import log_insertion
       import socket, os
       log_insertion(db, element_id,
                     user_id=current_user_id,
                     project=os.environ.get('STAX_PROJECT', ''),
                     host=socket.gethostname())

2. In MainWindow.setup_ui():

       from src.ui.analytics_panel import AnalyticsPanel
       self.analytics_dock = QtWidgets.QDockWidget("Analytics", self)
       self.analytics_panel = AnalyticsPanel(self.db)
       self.analytics_dock.setWidget(self.analytics_panel)
       self.analytics_dock.setVisible(False)
       self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.analytics_dock)

3. Ctrl+4 shortcut + toolbar button (see main.py integration).
"""

from __future__ import absolute_import, unicode_literals

import csv
import logging
import os

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# log_insertion — pure Python, NO Qt dependency.
# Safe to call from any thread or headless pipeline script.
# ---------------------------------------------------------------------------

def log_insertion(db, element_id, user_id=None, project="", host=""):
    """
    Write an insertion event to the InsertionLog table.

    Parameters
    ----------
    db         : DatabaseManager (or FakeDB in tests)
    element_id : int
    user_id    : int or None
    project    : str   typically from $STAX_PROJECT env var
    host       : str   socket.gethostname()
    """
    try:
        db.execute(
            "INSERT INTO insertion_log (element_fk, user_fk, project, host) "
            "VALUES (?, ?, ?, ?)",
            (element_id, user_id, project or None, host or None),
        )
        log.debug("Logged insertion: element %d by user %s", element_id, user_id)
    except Exception as exc:
        log.warning("Could not log insertion: %s", exc)


# ---------------------------------------------------------------------------
# Qt-dependent classes — only defined when PySide2 is importable.
# In headless test / CI environments the module loads cleanly because
# log_insertion() lives entirely above this guard.
# ---------------------------------------------------------------------------

try:
    from PySide2 import QtWidgets, QtCore, QtGui
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False


if _QT_AVAILABLE:

    class _BarChart(QtWidgets.QWidget):
        """
        Lightweight horizontal bar chart for top-N rankings.
        Pure Qt — no external charting library required.

        Data format: list of (label: str, value: int)
        """

        def __init__(self, parent=None):
            super(_BarChart, self).__init__(parent)
            self._data  = []
            self._color = QtGui.QColor("#4a7fc1")
            self.setMinimumHeight(100)

        def set_data(self, data):
            """data: list[(label, value)]"""
            self._data = data[:20]
            self.update()
            h = max(100, len(self._data) * 28 + 20)
            self.setMinimumHeight(h)

        def paintEvent(self, _event):
            if not self._data:
                return

            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)

            w     = self.width()
            h     = self.height()
            n     = len(self._data)
            max_v = max(v for _, v in self._data) or 1

            label_w = min(220, int(w * 0.4))
            bar_x   = label_w + 8
            bar_max = w - bar_x - 50

            row_h = max(20, (h - 10) // n)
            fm    = painter.fontMetrics()

            for i, (label, value) in enumerate(self._data):
                y = 5 + i * row_h

                elided = fm.elidedText(label, QtCore.Qt.ElideRight, label_w - 4)
                painter.setPen(self.palette().windowText().color())
                painter.drawText(
                    QtCore.QRect(0, y, label_w, row_h - 2),
                    QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                    elided,
                )

                bar_w = max(2, int((value / max_v) * bar_max))
                rect  = QtCore.QRect(bar_x, y + 2, bar_w, row_h - 6)
                painter.setBrush(self._color)
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRoundedRect(rect, 3, 3)

                painter.setPen(self.palette().windowText().color())
                painter.drawText(
                    QtCore.QRect(bar_x + bar_w + 4, y, 44, row_h - 2),
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                    str(value),
                )

            painter.end()

    class AnalyticsPanel(QtWidgets.QWidget):
        """
        Dockable analytics panel.  Shows usage data from InsertionLog.

        Tabs:
          • Top assets   — bar chart of most-inserted elements
          • Details      — sortable table of the same data
          • Over time    — monthly bar chart
          • By user      — per-user insertion counts

        The panel refreshes lazily — it loads data when it first becomes
        visible and whenever refresh() is explicitly called.
        """

        def __init__(self, db, parent=None):
            super(AnalyticsPanel, self).__init__(parent)
            self.db = db
            self._setup_ui()

        # ------------------------------------------------------------------
        # UI construction
        # ------------------------------------------------------------------

        def _setup_ui(self):
            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            # Toolbar row
            toolbar = QtWidgets.QHBoxLayout()
            toolbar.addWidget(QtWidgets.QLabel("<b>Usage Analytics</b>"))
            toolbar.addStretch()

            self._n_spin = QtWidgets.QSpinBox()
            self._n_spin.setRange(5, 50)
            self._n_spin.setValue(15)
            self._n_spin.setPrefix("Top ")
            self._n_spin.setSuffix("  assets")
            self._n_spin.setToolTip("Number of top assets to show")
            toolbar.addWidget(self._n_spin)

            refresh_btn = QtWidgets.QPushButton("Refresh")
            refresh_btn.clicked.connect(self.refresh)
            toolbar.addWidget(refresh_btn)

            export_btn = QtWidgets.QPushButton("Export CSV…")
            export_btn.clicked.connect(self._export_csv)
            toolbar.addWidget(export_btn)

            root.addLayout(toolbar)

            tabs = QtWidgets.QTabWidget()
            root.addWidget(tabs, 1)

            # Tab 1 — bar chart
            tab_top = QtWidgets.QWidget()
            tl = QtWidgets.QVBoxLayout(tab_top)
            self._chart = _BarChart()
            sc = QtWidgets.QScrollArea()
            sc.setWidget(self._chart)
            sc.setWidgetResizable(True)
            tl.addWidget(sc)
            tabs.addTab(tab_top, "Top Assets")

            # Tab 2 — details table
            tab_table = QtWidgets.QWidget()
            tl2 = QtWidgets.QVBoxLayout(tab_table)
            self._top_table = QtWidgets.QTableWidget(0, 5)
            self._top_table.setHorizontalHeaderLabels(
                ["#", "Name", "List", "Format", "Insertions"]
            )
            self._top_table.horizontalHeader().setStretchLastSection(True)
            self._top_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self._top_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self._top_table.verticalHeader().hide()
            tl2.addWidget(self._top_table)
            tabs.addTab(tab_table, "Details")

            # Tab 3 — over time
            tab_time = QtWidgets.QWidget()
            tl3 = QtWidgets.QVBoxLayout(tab_time)
            self._time_chart = _BarChart()
            self._time_chart._color = QtGui.QColor("#5aab6e")
            st = QtWidgets.QScrollArea()
            st.setWidget(self._time_chart)
            st.setWidgetResizable(True)
            tl3.addWidget(st)
            tabs.addTab(tab_time, "Over Time")

            # Tab 4 — by user
            tab_users = QtWidgets.QWidget()
            tl4 = QtWidgets.QVBoxLayout(tab_users)
            self._users_table = QtWidgets.QTableWidget(0, 3)
            self._users_table.setHorizontalHeaderLabels(
                ["Username", "Insertions", "Last active"]
            )
            self._users_table.horizontalHeader().setStretchLastSection(True)
            self._users_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self._users_table.verticalHeader().hide()
            tl4.addWidget(self._users_table)
            tabs.addTab(tab_users, "By User")

            # Tab 5 — search success (EP9 F060)
            tab_search = QtWidgets.QWidget()
            tls = QtWidgets.QVBoxLayout(tab_search)
            self._search_summary = QtWidgets.QLabel("No search data yet.")
            self._search_summary.setTextFormat(QtCore.Qt.RichText)
            tls.addWidget(self._search_summary)
            tls.addWidget(QtWidgets.QLabel("<b>Top failing searches</b> (zero results)"))
            self._zero_table = QtWidgets.QTableWidget(0, 2)
            self._zero_table.setHorizontalHeaderLabels(["Query", "Count"])
            self._zero_table.horizontalHeader().setStretchLastSection(True)
            self._zero_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self._zero_table.verticalHeader().hide()
            tls.addWidget(self._zero_table)
            export_search_btn = QtWidgets.QPushButton("Export CSV…")
            export_search_btn.clicked.connect(self._export_search_csv)
            tls.addWidget(export_search_btn)
            tabs.addTab(tab_search, "Search")

            # Tab 6 — storage hygiene (EP9 F063)
            tab_storage = QtWidgets.QWidget()
            tlst = QtWidgets.QVBoxLayout(tab_storage)
            self._storage_summary = QtWidgets.QLabel("No storage data yet.")
            self._storage_summary.setTextFormat(QtCore.Qt.RichText)
            self._storage_summary.setWordWrap(True)
            self._storage_summary.setAlignment(QtCore.Qt.AlignTop)
            tlst.addWidget(self._storage_summary, 1)
            export_storage_btn = QtWidgets.QPushButton("Export CSV…")
            export_storage_btn.clicked.connect(self._export_storage_csv)
            tlst.addWidget(export_storage_btn)
            tabs.addTab(tab_storage, "Storage")

            self._total_label = QtWidgets.QLabel("")
            root.addWidget(self._total_label)

        # ------------------------------------------------------------------
        # Data loading
        # ------------------------------------------------------------------

        def refresh(self):
            """Reload all analytics data from the DB."""
            n = self._n_spin.value()
            self._load_top_assets(n)
            self._load_over_time()
            self._load_by_user()
            self._load_search()
            self._load_storage()
            self._load_total()

        def showEvent(self, event):
            """Auto-refresh the first time the panel becomes visible."""
            super(AnalyticsPanel, self).showEvent(event)
            self.refresh()

        def _load_top_assets(self, n):
            try:
                rows = self.db.get_top_inserted_elements(n)
            except Exception as exc:
                log.warning("Analytics top: %s", exc)
                rows = []

            self._chart.set_data(
                [(r.get("name", "?"), r.get("count", 0)) for r in rows]
            )
            self._top_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self._top_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(i + 1)))
                self._top_table.setItem(i, 1, QtWidgets.QTableWidgetItem(row.get("name", "")))
                self._top_table.setItem(i, 2, QtWidgets.QTableWidgetItem(row.get("list_name", "")))
                self._top_table.setItem(i, 3, QtWidgets.QTableWidgetItem(row.get("format", "")))
                cnt = QtWidgets.QTableWidgetItem(str(row.get("count", 0)))
                cnt.setTextAlignment(QtCore.Qt.AlignCenter)
                self._top_table.setItem(i, 4, cnt)
            self._top_table.resizeColumnsToContents()

        def _load_over_time(self):
            try:
                rows = self.db.get_insertions_by_month()
            except Exception as exc:
                log.warning("Analytics monthly: %s", exc)
                rows = []
            self._time_chart.set_data(
                [(r.get("month", "?"), r.get("count", 0)) for r in rows]
            )

        def _load_by_user(self):
            try:
                rows = self.db.get_insertions_by_user()
            except Exception as exc:
                log.warning("Analytics by_user: %s", exc)
                rows = []
            self._users_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self._users_table.setItem(i, 0, QtWidgets.QTableWidgetItem(row.get("username") or "Guest"))
                self._users_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(row.get("count", 0))))
                self._users_table.setItem(i, 2, QtWidgets.QTableWidgetItem(row.get("last_active") or "—"))
            self._users_table.resizeColumnsToContents()

        def _load_search(self):
            try:
                stats = self.db.get_search_success_stats()
                zeros = self.db.get_zero_result_queries(self._n_spin.value())
            except Exception as exc:
                log.warning("Analytics search: %s", exc)
                stats, zeros = {"total": 0, "success_rate": 0.0, "zero_result_rate": 0.0}, []
            self._search_summary.setText(
                "Searches: <b>{}</b> &nbsp;·&nbsp; Success: <b>{:.0f}%</b> "
                "&nbsp;·&nbsp; Zero-result: <b>{:.0f}%</b>".format(
                    stats.get("total", 0),
                    stats.get("success_rate", 0.0) * 100,
                    stats.get("zero_result_rate", 0.0) * 100))
            self._zero_table.setRowCount(len(zeros))
            for i, row in enumerate(zeros):
                self._zero_table.setItem(i, 0, QtWidgets.QTableWidgetItem(row.get("query_text", "")))
                cnt = QtWidgets.QTableWidgetItem(str(row.get("count", 0)))
                cnt.setTextAlignment(QtCore.Qt.AlignCenter)
                self._zero_table.setItem(i, 1, cnt)
            self._zero_table.resizeColumnsToContents()

        def _load_storage(self):
            try:
                s = self.db.get_storage_stats()
                d = self.db.get_duplicate_stats()
            except Exception as exc:
                log.warning("Analytics storage: %s", exc)
                s, d = {}, {}
            fb = self._fmt_bytes
            self._storage_summary.setText(
                "<b>Repository</b><br>"
                "Elements: <b>{ec}</b> &nbsp;·&nbsp; Total size: <b>{tb}</b><br>"
                "Hard copies: <b>{hc}</b> ({hb}) &nbsp;·&nbsp; Soft copies: <b>{sc}</b><br>"
                "Deprecated: <b>{dc}</b> ({db} reclaimable by purge)<br><br>"
                "<b>Duplicate savings</b> (exact perceptual-hash match)<br>"
                "Clusters: <b>{cc}</b> &nbsp;·&nbsp; Redundant copies: <b>{du}</b><br>"
                "Reclaimable: <b>{rb}</b>".format(
                    ec=s.get("element_count", 0), tb=fb(s.get("total_bytes", 0)),
                    hc=s.get("hard_copy_count", 0), hb=fb(s.get("hard_copy_bytes", 0)),
                    sc=s.get("soft_copy_count", 0),
                    dc=s.get("deprecated_count", 0), db=fb(s.get("deprecated_bytes", 0)),
                    cc=d.get("cluster_count", 0), du=d.get("duplicate_count", 0),
                    rb=fb(d.get("reclaimable_bytes", 0))))

        @staticmethod
        def _fmt_bytes(n):
            n = float(n or 0)
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if n < 1024.0 or unit == "TB":
                    return ("{:.0f} {}".format(n, unit) if unit == "B"
                            else "{:.1f} {}".format(n, unit))
                n /= 1024.0

        def _load_total(self):
            try:
                total = self.db.get_total_insertions()
            except Exception:
                total = 0
            self._total_label.setText(
                "Total insertions logged: <b>{}</b>".format(total)
            )

        # ------------------------------------------------------------------
        # Export
        # ------------------------------------------------------------------

        def _export_csv(self):
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Analytics CSV", "stax_analytics.csv",
                "CSV files (*.csv)"
            )
            if not path:
                return
            try:
                rows = self.db.get_top_inserted_elements(self._n_spin.value())
                with open(path, "w", newline="") as fh:
                    writer = csv.DictWriter(
                        fh,
                        fieldnames=["rank", "name", "list_name",
                                    "format", "type", "count"],
                    )
                    writer.writeheader()
                    for i, row in enumerate(rows):
                        writer.writerow({
                            "rank":      i + 1,
                            "name":      row.get("name", ""),
                            "list_name": row.get("list_name", ""),
                            "format":    row.get("format", ""),
                            "type":      row.get("type", ""),
                            "count":     row.get("count", 0),
                        })
                QtWidgets.QMessageBox.information(
                    self, "Exported",
                    "Analytics exported to:\n{}".format(path)
                )
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Export Failed",
                    "Could not write CSV:\n{}".format(exc)
                )

        def _export_search_csv(self):
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Search Analytics CSV", "stax_search_analytics.csv",
                "CSV files (*.csv)")
            if not path:
                return
            try:
                stats = self.db.get_search_success_stats()
                zeros = self.db.get_zero_result_queries(1000)
                with open(path, "w", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["metric", "value"])
                    for k in ("total", "success", "zero_result",
                              "success_rate", "zero_result_rate"):
                        writer.writerow([k, stats.get(k, 0)])
                    writer.writerow([])
                    writer.writerow(["zero_result_query", "count"])
                    for row in zeros:
                        writer.writerow([row.get("query_text", ""), row.get("count", 0)])
                QtWidgets.QMessageBox.information(
                    self, "Exported", "Search analytics exported to:\n{}".format(path))
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Export Failed", "Could not write CSV:\n{}".format(exc))

        def _export_storage_csv(self):
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Storage Analytics CSV", "stax_storage_analytics.csv",
                "CSV files (*.csv)")
            if not path:
                return
            try:
                s = self.db.get_storage_stats()
                d = self.db.get_duplicate_stats()
                with open(path, "w", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["metric", "value"])
                    for k in ("element_count", "total_bytes", "hard_copy_bytes",
                              "hard_copy_count", "soft_copy_count",
                              "deprecated_count", "deprecated_bytes"):
                        writer.writerow([k, s.get(k, 0)])
                    for k in ("cluster_count", "duplicate_count", "reclaimable_bytes"):
                        writer.writerow([k, d.get(k, 0)])
                QtWidgets.QMessageBox.information(
                    self, "Exported", "Storage analytics exported to:\n{}".format(path))
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Export Failed", "Could not write CSV:\n{}".format(exc))

else:
    # -----------------------------------------------------------------------
    # Headless stubs — imported cleanly in test / CI environments
    # -----------------------------------------------------------------------

    class _BarChart:       # type: ignore[no-redef]
        """Stub — PySide2 not available."""

    class AnalyticsPanel:  # type: ignore[no-redef]
        """Stub — PySide2 not available."""

        def __init__(self, db, parent=None):
            self.db = db

        def refresh(self):
            pass
