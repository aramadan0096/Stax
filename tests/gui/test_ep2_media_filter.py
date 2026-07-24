import pytest

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'b','3D')")


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    return w


def _find_chip_by_text(chip_bar, substring):
    for i in range(chip_bar._row.count()):
        widget = chip_bar._row.itemAt(i).widget()
        if widget is None or widget in (chip_bar.count_label, chip_bar.clear_button):
            continue
        if substring in widget.text():
            return widget
    return None


@pytest.mark.gui
def test_apply_filter_updates_count(qtbot, stax_db, stax_config):
    _seed(stax_db)
    w = _widget(qtbot, stax_db, stax_config)

    w.apply_filter({"types": ["2D"]})

    assert "1 results" in w.chip_bar.count_label.text()
    assert w.current_filter["types"] == ["2D"]


@pytest.mark.gui
def test_chip_removed_round_trips_through_apply_filter(qtbot, stax_db, stax_config):
    """Clicking a chip's remove button must reach `_on_chip_removed` via the
    real `chip_removed` signal connection made in __init__, strip just that
    value from `current_filter`, and re-run the query (count goes from the
    1 filtered match back up to both seeded elements)."""
    _seed(stax_db)
    w = _widget(qtbot, stax_db, stax_config)

    w.apply_filter({"types": ["2D"]})
    assert w.chip_bar.chip_count() == 1

    chip_button = None
    for i in range(w.chip_bar._row.count()):
        widget = w.chip_bar._row.itemAt(i).widget()
        if widget is None or widget in (w.chip_bar.count_label, w.chip_bar.clear_button):
            continue
        chip_button = widget
        break
    assert chip_button is not None, "expected exactly one chip button for types=2D"

    chip_button.click()

    assert w.current_filter["types"] == []
    assert "2 results" in w.chip_bar.count_label.text()
    assert w.chip_bar.chip_count() == 0


@pytest.mark.gui
def test_chip_removal_does_not_resurrect_value_on_next_drawer_toggle(qtbot, stax_db, stax_config):
    """Fix pass regression test for the drawer `_state`-goes-stale bug.

    With a two-value single-facet filter (tags_any=["fire", "smoke"]) built
    up through the drawer's own checkbox-toggle entry point
    (`set_value_state`, the same path a real checkbox click drives), so
    `facet_drawer._state` genuinely holds both tag entries -- not just
    `w.current_filter` -- removing the "fire" chip via the chip bar must
    also clear that entry out of `_state`. Otherwise the very next toggle
    of an *unrelated* checkbox (which rebuilds the whole spec from
    `_state` via `current_filter()`) silently resurrects
    tags_any=["fire"], undoing the user's removal.
    """
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'a','2D','fire')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'b','2D','smoke')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'c','3D','')")

    w = _widget(qtbot, stax_db, stax_config)

    w.facet_drawer.set_value_state("tag", "fire", "include")
    w.facet_drawer.set_value_state("tag", "smoke", "include")
    assert w.current_filter["tags_any"] == ["fire", "smoke"]
    assert w.chip_bar.chip_count() == 2

    fire_chip = _find_chip_by_text(w.chip_bar, "fire")
    assert fire_chip is not None, "expected a removable chip for the fire tag"
    fire_chip.click()

    assert w.current_filter["tags_any"] == ["smoke"]

    # Toggle a *different* drawer checkbox (the "type" facet's 2D value).
    # This fires filter_changed -> apply_filter with a spec rebuilt whole
    # from facet_drawer._state via current_filter().
    w.facet_drawer.set_value_state("type", "2D", "include")

    assert w.current_filter["tags_any"] == ["smoke"], (
        "removing the fire chip must be permanent -- the next unrelated "
        "checkbox toggle resurrected it via the drawer's stale _state"
    )


@pytest.mark.gui
def test_clear_filters_resets_facet_only_zero_result_filter(qtbot, stax_db, stax_config):
    """Fix pass regression test: a facet/chip filter (search box empty)
    that yields zero rows must have a working 'Clear filters' CTA.

    Before the fix, `_request_clear_filters` only cleared the (already
    empty) search box -- no textChanged fired, nothing re-ran, and a
    facet-originated zero-result filter could never be cleared from the
    empty-state page.
    """
    _seed(stax_db)
    w = _widget(qtbot, stax_db, stax_config)

    w.apply_filter({"types": ["nonexistent-type"]})
    assert w.current_elements == []
    assert w.chip_bar.chip_count() == 1
    assert w.search_box.text() == ""

    w._request_clear_filters()

    from filter_spec import empty_filter, normalize
    assert w.current_filter == normalize(empty_filter())
    assert w.chip_bar.chip_count() == 0
    assert len(w.current_elements) == 2
