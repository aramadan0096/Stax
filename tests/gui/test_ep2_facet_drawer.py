import pytest
from PySide2 import QtCore

from ui.facet_drawer import FacetDrawer


@pytest.mark.gui
def test_include_type_emits_filter(qtbot):
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {"2D": 2, "3D": 1}, "format": {}, "tag": {},
                       "rating": {}, "label": {}, "status": {}})
    with qtbot.waitSignal(drawer.filter_changed, timeout=1000):
        drawer.set_value_state("type", "2D", "include")
    assert drawer.current_filter()["types"] == ["2D"]


@pytest.mark.gui
def test_exclude_tag_populates_exclude_list(qtbot):
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {"city": 3},
                       "rating": {}, "label": {}, "status": {}})
    drawer.set_value_state("tag", "city", "exclude")
    assert drawer.current_filter()["tags_exclude"] == ["city"]


@pytest.mark.gui
def test_set_facets_restores_checkbox_state_without_reemitting(qtbot):
    """A set_facets() refresh rebuilds the group boxes from scratch, but the
    user's existing selections in self._state must survive the refresh AND
    the rebuilt checkboxes must visually reflect them -- without the refresh
    itself firing filter_changed (that would look like a new user edit and
    could loop with Task 6's apply_filter)."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {"2D": 2, "3D": 1}, "format": {}, "tag": {},
                       "rating": {}, "label": {}, "status": {}})
    drawer.set_value_state("type", "2D", "include")

    emitted = []
    drawer.filter_changed.connect(emitted.append)

    # Simulate a refresh (e.g. counts changed because of some other filter
    # edit) that rebuilds the "type" group box's checkboxes from scratch.
    drawer.set_facets({"type": {"2D": 5, "3D": 1}, "format": {}, "tag": {},
                       "rating": {}, "label": {}, "status": {}})

    assert emitted == [], "set_facets() must not emit filter_changed itself"
    checkbox = drawer._checkboxes[("type", "2D")]
    assert checkbox.checkState() == QtCore.Qt.Checked
    # And the underlying filter is unaffected either way.
    assert drawer.current_filter()["types"] == ["2D"]
