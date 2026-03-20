# -*- coding: utf-8 -*-
"""
StaX — ingestion_core_patch.py
================================
This file contains the complete set of changes required in
src/ingestion_core.py to wire Features 1 (async preview) and 3
(duplicate detection) into the ingestion pipeline.

HOW TO APPLY
------------
This is NOT a standalone module.  Open src/ingestion_core.py and apply
the three targeted changes described below.  Each change is surrounded
by a clear comment block that shows the Before and After.

CHANGE 1 — Add imports at the top of ingestion_core.py
CHANGE 2 — Replace synchronous _generate_previews() call in ingest_file()
CHANGE 3 — Add duplicate check before writing the DB record
"""

# =============================================================================
# CHANGE 1 — Add these imports near the top of ingestion_core.py
#            (after the existing import block)
# =============================================================================

# ---- NEW: Feature 1 — async preview worker ----
# from src.preview_worker import get_preview_queue, PreviewJob
# ---- NEW: Feature 3 — duplicate detection -----
# from src.duplicate_detection import (
#     compute_phash, find_duplicates, DuplicateDialog
# )


# =============================================================================
# CHANGE 2 — Inside IngestionCore.ingest_file()
#
# Find the existing synchronous preview generation call.  It looks
# approximately like one of these patterns:
#
#   self._generate_previews(element_id, filepath, ...)
#   self._generate_thumbnail(...)
#   preview_path = self._generate_preview(...)
#
# Replace the entire preview-generation block with the async version below.
# The element must already be saved to the DB (element_id must exist) before
# this point.
# =============================================================================

def _async_preview_submission(
    self,
    element_id,
    filepath,
    first_frame_path,
    element_type,
    frame_range,
):
    """
    Submit a preview generation job to the async worker.

    Drop this method into IngestionCore and call it in ingest_file()
    where the synchronous preview call used to be.

    Parameters
    ----------
    element_id      : int
    filepath        : str   original ingested file path
    first_frame_path: str   path to the first frame (same as filepath for movies)
    element_type    : str   '2D', '3D', 'Toolset'
    frame_range     : str or None
    """
    import os
    from src.preview_worker import get_preview_queue, PreviewJob

    previews_dir = os.path.join(
        self.config.get('previews_path', ''),
        str(element_id),
    )

    job = PreviewJob(
        element_id   = element_id,
        source_path  = first_frame_path or filepath,
        output_dir   = previews_dir,
        asset_type   = element_type,
        frame_range  = frame_range,
        config       = self.config,
        priority     = 50,
    )

    worker = get_preview_queue()
    if not worker.isRunning():
        worker.start()
    worker.submit(job)


# =============================================================================
# CHANGE 3 — Inside IngestionCore.ingest_file()
#
# Insert the block below AFTER thumbnail_path is known but BEFORE the
# call to self.db.add_element() (or equivalent DB write).
#
# The variable names (thumbnail_path, name, copy_policy) match what
# IngestionCore already uses — adjust if your local variable names differ.
# =============================================================================

def _check_for_duplicate(self, thumbnail_path, filepath, name, parent_widget=None):
    """
    Compute a perceptual hash and check for duplicates in the DB.

    Returns
    -------
    tuple (phash: str|None, should_skip: bool)
        should_skip=True  means the caller must abort ingestion.
        should_skip=False means ingestion can proceed (no dupe, or user
                          chose "Ingest Anyway").
    """
    if not self.config.get('dedup_enabled', True):
        return None, False

    from src.duplicate_detection import (
        compute_phash, find_duplicates, DuplicateDialog
    )

    # Use the thumbnail if it already exists (faster), else the source
    phash_source = (
        thumbnail_path
        if (thumbnail_path and __import__('os').path.isfile(thumbnail_path))
        else filepath
    )
    phash = compute_phash(phash_source)
    if not phash:
        return None, False

    dupes = find_duplicates(
        self.db,
        phash,
        threshold=self.config.get('dedup_threshold', 8),
    )

    if not dupes:
        return phash, False

    # DuplicateDialog requires a QApplication on the main thread.
    # ingest_file() is always called from MainWindow.perform_ingestion()
    # which runs on the main thread — so this is safe.
    dlg    = DuplicateDialog(dupes, name, parent=parent_widget)
    action = dlg.exec_()

    if action == DuplicateDialog.ACTION_SKIP:
        return phash, True   # caller should return early

    return phash, False   # ACTION_INGEST_ANYWAY — proceed


# =============================================================================
# COMPLETE ingest_file() SKELETON showing the correct call sequence
#
# Your actual ingest_file() has more detail, but the ordering of these
# three hook points is what matters:
# =============================================================================

def ingest_file_skeleton(
    self,
    filepath,
    target_list_id,
    copy_policy=None,
    parent_widget=None,
):
    """
    SKELETON — shows the correct ordering of the three new hook points.
    Do NOT replace your entire ingest_file() with this; use it as a
    structural guide only.
    """
    import os

    # --- existing: sequence detection, frame range, metadata extraction ---
    name        = os.path.basename(filepath)
    element_type = '2D'    # determined by existing logic
    frame_range  = None    # determined by existing logic
    first_frame  = filepath

    # --- existing: file copy (hard/soft policy) ---
    dest_path = filepath   # determined by existing copy logic

    # ---- NEW CHANGE 3: duplicate check (before DB write) -----------------
    thumbnail_path = None   # may or may not exist yet at this point
    phash, should_skip = self._check_for_duplicate(
        thumbnail_path, filepath, name, parent_widget
    )
    if should_skip:
        return {'success': False, 'reason': 'duplicate_skipped',
                'message': 'Skipped — duplicate of existing asset.'}
    # -----------------------------------------------------------------------

    # --- existing: write element record to DB ---
    element_id = self.db.add_element(
        list_fk      = target_list_id,
        name         = name,
        element_type = element_type,
        filepath     = dest_path,
        frame_range  = frame_range,
        # ... other fields ...
    )

    # ---- NEW CHANGE 3b: store phash after getting element_id -------------
    if phash:
        self.db.update_element_phash(element_id, phash)
    # -----------------------------------------------------------------------

    # ---- NEW CHANGE 2: async preview submission (replaces sync call) ------
    self._async_preview_submission(
        element_id       = element_id,
        filepath         = filepath,
        first_frame_path = first_frame,
        element_type     = element_type,
        frame_range      = frame_range,
    )
    # -----------------------------------------------------------------------

    # --- existing: extensibility post-ingest hook ---
    # self.processor_manager.run_post_ingest(element_id, ...)

    return {'success': True, 'element_id': element_id}
