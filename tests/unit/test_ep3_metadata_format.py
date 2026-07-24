import pytest
from ui.metadata_format import (
    human_size,
    element_field_rows,
    VIDEO_EXTS,
    SEQUENCE_EXTS,
    detect_playback_mode,
)


@pytest.mark.unit
def test_human_size_units():
    assert human_size(500) == "500 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


@pytest.mark.unit
def test_field_rows_include_core_fields():
    rows = dict(element_field_rows({"name": "a", "type": "2D", "format": ".exr",
                                    "frame_range": "1-10", "file_size": 1024}))
    assert rows["Name"] == "a"
    assert rows["Format"] == ".exr"
    assert rows["Frames"] == "1-10"
    assert rows["Size"] == "1.0 KB"


@pytest.mark.unit
def test_detect_playback_mode_video_extension():
    is_video, is_sequence = detect_playback_mode(".mp4", None)
    assert is_video is True
    assert is_sequence is False


@pytest.mark.unit
def test_detect_playback_mode_sequence_with_frame_range():
    is_video, is_sequence = detect_playback_mode(".exr", "1-10")
    assert is_video is False
    assert is_sequence is True


@pytest.mark.unit
def test_detect_playback_mode_sequence_without_frame_range_is_not_sequence():
    is_video, is_sequence = detect_playback_mode(".exr", None)
    assert is_video is False
    assert is_sequence is False


@pytest.mark.unit
def test_detect_playback_mode_extension_without_leading_dot():
    is_video, is_sequence = detect_playback_mode("mp4", None)
    assert is_video is True
    assert is_sequence is False


@pytest.mark.unit
def test_detect_playback_mode_empty_format():
    is_video, is_sequence = detect_playback_mode("", "1-10")
    assert is_video is False
    assert is_sequence is False

    is_video, is_sequence = detect_playback_mode(None, None)
    assert is_video is False
    assert is_sequence is False
