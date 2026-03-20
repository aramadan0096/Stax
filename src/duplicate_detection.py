# -*- coding: utf-8 -*-
"""
StaX — Duplicate Detection  (Feature 3)
========================================
Uses perceptual hashing (pHash via Pillow/imagehash) to detect visually
identical or near-identical assets at ingest time, preventing library bloat.

Components
----------
  compute_phash(path)           → str | None
      Compute a hex pHash string for the first readable frame of *path*.

  find_duplicates(db, phash, threshold, exclude_id)  → list[dict]
      Query the DB for elements whose pHash is within *threshold* Hamming
      bits of the given hash.

  DuplicateDialog               QDialog
      Shown to the user when a candidate duplicate is found.
      Options: Skip (cancel ingest), Merge (link to existing), Ingest Anyway.

Integration in IngestionCore.ingest_file()
------------------------------------------
After generating the thumbnail and before writing the DB record:

    from src.duplicate_detection import compute_phash, find_duplicates
    from src.ui.duplicate_dialog import DuplicateDialog

    phash = compute_phash(thumbnail_path or filepath)
    if phash:
        dupes = find_duplicates(self.db, phash,
                                threshold=self.config.get('dedup_threshold', 8))
        if dupes:
            # Must be called on the main thread — emit a signal from worker
            # and handle in MainWindow, or run synchronously when ingest
            # is triggered from the GUI.
            dlg = DuplicateDialog(dupes, new_element_name, parent_widget)
            action = dlg.exec_()   # DuplicateDialog.ACTION_*
            if action == DuplicateDialog.ACTION_SKIP:
                return {'success': False, 'reason': 'duplicate_skipped'}
            # ACTION_INGEST_ANYWAY falls through to normal ingest

Store the hash after inserting:

    self.db.update_element_phash(element_id, phash)
"""

from __future__ import absolute_import, unicode_literals

import os
import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pHash computation
# ---------------------------------------------------------------------------

def compute_phash(path):
    """
    Compute a perceptual hash (pHash) for the image at *path*.

    Returns a hex string (e.g. '8f6e3a1b2c...') or None if computation
    fails (missing file, unsupported format, imagehash not installed).
    """
    if not path or not os.path.isfile(path):
        return None

    try:
        import imagehash
        from PIL import Image
        img  = Image.open(path).convert("RGB")
        h    = imagehash.phash(img)
        return str(h)   # hex string, 16 chars for hash_size=8
    except ImportError:
        log.debug(
            "imagehash not installed — falling back to basic MD5 hash. "
            "Install imagehash for perceptual duplicate detection."
        )
        return _md5_hash(path)
    except Exception as exc:
        log.debug("pHash failed for %s: %s", path, exc)
        return None


def _md5_hash(path):
    """Fallback: first 16 chars of MD5 of the file content."""
    try:
        import hashlib
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return None


def hamming_distance(hash_a, hash_b):
    """
    Return the Hamming distance between two pHash hex strings.
    Lower = more similar.  0 = identical.
    Falls back to 0 if hashes are equal, 999 on error.
    """
    if hash_a == hash_b:
        return 0
    try:
        import imagehash
        return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
    except Exception:
        # If imagehash is unavailable, treat non-equal MD5 as distance 999
        return 999


def find_duplicates(db, phash, threshold=8, exclude_id=None):
    """
    Search the DB for elements whose pHash is within *threshold* Hamming
    distance of *phash*.

    Parameters
    ----------
    db          : DatabaseManager
    phash       : str   hash of the candidate asset
    threshold   : int   max Hamming bits to consider a duplicate (default 8)
    exclude_id  : int   element_id to skip (the asset being ingested)

    Returns
    -------
    list[dict]  matching element rows, each augmented with a 'distance' key
    """
    if not phash:
        return []

    try:
        candidates = db.get_elements_with_phash()
    except AttributeError:
        log.warning(
            "db_manager does not expose get_elements_with_phash() — "
            "duplicate detection disabled."
        )
        return []

    results = []
    for elem in candidates:
        if exclude_id is not None and elem.get("element_id") == exclude_id:
            continue
        stored = elem.get("phash") or ""
        if not stored:
            continue
        dist = hamming_distance(phash, stored)
        if dist <= threshold:
            d = dict(elem)
            d["distance"] = dist
            results.append(d)

    results.sort(key=lambda x: x["distance"])
    return results


# ---------------------------------------------------------------------------
# DuplicateDialog
# ---------------------------------------------------------------------------

try:
    from PySide2 import QtWidgets, QtCore, QtGui

    class DuplicateDialog(QtWidgets.QDialog):
        """
        Modal dialog shown when a potential duplicate is detected.

        Usage
        -----
            dlg = DuplicateDialog(duplicates, new_name, parent=self)
            result = dlg.exec_()
            if result == DuplicateDialog.ACTION_SKIP:
                return   # abort ingest

        Class attributes
        ----------------
        ACTION_SKIP         = 0   user chose to cancel the ingest
        ACTION_INGEST_ANYWAY= 1   user chose to ingest despite duplicate
        """

        ACTION_SKIP          = 0
        ACTION_INGEST_ANYWAY = 1

        def __init__(self, duplicates, new_name="", parent=None):
            super(DuplicateDialog, self).__init__(parent)
            self.setWindowTitle("Duplicate Asset Detected")
            self.setMinimumWidth(520)
            self.setModal(True)
            self._action = self.ACTION_SKIP
            self._setup_ui(duplicates, new_name)

        def _setup_ui(self, duplicates, new_name):
            layout = QtWidgets.QVBoxLayout(self)
            layout.setSpacing(12)

            # Header
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(
                self.style().standardPixmap(
                    QtWidgets.QStyle.SP_MessageBoxWarning
                ).scaled(32, 32, QtCore.Qt.KeepAspectRatio,
                         QtCore.Qt.SmoothTransformation)
            )
            header_text = QtWidgets.QLabel(
                "<b>Possible duplicate detected</b><br>"
                "The asset you are ingesting may already be in the library."
            )
            header_text.setWordWrap(True)

            header_row = QtWidgets.QHBoxLayout()
            header_row.addWidget(icon_label)
            header_row.addWidget(header_text, 1)
            layout.addLayout(header_row)

            # New asset label
            if new_name:
                layout.addWidget(
                    QtWidgets.QLabel(
                        "<b>Ingesting:</b> {}".format(new_name)
                    )
                )

            # Duplicate list
            layout.addWidget(
                QtWidgets.QLabel(
                    "Existing asset(s) with similar visual content:"
                )
            )

            table = QtWidgets.QTableWidget(len(duplicates), 4)
            table.setHorizontalHeaderLabels(
                ["Name", "List", "Format", "Similarity"]
            )
            table.horizontalHeader().setStretchLastSection(True)
            table.setEditTriggers(
                QtWidgets.QAbstractItemView.NoEditTriggers
            )
            table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows
            )
            table.verticalHeader().hide()
            table.setMaximumHeight(180)

            for row, dup in enumerate(duplicates):
                distance = dup.get("distance", 999)
                sim_pct  = max(0, int(100 - (distance / 64.0) * 100))

                table.setItem(
                    row, 0,
                    QtWidgets.QTableWidgetItem(dup.get("name", ""))
                )
                table.setItem(
                    row, 1,
                    QtWidgets.QTableWidgetItem(
                        dup.get("list_name", str(dup.get("list_fk", "")))
                    )
                )
                table.setItem(
                    row, 2,
                    QtWidgets.QTableWidgetItem(dup.get("format", ""))
                )
                sim_item = QtWidgets.QTableWidgetItem(
                    "{}% ({} bit{})".format(
                        sim_pct, distance,
                        "s" if distance != 1 else ""
                    )
                )
                if distance == 0:
                    sim_item.setForeground(QtGui.QColor("#e05555"))
                elif distance <= 4:
                    sim_item.setForeground(QtGui.QColor("#e0a055"))
                table.setItem(row, 3, sim_item)

            table.resizeColumnsToContents()
            layout.addWidget(table)

            # Threshold hint
            hint = QtWidgets.QLabel(
                "<i>Tip: adjust duplicate sensitivity in Settings → "
                "Ingest → Duplicate threshold.</i>"
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

            # Buttons
            btn_layout = QtWidgets.QHBoxLayout()
            btn_layout.addStretch()

            btn_skip = QtWidgets.QPushButton("Skip (don't ingest)")
            btn_skip.setDefault(True)
            btn_skip.clicked.connect(self._on_skip)

            btn_ingest = QtWidgets.QPushButton("Ingest Anyway")
            btn_ingest.clicked.connect(self._on_ingest_anyway)

            btn_layout.addWidget(btn_ingest)
            btn_layout.addWidget(btn_skip)
            layout.addLayout(btn_layout)

        def _on_skip(self):
            self._action = self.ACTION_SKIP
            self.accept()

        def _on_ingest_anyway(self):
            self._action = self.ACTION_INGEST_ANYWAY
            self.accept()

        def exec_(self):
            super(DuplicateDialog, self).exec_()
            return self._action

except ImportError:
    # PySide2 not available (e.g. running tests headlessly)
    class DuplicateDialog(object):   # type: ignore[no-redef]
        ACTION_SKIP          = 0
        ACTION_INGEST_ANYWAY = 1

        def __init__(self, *a, **kw):
            self._action = self.ACTION_SKIP

        def exec_(self):
            return self._action
