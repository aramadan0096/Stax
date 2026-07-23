import pytest

from utils.formatting import human_size


@pytest.mark.unit
@pytest.mark.parametrize("num_bytes,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1023, "1023 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1048576, "1.0 MB"),
    (5 * 1048576, "5.0 MB"),          # reproduces old >=1MB output
    (2 * 1024 ** 3, "2.0 GB"),        # reproduces old GB output
    (512 * 1024, "512.0 KB"),         # documented sub-MB refinement (was "0.5 MB")
])
def test_boundaries(num_bytes, expected):
    assert human_size(num_bytes) == expected


@pytest.mark.unit
def test_non_numeric_is_safe():
    assert human_size(None) == "0 B"
    assert human_size("bad") == "0 B"
