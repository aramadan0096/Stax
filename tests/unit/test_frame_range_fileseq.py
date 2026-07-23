import pytest

from ingestion_core import parse_frame_range, SequenceDetector


@pytest.mark.unit
def test_simple_contiguous_range():
    first, last, frames = parse_frame_range("1-10")
    assert (first, last) == (1, 10)
    assert frames == list(range(1, 11))


@pytest.mark.unit
def test_negative_first_frame():
    first, last, frames = parse_frame_range("-5-10")
    assert first == -5
    assert last == 10
    assert frames[0] == -5


@pytest.mark.unit
def test_stepped_range():
    first, last, frames = parse_frame_range("1-10x2")
    assert first == 1
    assert last == 9
    assert frames == [1, 3, 5, 7, 9]


@pytest.mark.unit
def test_missing_frames_range():
    first, last, frames = parse_frame_range("1-3,5")
    assert first == 1
    assert last == 5
    assert 4 not in frames


@pytest.mark.unit
def test_single_frame_and_blank():
    assert parse_frame_range("7") == (7, 7, [7])
    assert parse_frame_range("") is None
    assert parse_frame_range(None) is None


@pytest.mark.unit
def test_compact_frame_range_contiguous_matches_first_last():
    # Contiguous must still render "first-last" so SP0's characterization holds.
    assert SequenceDetector._compact_frame_range([1, 2, 3, 4]) == "1-4"


@pytest.mark.unit
def test_compact_frame_range_with_gap():
    assert SequenceDetector._compact_frame_range([1, 2, 3, 5]) == "1-3,5"
