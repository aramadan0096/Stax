import pytest

from ui.drag_gallery_view import DragGalleryView
from ui.lazy_gallery_view import LazyGalleryView


@pytest.mark.gui
def test_drag_gallery_is_a_lazy_gallery(qtbot, stax_config):
    from nuke_bridge import NukeBridge
    view = DragGalleryView(db_manager=None, config=stax_config,
                           nuke_bridge=NukeBridge(mock_mode=True))
    qtbot.addWidget(view)
    assert isinstance(view, LazyGalleryView)
    assert hasattr(view, "insert_to_nuke")
    assert hasattr(view, "on_preview_ready")
    assert hasattr(view, "set_item_loader")
