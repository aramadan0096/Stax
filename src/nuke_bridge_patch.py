# -*- coding: utf-8 -*-
"""
StaX — nuke_bridge_patch.py
============================
This file shows the exact changes required in src/nuke_bridge.py to wire
Feature 6 (usage analytics — insertion logging) into the insertion pipeline.

HOW TO APPLY
------------
Open src/nuke_bridge.py and apply CHANGE 1 (import) and CHANGE 2 (log call).

The critical constraint: logging failures must NEVER break asset insertion.
The entire analytics block is wrapped in a bare try/except.
"""

# =============================================================================
# CHANGE 1 — Add imports near the top of nuke_bridge.py
# =============================================================================

# ---- NEW: Feature 6 — analytics logging ----
# import os
# import socket
# from src.ui.analytics_panel import log_insertion as _log_insertion


# =============================================================================
# CHANGE 2 — Inside NukeIntegration.insert_element() (or NukeBridge equivalent)
#
# Find the SUCCESS PATH — the code that runs after a Read/ReadGeo/Paste node
# has been successfully created in Nuke's DAG.  Append the block below.
#
# self._current_user_id must be set from MainWindow whenever the user logs in.
# Add it to __init__ as: self._current_user_id = None
# Update it from MainWindow.show_login():
#   self.nuke_integration._current_user_id = (
#       self.current_user.get('user_id') if self.current_user else None
#   )
# =============================================================================

def _log_insertion_hook(self, element_id):
    """
    Call this at the end of NukeIntegration.insert_element() on success.
    Wrap in try/except so logging failures never propagate.
    """
    try:
        from src.ui.analytics_panel import log_insertion as _log_insertion
        _log_insertion(
            db         = self.db,
            element_id = element_id,
            user_id    = getattr(self, '_current_user_id', None),
            project    = os.environ.get('STAX_PROJECT', ''),
            host       = socket.gethostname(),
        )
    except Exception:
        pass   # analytics failures are non-fatal


# =============================================================================
# COMPLETE insert_element() SKELETON showing correct hook placement
# =============================================================================

def insert_element_skeleton(self, element_id):
    """
    SKELETON — shows where _log_insertion_hook() is called.
    Do NOT replace your entire method with this.
    """
    element = self.db.get_element_by_id(element_id)
    if element is None:
        raise ValueError("Element {} not found".format(element_id))

    element_type = element.get('type', '2D')

    if element_type == '2D':
        self.nuke_bridge.create_read_node(element)
    elif element_type == '3D':
        self.nuke_bridge.create_read_geo_node(element)
    elif element_type == 'Toolset':
        self.nuke_bridge.paste_toolset(element)

    # Run post-import processor hook (existing)
    # self.processor_manager.run_post_import(element_id, ...)

    # ---- NEW CHANGE 2: log for analytics ----------------------------------
    self._log_insertion_hook(element_id)
    # -----------------------------------------------------------------------
