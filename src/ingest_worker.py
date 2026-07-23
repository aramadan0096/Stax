# -*- coding: utf-8 -*-
"""Shared background ingestion worker for StaX.

Runs IngestionCore.ingest_file over a flat list of (source_path, list_id)
jobs off the GUI thread, reporting progress and a final tally via signals.
Replaces the in-loop GUI-thread ingestion and QApplication.processEvents().
"""

import logging

from PySide2 import QtCore

from src.ingestion_core import IngestionCore

log = logging.getLogger(__name__)


class IngestWorker(QtCore.QThread):
    """QThread that ingests a list of (source_path, target_list_id) jobs.

    Signals
    -------
    progress(int done, int total, str label)
    file_done(dict result)
    ingest_finished(int success, int skipped, int errors)
    ingest_failed(str message)
    """

    progress        = QtCore.Signal(int, int, str)
    file_done       = QtCore.Signal(dict)
    ingest_finished = QtCore.Signal(int, int, int)
    ingest_failed   = QtCore.Signal(str)

    def __init__(self, db, config, jobs, copy_policy="soft", parent=None):
        super(IngestWorker, self).__init__(parent)
        self.db = db
        self.config = config          # MUST be a plain dict (Config.get_all())
        self.jobs = list(jobs)
        self.copy_policy = copy_policy
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import os
        success = skipped = errors = 0
        total = len(self.jobs)
        try:
            core = IngestionCore(self.db, self.config)
            for i, (source_path, list_id) in enumerate(self.jobs, start=1):
                if self._cancelled:
                    break
                label = os.path.basename(source_path)
                self.progress.emit(i, total, label)
                result = core.ingest_file(source_path, list_id,
                                          copy_policy=self.copy_policy)
                if isinstance(result, dict):
                    self.file_done.emit(result)
                    if result.get("success"):
                        success += 1
                    elif result.get("reason") == "duplicate_skipped":
                        skipped += 1
                    else:
                        errors += 1
                else:
                    errors += 1
            self.ingest_finished.emit(success, skipped, errors)
        except Exception as exc:               # noqa: BLE001
            log.exception("IngestWorker crashed")
            self.ingest_failed.emit(str(exc))
