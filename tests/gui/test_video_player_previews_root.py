# -*- coding: utf-8 -*-
"""Regression test for H6: the geometry viewer's /model/ allow-list must be
rooted at the *configured* previews_path, not <project_root>/previews.

Pre-H6, GeometryViewerServer served any path. H6 added a containment check
against previews_root, but GeometryViewerWidget(project_root) was constructed
without threading the configured previews_path through, so in real STOCK_DB /
network-share deployments (where previews live outside the project root),
every real GLB preview fails the allow-list check and 403s.
"""
import pytest


@pytest.mark.gui
def test_video_player_widget_threads_configured_previews_path(qtbot, stax_db, tmp_path):
    """VideoPlayerWidget must pass config['previews_path'] into GeometryViewerWidget
    so its internal _previews_root matches the configured (out-of-tree) location,
    not the project_root/previews default.
    """
    from video_player_widget import VideoPlayerWidget
    from geometry_viewer import _norm

    # Simulate a STOCK_DB deployment: previews live entirely outside the project root.
    configured_previews = tmp_path / "network_share" / "previews"
    configured_previews.mkdir(parents=True)

    config = {"previews_path": str(configured_previews)}

    widget = VideoPlayerWidget(stax_db, config)
    qtbot.addWidget(widget)

    project_root_previews = _norm(
        __import__("os").path.join(widget._project_root, "previews")
    )

    assert widget.geometry_viewer._previews_root == _norm(str(configured_previews)), (
        "geometry_viewer._previews_root should be the configured previews_path, "
        "got {0!r}".format(widget.geometry_viewer._previews_root)
    )
    assert widget.geometry_viewer._previews_root != project_root_previews, (
        "geometry_viewer._previews_root regressed to the <project_root>/previews "
        "default instead of the configured out-of-tree previews_path"
    )
