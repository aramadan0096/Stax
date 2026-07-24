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
