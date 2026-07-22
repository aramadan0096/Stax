import os
import pytest

from ingestion_core import SequenceDetector


@pytest.mark.unit
def test_detects_dot_padded_sequence(tiny_sequence):
    info = SequenceDetector.detect_sequence(tiny_sequence[0])
    assert info is not None
    assert info["frame_count"] == 4
    assert info["first_frame"] == 1
    assert info["last_frame"] == 4
    assert info["frame_range"] == "1-4"
    assert info["padding"] == 4
    assert info["ffmpeg_pattern"] == "shot.%04d.png"


@pytest.mark.unit
def test_single_file_is_not_a_sequence(tmp_path):
    from PIL import Image
    lone = str(tmp_path / "single.0001.png")
    Image.new("RGB", (8, 8), (0, 0, 0)).save(lone)
    assert SequenceDetector.detect_sequence(lone) is None


@pytest.mark.unit
def test_get_sequence_path_builds_printf_pattern(tiny_sequence):
    info = SequenceDetector.detect_sequence(tiny_sequence[0])
    seq_path = SequenceDetector.get_sequence_path(info)
    assert seq_path.endswith("shot.%04d.png")
    assert os.path.dirname(seq_path) == os.path.dirname(tiny_sequence[0])
