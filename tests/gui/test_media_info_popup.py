import pytest

from ui.media_info_popup import MediaInfoPopup


def _elem(**kw):
    base = {"name": "e", "type": "2D", "format": "", "frame_range": None, "file_size": 0}
    base.update(kw)
    return base


@pytest.mark.gui
def test_video_controls_detected_by_format(qtbot):
    popup = MediaInfoPopup()
    qtbot.addWidget(popup)

    popup.show_element(_elem(type="2D", format=".mp4"))
    assert popup.is_video is True
    assert popup.is_sequence is False

    popup.show_element(_elem(type="2D", format=".exr", frame_range="1-10"))
    assert popup.is_video is False
    assert popup.is_sequence is True

    popup.show_element(_elem(type="3D", format=".abc"))
    assert popup.is_video is False
    assert popup.is_sequence is False

    # A lone still (png, no frame range) is neither.
    popup.show_element(_elem(type="2D", format=".png", frame_range=None))
    assert popup.is_video is False
    assert popup.is_sequence is False
