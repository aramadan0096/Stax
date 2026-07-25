# -*- coding: utf-8 -*-
"""At-ingest + backfill indexing (EP7). Reuses the SP2 async-worker pattern
(preview_worker.PreviewWorker). index_element is a pure step: colors always,
embeddings only when an embedder is available. It never raises."""

import logging
import queue

from ai.color_index import compute_color_signature

logger = logging.getLogger(__name__)


def _image_for(row):
    return (row.get("preview_path") or row.get("filepath_hard")
            or row.get("filepath_soft"))


def index_element(db, element_id, embedder=None):
    """Compute + store color (always) and embedding (if embedder available)."""
    result = {"element_id": element_id, "embedded": False, "colored": False}
    row = db.get_element_by_id(element_id)
    if not row:
        return result
    row = dict(row)
    image_path = _image_for(row)

    try:
        sig = compute_color_signature(image_path)
        if sig is not None:
            db.store_element_color(element_id, sig["histogram"], sig["dominant"])
            result["colored"] = True
    except Exception:
        logger.exception("color index failed for element %s", element_id)

    if embedder is not None:
        try:
            if embedder.is_available() and image_path:
                vec = embedder.embed_image(image_path)
                db.store_element_embedding(element_id, embedder.id, vec)
                result["embedded"] = True
        except Exception:
            logger.exception("embedding failed for element %s", element_id)
    return result


try:
    from PySide2 import QtCore

    class AiIndexWorker(QtCore.QThread):
        """Drains a queue of element_ids and indexes them off the GUI thread."""

        indexed = QtCore.Signal(int)
        progress = QtCore.Signal(int, int)   # (done, total)
        finished_all = QtCore.Signal()

        def __init__(self, db, embedder=None, parent=None):
            super(AiIndexWorker, self).__init__(parent)
            self.db = db
            self.embedder = embedder
            self._queue = queue.Queue()
            self._running = True
            self._done = 0
            self._total = 0

        def enqueue(self, element_id):
            self._total += 1
            self._queue.put(element_id)

        def enqueue_many(self, element_ids):
            for eid in element_ids:
                self.enqueue(eid)

        def stop(self):
            self._running = False
            self._queue.put(None)

        def run(self):
            while self._running:
                eid = self._queue.get()
                if eid is None:
                    break
                index_element(self.db, eid, self.embedder)
                self._done += 1
                self.indexed.emit(eid)
                self.progress.emit(self._done, self._total)
                if self._queue.empty():
                    self.finished_all.emit()

except ImportError:   # headless without PySide2
    AiIndexWorker = None   # type: ignore
