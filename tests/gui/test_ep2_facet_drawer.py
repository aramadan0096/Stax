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


@pytest.mark.gui
def test_set_facets_restores_exclude_checkbox_state_without_reemitting(qtbot):
    """Symmetric counterpart to
    test_set_facets_restores_checkbox_state_without_reemitting above: that
    test only ever exercised the include -> Qt.Checked restore path. This
    covers exclude -> Qt.PartiallyChecked, which uses the same
    _STATE_TO_QT_CHECKSTATE / _sync_checkbox machinery but was previously
    unasserted."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {"city": 3},
                       "rating": {}, "label": {}, "status": {}})
    drawer.set_value_state("tag", "city", "exclude")

    emitted = []
    drawer.filter_changed.connect(emitted.append)

    drawer.set_facets({"type": {}, "format": {}, "tag": {"city": 9},
                       "rating": {}, "label": {}, "status": {}})

    assert emitted == [], "set_facets() must not emit filter_changed itself"
    checkbox = drawer._checkboxes[("tag", "city")]
    assert checkbox.checkState() == QtCore.Qt.PartiallyChecked
    assert drawer.current_filter()["tags_exclude"] == ["city"]


@pytest.mark.gui
def test_facet_checkbox_is_enabled_and_real_click_updates_filter(qtbot):
    """Regression guard for the critical finding: set_facets() used to build
    each QGroupBox as setCheckable(True) + setChecked(False), which Qt
    disables along with every child widget -- so a real user click on a
    facet value did nothing at all (only the programmatic
    set_value_state() path worked, which is why the pre-fix suite was
    green despite the UI being dead). This drives an actual mouse click and
    must fail against the pre-fix code: isEnabled() would be False there
    and the click would be a no-op (filter_changed never fires)."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {"city": 3},
                       "rating": {}, "label": {}, "status": {}})
    drawer.show()
    qtbot.wait(50)

    checkbox = drawer._checkboxes[("tag", "city")]
    assert checkbox.isEnabled() is True

    with qtbot.waitSignal(drawer.filter_changed, timeout=1000):
        qtbot.mouseClick(checkbox, QtCore.Qt.LeftButton)

    # First real click on a fresh tristate checkbox: Unchecked ->
    # PartiallyChecked ("exclude").
    assert checkbox.checkState() == QtCore.Qt.PartiallyChecked
    assert drawer.current_filter()["tags_exclude"] == ["city"]


@pytest.mark.gui
def test_set_value_state_syncs_rendered_checkbox_and_emits_once(qtbot):
    """set_value_state() is Task 6's chip-removal entry point. If it only
    updated self._state without touching the rendered checkbox, the drawer
    would show a stale (still-checked) box until the next set_facets()
    refresh. It must also emit filter_changed exactly once per call -- not
    zero (silently stale) and not twice (the checkbox sync must be
    signal-blocked, or it would double-fire on top of the explicit emit)."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {"2D": 2}, "format": {}, "tag": {},
                       "rating": {}, "label": {}, "status": {}})

    emitted = []
    drawer.filter_changed.connect(emitted.append)
    checkbox = drawer._checkboxes[("type", "2D")]

    drawer.set_value_state("type", "2D", "include")
    assert checkbox.checkState() == QtCore.Qt.Checked
    assert len(emitted) == 1

    drawer.set_value_state("type", "2D", "exclude")
    assert checkbox.checkState() == QtCore.Qt.PartiallyChecked
    assert len(emitted) == 2

    drawer.set_value_state("type", "2D", None)
    assert checkbox.checkState() == QtCore.Qt.Unchecked
    assert len(emitted) == 3


@pytest.mark.gui
def test_status_active_include_sets_is_deprecated_false(qtbot):
    """The "active" status row used to do nothing: current_filter() only
    ever reacted to value == "deprecated", so toggling "active" mutated
    _state and fired filter_changed while leaving is_deprecated untouched.
    Selecting "active" must now clear is_deprecated to False."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {}, "rating": {},
                       "label": {}, "status": {"active": 4, "deprecated": 1}})
    drawer.set_value_state("status", "active", "include")
    assert drawer.current_filter()["is_deprecated"] is False


@pytest.mark.gui
def test_status_deprecated_include_still_sets_is_deprecated_true(qtbot):
    """Regression guard: the pre-existing "deprecated" row behaviour must
    survive the "active" row fix untouched."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {}, "rating": {},
                       "label": {}, "status": {"active": 4, "deprecated": 1}})
    drawer.set_value_state("status", "deprecated", "include")
    assert drawer.current_filter()["is_deprecated"] is True


@pytest.mark.gui
def test_status_both_rows_set_deprecated_wins_deterministically(qtbot):
    """The two status rows are mutually exclusive filters on the same
    is_deprecated flag. If both end up set at once, the resolution must be
    a deliberate, order-independent rule -- not an accident of
    self._state's dict/insertion order. Per current_filter()'s documented
    resolution, "deprecated" always wins, regardless of which row was set
    first."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {}, "rating": {},
                       "label": {}, "status": {"active": 4, "deprecated": 1}})

    drawer.set_value_state("status", "active", "include")
    drawer.set_value_state("status", "deprecated", "include")
    assert drawer.current_filter()["is_deprecated"] is True

    # Set in the opposite order -- the result must be identical.
    drawer.set_value_state("status", "active", None)
    drawer.set_value_state("status", "deprecated", None)
    drawer.set_value_state("status", "deprecated", "include")
    drawer.set_value_state("status", "active", "include")
    assert drawer.current_filter()["is_deprecated"] is True


@pytest.mark.gui
def test_empty_facet_with_active_selection_still_renders_with_zero_count(qtbot):
    """If a tag selection lives in self._state but a refresh reports zero
    values for that facet, the group box used to vanish entirely -- the
    only in-drawer control that could clear the selection disappeared,
    while current_filter() kept reporting it as active. The facet's group
    box (and the selected checkbox) must stay visible, at a count of 0, so
    the user can still see and clear it."""
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {"city": 3},
                       "rating": {}, "label": {}, "status": {}})
    drawer.set_value_state("tag", "city", "include")

    # Refresh reports zero "tag" values now (e.g. every element carrying
    # the tag got re-tagged elsewhere).
    drawer.set_facets({"type": {}, "format": {}, "tag": {},
                       "rating": {}, "label": {}, "status": {}})

    checkbox = drawer._checkboxes[("tag", "city")]
    assert checkbox.isEnabled() is True
    assert checkbox.checkState() == QtCore.Qt.Checked
    assert checkbox.text() == "city (0)"
    assert drawer.current_filter()["tags_any"] == ["city"]


@pytest.mark.gui
def test_sync_from_filter_rebuilds_state_and_clears_stale_entries(qtbot):
    """sync_from_filter() is current_filter()'s inverse: given a spec, it
    must rebuild self._state to exactly match it -- including dropping any
    entry the spec no longer carries -- and must not emit filter_changed
    (Task 6's apply_filter calls this on every refresh; an emit here would
    re-enter apply_filter)."""
    from filter_spec import empty_filter

    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {"2D": 2, "3D": 1}, "format": {}, "tag": {"fire": 1, "smoke": 1},
                       "rating": {}, "label": {}, "status": {}})
    drawer.set_value_state("tag", "fire", "include")
    drawer.set_value_state("tag", "smoke", "include")
    assert drawer.current_filter()["tags_any"] == ["fire", "smoke"]

    spec = empty_filter()
    spec["tags_any"] = ["smoke"]

    emitted = []
    drawer.filter_changed.connect(emitted.append)
    drawer.sync_from_filter(spec)

    assert emitted == [], "sync_from_filter() must not emit filter_changed"
    assert drawer.current_filter()["tags_any"] == ["smoke"]
    assert ("tag", "fire") not in drawer._state
    fire_checkbox = drawer._checkboxes[("tag", "fire")]
    assert fire_checkbox.checkState() == QtCore.Qt.Unchecked


@pytest.mark.gui
def test_sync_from_filter_round_trips_every_mapped_facet(qtbot):
    """Covers every spec key sync_from_filter maps back onto a facet, using
    the same correspondence current_filter() uses in the other direction.
    tags_all is deliberately not exercised here -- current_filter() never
    emits it, so there is nothing for sync_from_filter to round-trip."""
    from filter_spec import empty_filter

    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    spec = empty_filter()
    spec["types"] = ["2D"]
    spec["formats"] = ["exr"]
    spec["formats_exclude"] = ["mov"]
    spec["tags_any"] = ["fire"]
    spec["tags_exclude"] = ["city"]
    spec["label_fks"] = [42]
    spec["rating_min"] = 3
    spec["is_deprecated"] = True

    drawer.sync_from_filter(spec)
    rebuilt = drawer.current_filter()

    assert rebuilt["types"] == ["2D"]
    assert rebuilt["formats"] == ["exr"]
    assert rebuilt["formats_exclude"] == ["mov"]
    assert rebuilt["tags_any"] == ["fire"]
    assert rebuilt["tags_exclude"] == ["city"]
    assert rebuilt["label_fks"] == [42]
    assert rebuilt["rating_min"] == 3
    assert rebuilt["is_deprecated"] is True

    # is_deprecated False must map onto the "active" row, not "deprecated",
    # and sync_from_filter must fully replace _state, not merge into it --
    # nothing from the spec above should linger.
    spec2 = empty_filter()
    spec2["is_deprecated"] = False
    drawer.sync_from_filter(spec2)
    rebuilt2 = drawer.current_filter()
    assert rebuilt2["is_deprecated"] is False
    assert rebuilt2["types"] == []
    assert ("status", "deprecated") not in drawer._state
