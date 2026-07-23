import pytest

from PySide2 import QtCore


@pytest.mark.gui
def test_repopulate_triggers_lazy_visible_load(qtbot, stax_db, stax_config):
    """
    C4 regression: _update_views_with_elements populates gallery_view
    directly (bypassing LazyGalleryView.set_elements), so none of that
    class's own triggers (its set_elements timer, scrollbar
    valueChanged, resizeEvent) fire on an ordinary list switch. Without
    an explicit kick, real thumbnails never decode until the user
    happens to resize the window.

    This asserts the concrete fix mechanism: refresh_visible() exists
    on the gallery view and is scheduled (deferred) after repopulation,
    and that the deferred call actually reaches _load_visible, which in
    turn invokes the registered per-item loader for the (now visible)
    items — without requiring a scroll or resize.
    """
    from ui.media_display_widget import MediaDisplayWidget
    from nuke_bridge import NukeBridge

    widget = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(widget)
    widget.show()

    assert hasattr(widget.gallery_view, "refresh_visible")

    # Spy on refresh_visible to confirm it gets scheduled by the
    # repopulation path (mirrors LazyGalleryView.set_elements's own
    # QTimer.singleShot(0, self._load_visible)).
    calls = []
    original = widget.gallery_view.refresh_visible

    def _spy():
        calls.append(True)
        return original()

    widget.gallery_view.refresh_visible = _spy

    # Also spy on the registered lazy item loader to confirm the
    # deferred call actually reaches _load_visible and loads visible
    # items, not just that refresh_visible was scheduled.
    loaded_items = []
    real_loader = None

    def _wrap_set_item_loader(loader):
        def _tracking_loader(item):
            loaded_items.append(item)
            return loader(item)
        widget.gallery_view._item_loader = _tracking_loader

    widget.gallery_view.set_item_loader = _wrap_set_item_loader

    elements = [
        {
            "element_id": 1,
            "name": "elem_one",
            "type": "image",
            "preview_path": None,
            "gif_preview_path": None,
        },
        {
            "element_id": 2,
            "name": "elem_two",
            "type": "image",
            "preview_path": None,
            "gif_preview_path": None,
        },
    ]

    widget._update_views_with_elements(elements)

    # Not yet triggered synchronously inside the loop — the fix defers
    # via QTimer.singleShot(0, ...) so viewport geometry settles first.
    assert calls == []

    # Let the singleShot(0, ...) fire.
    qtbot.wait(50)

    assert calls == [True], (
        "refresh_visible was not scheduled/invoked after repopulating "
        "the gallery — real thumbnails would never decode until a "
        "resize/scroll happens (C4 regression)."
    )
    assert len(loaded_items) == 2, (
        "The deferred refresh_visible() call did not reach "
        "_load_visible/the registered item loader for the visible "
        "items."
    )
