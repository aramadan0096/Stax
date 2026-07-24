import pytest
from ui.filter_chip_bar import FilterChipBar


@pytest.mark.gui
def test_renders_chip_per_clause_and_count(qtbot):
    bar = FilterChipBar()
    qtbot.addWidget(bar)
    bar.set_filter({"types": ["2D"], "tags_any": ["fire"]}, result_count=7)
    assert bar.chip_count() == 2
    assert "7" in bar.count_label.text()


@pytest.mark.gui
def test_clear_all_emits(qtbot):
    bar = FilterChipBar()
    qtbot.addWidget(bar)
    bar.set_filter({"types": ["2D"]}, result_count=1)
    with qtbot.waitSignal(bar.cleared, timeout=1000):
        bar.clear_button.click()


@pytest.mark.gui
def test_set_filter_twice_does_not_accumulate_chips(qtbot):
    """set_filter() must fully clear the previous render before drawing the
    new one. If stale chip buttons from a prior filter linger (e.g. because
    count_label/clear_button got re-parented into self._chips, or old chip
    buttons weren't actually disposed of), chip_count() after a second call
    would reflect the union of both specs instead of just the second one."""
    bar = FilterChipBar()
    qtbot.addWidget(bar)

    bar.set_filter({"types": ["2D"], "tags_any": ["fire"]}, result_count=7)
    assert bar.chip_count() == 2

    bar.set_filter({"formats": ["exr"]}, result_count=3)
    assert bar.chip_count() == 1
    assert "3" in bar.count_label.text()

    # count_label and clear_button must not have been duplicated into the
    # chip list or the row layout across the two calls.
    assert bar.count_label not in bar._chips
    assert bar.clear_button not in bar._chips
    # Exactly one count_label and one clear_button widget in the row layout.
    widgets = [bar._row.itemAt(i).widget() for i in range(bar._row.count())]
    widgets = [w for w in widgets if w is not None]
    assert widgets.count(bar.count_label) == 1
    assert widgets.count(bar.clear_button) == 1


@pytest.mark.gui
def test_chip_removed_emits_correctly_typed_key_and_value(qtbot):
    """Task 6 removes exactly one clause value using the (key, value) pair
    a chip's click emits. This must round-trip the original typed value --
    an int label_fk and a bool is_deprecated in particular -- since the
    signal is declared `object` specifically to avoid coercing them to str."""
    bar = FilterChipBar()
    qtbot.addWidget(bar)
    bar.set_filter(
        {
            "tags_any": ["fire"],
            "label_fks": [42],
            "is_deprecated": True,
        },
        result_count=5,
    )

    received = []
    bar.chip_removed.connect(lambda key, value: received.append((key, value)))

    # Locate and click each chip button by its emitted signal, verifying the
    # payload for each one is both correctly keyed and correctly typed.
    for i in range(bar._row.count()):
        w = bar._row.itemAt(i).widget()
        if w in (bar.count_label, bar.clear_button):
            continue
        if w is not None:
            w.click()

    assert ("tags_any", "fire") in received
    assert ("label_fks", 42) in received
    assert ("is_deprecated", True) in received

    label_pair = next(p for p in received if p[0] == "label_fks")
    assert type(label_pair[1]) is int

    deprecated_pair = next(p for p in received if p[0] == "is_deprecated")
    assert type(deprecated_pair[1]) is bool
