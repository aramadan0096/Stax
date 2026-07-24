# -*- coding: utf-8 -*-
"""EP3 Task 9: pure-logic accessibility helpers (no Qt).

See `tests/gui/test_ep3_accessibility.py` for the Qt-dependent tests that
apply accessibility settings to a real QApplication (font scaling,
additive QSS layering, idempotence/round-trip, and the Settings tab).
"""

import pytest

from ui.accessibility import scaled_point_size


@pytest.mark.unit
def test_scaled_point_size():
    assert scaled_point_size(10, 100) == 10
    assert scaled_point_size(10, 150) == 15
    assert scaled_point_size(10, 125) == 12
