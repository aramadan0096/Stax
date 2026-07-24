import pytest

from ui.command_palette import build_jump_targets


class _FakeConfig(object):
    """Minimal stand-in for src.config.Config — just needs .get(key, default)."""

    def __init__(self, values=None):
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self._values.get(key, default)


class _Recorder(object):
    """Records the id it was called with, for asserting closures bind correctly."""

    def __init__(self):
        self.calls = []

    def __call__(self, item_id):
        self.calls.append(item_id)


def _labels(entries):
    return [label for label, _ in entries]


@pytest.mark.unit
def test_jump_targets_lists_only_when_stack_view_disabled(stax_db):
    stack_id = stax_db.create_stack("Plates", "//server/plates")
    list_id = stax_db.create_list(stack_id, "Beauty")
    stax_db.create_list(stack_id, "Utility")

    config = _FakeConfig({"show_entire_stack_elements": False})
    on_list = _Recorder()
    on_stack = _Recorder()

    entries = build_jump_targets(stax_db, config, on_list, on_stack)
    labels = _labels(entries)

    assert any(lbl.startswith("Go to list: Plates / Beauty") for lbl in labels)
    assert any(lbl.startswith("Go to list: Plates / Utility") for lbl in labels)
    assert not any(lbl.startswith("Go to stack:") for lbl in labels)

    # The list entry actually invokes on_list_selected with the right id.
    beauty_entry = next(t for lbl, t in entries if "Beauty" in lbl)
    beauty_entry()
    assert on_list.calls == [list_id]
    assert on_stack.calls == []


@pytest.mark.unit
def test_jump_targets_include_stacks_when_enabled(stax_db):
    stack_id = stax_db.create_stack("Plates", "//server/plates")
    stax_db.create_list(stack_id, "Beauty")

    config = _FakeConfig({"show_entire_stack_elements": True})
    on_list = _Recorder()
    on_stack = _Recorder()

    entries = build_jump_targets(stax_db, config, on_list, on_stack)
    labels = _labels(entries)

    assert any(lbl == "Go to stack: Plates" for lbl in labels)
    assert any(lbl.startswith("Go to list: Plates / Beauty") for lbl in labels)

    stack_entry = next(t for lbl, t in entries if lbl == "Go to stack: Plates")
    stack_entry()
    assert on_stack.calls == [stack_id]


@pytest.mark.unit
def test_jump_targets_default_config_omits_stacks(stax_db):
    stack_id = stax_db.create_stack("Plates", "//server/plates")
    stax_db.create_list(stack_id, "Beauty")

    # No "show_entire_stack_elements" key at all — must behave like False (the
    # documented default), not raise or include stack entries.
    config = _FakeConfig({})
    entries = build_jump_targets(stax_db, config, _Recorder(), _Recorder())
    labels = _labels(entries)

    assert not any(lbl.startswith("Go to stack:") for lbl in labels)
    assert any(lbl.startswith("Go to list: Plates / Beauty") for lbl in labels)


@pytest.mark.unit
def test_jump_targets_each_entry_captures_its_own_id(stax_db):
    """Classic late-binding closure bug: every callable must bind its own id,
    not the last-iterated stack/list."""
    stack_a = stax_db.create_stack("Alpha", "//server/alpha")
    stack_b = stax_db.create_stack("Bravo", "//server/bravo")
    list_a = stax_db.create_list(stack_a, "ListA")
    list_b = stax_db.create_list(stack_b, "ListB")

    config = _FakeConfig({"show_entire_stack_elements": True})
    on_list = _Recorder()
    on_stack = _Recorder()
    entries = build_jump_targets(stax_db, config, on_list, on_stack)

    for label, target in entries:
        target()

    assert sorted(on_stack.calls) == sorted([stack_a, stack_b])
    assert sorted(on_list.calls) == sorted([list_a, list_b])
