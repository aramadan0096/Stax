# -*- coding: utf-8 -*-
"""Named layout presets for the main window (EP3 Task 8).

Each preset is a plain dict:

    {
        "main_sizes":      [left, center, right] -- nominal widths for
                            `MainWindow.main_splitter`'s 3 direct children
                            (stacks_panel, media_display, right_splitter).
        "preview_visible": bool -- whether `video_player_pane` (the top
                            widget of the nested `right_splitter`, EP3
                            Task 6) should be shown.
        "docks":            {"history": bool, "settings": bool,
                             "analytics": bool} -- desired visibility of
                            the three QDockWidgets.
    }

`preview_visible` intentionally replaces an earlier `right_visible` name:
since EP3 Task 6 nested `video_player_pane` and the sticky `InspectorPanel`
together inside `main_splitter`'s 3rd column (`right_splitter`), the right
*column* itself must never be hidden or collapsed to width 0 -- doing so
would hide the inspector, including its "No selection" state, which is a
defect Task 6 explicitly fixed (see `MainWindow.collapse_preview_pane`).
`preview_visible` names exactly what a preset actually controls: the video
preview widget, not the column that also holds the inspector.

For that reason the "Ingest" preset here does not encode a literal zero
for the right column, and `apply_preset()` never applies one either -- it
delegates to `MainWindow.collapse_preview_pane()`, which derives the
column's floor width from `InspectorPanel.minimumSizeHint()` (see
`MainWindow._right_column_collapsed_width()`), the same logic already used
when a selection collapses the preview. The `240` stored in the "Ingest"
row below is the same floor constant `_right_column_collapsed_width()`
falls back to, kept here only as a shape-valid placeholder for the static
table (and as the value used when the inspector's real minimum is smaller)
-- the width `apply_preset()` actually requests always comes from
`collapse_preview_pane()`, not from this dict.
"""

LAYOUT_PRESETS = {
    "Browse": {
        "main_sizes": [280, 920, 360],
        "preview_visible": True,
        "docks": {"history": False, "settings": False, "analytics": False},
    },
    "Review": {
        "main_sizes": [0, 700, 860],
        "preview_visible": True,
        "docks": {"history": False, "settings": False, "analytics": False},
    },
    "Ingest": {
        "main_sizes": [280, 1000, 240],
        "preview_visible": False,
        "docks": {"history": True, "settings": False, "analytics": False},
    },
    "Curation": {
        "main_sizes": [320, 1040, 200],
        "preview_visible": True,
        "docks": {"history": False, "settings": False, "analytics": False},
    },
}

_DOCK_ATTRS = (
    ("history", "history_dock"),
    ("settings", "settings_dock"),
    ("analytics", "analytics_dock"),
)


def preset_names():
    return ["Browse", "Review", "Ingest", "Curation"]


def apply_preset(main_window, name):
    """Apply a named layout preset to `main_window` (a `MainWindow`).

    Sets `main_splitter`'s column sizes, shows/hides `video_player_pane`,
    shows/hides the history/settings/analytics docks, and persists the
    selection to `Config` under the `layout_preset` key.
    """
    preset = LAYOUT_PRESETS.get(name)
    if not preset:
        return

    main_splitter = getattr(main_window, "main_splitter", None)
    if main_splitter is not None:
        main_splitter.setSizes(list(preset["main_sizes"]))

    preview_visible = preset["preview_visible"]
    video_pane = getattr(main_window, "video_player_pane", None)
    if video_pane is not None:
        if preview_visible:
            video_pane.setVisible(True)
        elif hasattr(main_window, "collapse_preview_pane"):
            # Reuse the exact inspector-derived floor `collapse_preview_pane()`
            # already computes (EP3 Task 6) instead of duplicating a magic
            # number here -- this is what keeps the sticky inspector
            # reachable and the right column above width 0.
            main_window.collapse_preview_pane()
        else:
            video_pane.setVisible(False)

    docks = preset["docks"]
    for key, dock_attr in _DOCK_ATTRS:
        dock = getattr(main_window, dock_attr, None)
        if dock is not None:
            dock.setVisible(docks.get(key, False))

    config = getattr(main_window, "config", None)
    if config is not None:
        config.set("layout_preset", name)
