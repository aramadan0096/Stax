# -*- coding: utf-8 -*-
"""Stdlib polling watch-folder scanner (EP6, F031). No watchdog dependency."""

import logging

from PySide2 import QtCore

from src.ingest_automation import scan_folder, MEDIA_EXTS

log = logging.getLogger(__name__)


class WatchFolderScanner(QtCore.QThread):
    """Polls configured folders on an interval and emits newly-seen files.

    `folders` is a list of dicts: {watch_id, path, recipe_id, target_list_id,
    interval_sec?}. Diffing is delegated to the pure `scan_folder`; this class
    only owns the per-folder 'seen' sets, the timer loop, and the signals.
    """

    files_detected = QtCore.Signal(int, list)   # (watch_id, [paths])
    scan_error     = QtCore.Signal(int, str)

    def __init__(self, folders, exts=None, interval_sec=30, parent=None):
        super(WatchFolderScanner, self).__init__(parent)
        self.folders = list(folders)
        self.exts = set(exts) if exts else set(MEDIA_EXTS)
        self.interval_sec = interval_sec
        self._seen = {}          # watch_id -> set(paths)
        self._stopped = False

    def scan_once(self):
        """Run one pass over all folders. Return [(watch_id, [new_paths]), ...]
        for folders that produced new files. Emits files_detected too."""
        results = []
        for wf in self.folders:
            wid = wf["watch_id"]
            seen = self._seen.get(wid, set())
            new_paths, updated = scan_folder(wf["path"], seen, exts=self.exts)
            self._seen[wid] = updated
            if new_paths:
                results.append((wid, new_paths))
                self.files_detected.emit(wid, new_paths)
        return results

    def run(self):
        self._stopped = False
        while not self._stopped:
            try:
                self.scan_once()
            except Exception as exc:              # noqa: BLE001
                log.exception("WatchFolderScanner pass failed")
                self.scan_error.emit(-1, str(exc))
            # sleep in cancellable slices
            slept = 0
            while slept < self.interval_sec * 1000 and not self._stopped:
                self.msleep(200)
                slept += 200

    def stop(self):
        self._stopped = True
