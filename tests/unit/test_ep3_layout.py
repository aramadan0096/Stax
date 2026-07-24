# -*- coding: utf-8 -*-
"""EP3 Task 8: shape/contract test for the named layout-preset table.

Pure-logic test -- no Qt, no MainWindow. See
`tests/gui/test_ep3_layout_apply.py` for the spec Section 5 GUI test that
actually applies presets to a real MainWindow and asserts the resulting
splitter sizes / dock visibility.
"""

import pytest

from ui.layout_manager import LAYOUT_PRESETS, preset_names


@pytest.mark.unit
def test_presets_defined():
    assert set(preset_names()) == {"Browse", "Review", "Ingest", "Curation"}
    for name in preset_names():
        p = LAYOUT_PRESETS[name]
        assert "main_sizes" in p and len(p["main_sizes"]) == 3


@pytest.mark.unit
def test_preset_shape_has_preview_visible_and_docks():
    """Every preset declares `preview_visible` (bool) and a `docks` dict
    covering the three dockable panels. `preview_visible` -- not the
    brief's original `right_visible` -- names exactly what it now
    controls: the video_player_pane specifically, not the whole right
    column (which, post EP3 Task 6, always stays visible so the sticky
    inspector remains reachable)."""
    for name in preset_names():
        p = LAYOUT_PRESETS[name]
        assert isinstance(p["preview_visible"], bool)
        assert set(p["docks"].keys()) == {"history", "settings", "analytics"}


@pytest.mark.unit
def test_no_preset_declares_a_zero_right_column():
    """Regression guard at the data level: EP3 Task 6 fixed a bug where
    driving the right column to width 0 hid the sticky inspector. No
    preset's nominal `main_sizes[2]` should encode that mistake again --
    even though `apply_preset()` additionally enforces this dynamically
    via `collapse_preview_pane()`'s inspector-derived floor at apply
    time (see the GUI test), the static table itself must not regress."""
    for name in preset_names():
        assert LAYOUT_PRESETS[name]["main_sizes"][2] > 0
