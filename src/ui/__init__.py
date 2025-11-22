# -*- coding: utf-8 -*-
"""
UI Components Module
Centralized imports for all UI widgets and dialogs
"""

# Core Widgets
from src.ui.pagination_widget import PaginationWidget
from src.ui.drag_gallery_view import DragGalleryView
from src.ui.media_info_popup import MediaInfoPopup
from src.ui.stacks_lists_panel import StacksListsPanel
from src.ui.media_display_widget import MediaDisplayWidget
from src.ui.history_panel import HistoryPanel
from src.ui.settings_panel import SettingsPanel

# Dialog Widgets
from src.ui.dialogs import (
    AdvancedSearchDialog,
    AddStackDialog,
    AddListDialog,
    AddSubListDialog,
    CreatePlaylistDialog,
    AddToPlaylistDialog,
    LoginDialog,
    EditElementDialog,
    RegisterToolsetDialog,
    SelectListDialog,
    NukeInstallerDialog,
)

from src.ui.ingest_library_dialog import IngestLibraryDialog

__all__ = [
    # Core Widgets
    'PaginationWidget',
    'DragGalleryView',
    'MediaInfoPopup',
    'StacksListsPanel',
    'MediaDisplayWidget',
    'HistoryPanel',
    'SettingsPanel',
    # Dialogs
    'AdvancedSearchDialog',
    'AddStackDialog',
    'AddListDialog',
    'AddSubListDialog',
    'CreatePlaylistDialog',
    'AddToPlaylistDialog',
    'LoginDialog',
    'EditElementDialog',
    'RegisterToolsetDialog',
    'SelectListDialog',
    'IngestLibraryDialog',
    'NukeInstallerDialog',
]
