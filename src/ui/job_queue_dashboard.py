# -*- coding: utf-8 -*-
"""Central job-queue dashboard (EP6, F033/F034).

Reads the ingest_jobs ledger and controls SP2's IngestWorker via signals.
It does NOT execute jobs itself — retry/cancel are emitted to the host, which
re-submits to a fresh IngestWorker / flags the running one.
"""

import logging

from PySide2 import QtWidgets, QtCore

log = logging.getLogger(__name__)

_ACTIVE_STATES = ("pending", "running")


class JobQueueDashboard(QtWidgets.QWidget):
    retry_requested  = QtCore.Signal(int)
    cancel_requested = QtCore.Signal(int)

    def __init__(self, db, parent=None):
        super(JobQueueDashboard, self).__init__(parent)
        self.db = db
        self._row_jobs = []      # row index -> (job_id, status)
        layout = QtWidgets.QVBoxLayout(self)

        self.jobs_table = QtWidgets.QTableWidget(0, 4)
        self.jobs_table.setHorizontalHeaderLabels(["Status", "File", "Attempts", "Message"])
        self.jobs_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.jobs_table.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self.jobs_table)

        row = QtWidgets.QHBoxLayout()
        self.retry_button = QtWidgets.QPushButton("Retry")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.clear_button = QtWidgets.QPushButton("Clear finished")
        self.retry_button.clicked.connect(self._on_retry)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.clear_button.clicked.connect(self._on_clear)
        for b in (self.retry_button, self.cancel_button, self.clear_button):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        self._sync_buttons()

    def refresh(self):
        import os
        jobs = self.db.get_jobs()
        self._row_jobs = []
        self.jobs_table.setRowCount(len(jobs))
        for r, job in enumerate(jobs):
            src = job.get("source_path") or ""
            self.jobs_table.setItem(r, 0, QtWidgets.QTableWidgetItem(job.get("status", "")))
            self.jobs_table.setItem(r, 1, QtWidgets.QTableWidgetItem(os.path.basename(src)))
            self.jobs_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(job.get("attempts", 0))))
            self.jobs_table.setItem(r, 3, QtWidgets.QTableWidgetItem(job.get("message") or ""))
            self._row_jobs.append((job["job_id"], job.get("status")))
        self._sync_buttons()

    def _selected(self):
        r = self.jobs_table.currentRow()
        if 0 <= r < len(self._row_jobs):
            return self._row_jobs[r]
        return (None, None)

    def _sync_buttons(self):
        job_id, status = self._selected()
        self.retry_button.setEnabled(status == "failed")
        self.cancel_button.setEnabled(status in _ACTIVE_STATES)

    def _on_retry(self):
        job_id, status = self._selected()
        if job_id is not None and status == "failed":
            self.retry_requested.emit(job_id)

    def _on_cancel(self):
        job_id, status = self._selected()
        if job_id is not None and status in _ACTIVE_STATES:
            self.cancel_requested.emit(job_id)

    def _on_clear(self):
        self.db.clear_finished_jobs()
        self.refresh()
