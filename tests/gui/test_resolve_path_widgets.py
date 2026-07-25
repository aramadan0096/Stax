import os

import pytest

from utils.paths import resolve_path
from ui.media_display_widget import MediaDisplayWidget
from ui.media_info_popup import MediaInfoPopup
from video_player_widget import VideoPlayerWidget
from nuke_bridge import NukeBridge


@pytest.mark.gui
def test_gallery_wrapper_matches_shared_helper(qtbot, tmp_path, stax_db, stax_config, mock_nuke):
    """The widget wrappers must produce exactly what the shared helper produces."""
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)

    rel = os.path.join("previews", "a.png")
    assert w._resolve_path(rel) == resolve_path(rel, project_root=w._project_root)
    assert w._resolve_path(None) is None
    assert w._resolve_path("   ") is None
    ap = os.path.abspath(str(tmp_path / "b.png"))
    assert w._resolve_path(ap) == os.path.normpath(ap)


@pytest.mark.gui
def test_popup_and_player_wrappers_match_shared_helper(qtbot, stax_db, stax_config):
    rel = os.path.join("previews", "c.png")

    popup = MediaInfoPopup()
    qtbot.addWidget(popup)
    assert popup._resolve_path(rel) == resolve_path(rel, project_root=popup._project_root)
    assert popup._resolve_path(None) is None

    player = VideoPlayerWidget(stax_db, stax_config)
    qtbot.addWidget(player)
    assert player._resolve_path(rel) == resolve_path(rel, project_root=player._project_root)
    assert player._resolve_path(None) is None


@pytest.mark.gui
def test_storage_wrapper_prefers_config(qtbot, stax_db, stax_config, mock_nuke):
    """drag_gallery_view's storage variant must still consult Config first."""
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    view = w.gallery_view

    rel = os.path.join("previews", "d.png")
    assert view._resolve_storage_path(rel) == resolve_path(
        rel, project_root=view._project_root, config=view.config
    )
    assert view._resolve_storage_path(None) is None
