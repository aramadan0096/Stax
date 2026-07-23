import pytest

import duplicate_detection as dd
from duplicate_detection import hamming_distance, find_duplicates


@pytest.mark.unit
def test_identical_hashes_zero_distance():
    assert hamming_distance("p:ffff0000ffff0000", "p:ffff0000ffff0000") == 0


@pytest.mark.unit
def test_two_phashes_use_bit_distance():
    d = hamming_distance("p:ffffffffffffffff", "p:fffffffffffffff0")
    assert 0 < d <= 64


@pytest.mark.unit
def test_md5_fallback_nonequal_is_far_not_hexdecoded():
    # Two different MD5 fallbacks must NEVER be hex_to_hash'd; non-equal => far.
    assert hamming_distance("m:0123456789abcdef", "m:fedcba9876543210") == 999


@pytest.mark.unit
def test_md5_equal_is_zero():
    assert hamming_distance("m:0123456789abcdef", "m:0123456789abcdef") == 0


@pytest.mark.unit
def test_mixed_kinds_never_compared_as_phash():
    assert hamming_distance("p:ffffffffffffffff", "m:ffffffffffffffff") == 999


class _FakeDB(object):
    def __init__(self, rows):
        self._rows = rows

    def get_elements_with_phash(self):
        return self._rows


@pytest.mark.unit
def test_find_duplicates_filters_by_threshold_and_sorts():
    rows = [
        {"element_id": 1, "phash": "p:ffffffffffffffff", "name": "a"},
        {"element_id": 2, "phash": "p:0000000000000000", "name": "b"},  # far
        {"element_id": 3, "phash": "", "name": "c"},                     # no hash
    ]
    dupes = find_duplicates(_FakeDB(rows), "p:ffffffffffffffff", threshold=4)
    ids = [d["element_id"] for d in dupes]
    assert ids == [1]
    assert dupes[0]["distance"] == 0
