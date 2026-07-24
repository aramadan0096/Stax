# -*- coding: utf-8 -*-
"""Fix pass 3 regression test.

nuke_launcher.StaXPanel.on_stack_selected's zero-elements branch must reset
the empty page on BOTH outcomes of `stack = self.db.get_stack_by_id(stack_id)`
-- including when it comes back falsy (e.g. the stack was deleted between
the user's click and this lookup) -- not just when a stack dict comes back.

Before this fix, only `if stack:` called self.media_display.show_empty_state(...);
the implicit `else` did nothing, so a vanished stack left whatever was already
on screen (including stale elements from a previously-selected stack) in
place.

This drives StaXPanel.on_stack_selected directly against light duck-typed
fakes for self.db / self.config / self.media_display, rather than
constructing a real StaXPanel. A real StaXPanel is heavyweight (real
DB/Config/UI setup) and schedules a QTimer.singleShot(100, self.show_login)
in __init__ that empirically outlives qtbot's widget teardown and can crash
an unrelated *later* test in the same process once enough wall-clock time
has passed (reproduced while drafting this test, by adding a second real
StaXPanel next to tests/nuke/test_panel_advanced_search.py's). That hazard is
pre-existing and out of scope for this control-flow fix, so it is avoided
here entirely rather than worked around.
"""

import pytest

import nuke_launcher


class _FakeConfig(object):
    def __init__(self, show_entire_stack_elements=True):
        self._show_entire = show_entire_stack_elements

    def get(self, key, default=None):
        if key == 'show_entire_stack_elements':
            return self._show_entire
        return default


class _FakePagination(object):
    def __init__(self):
        self.calls = []

    def set_total_items(self, n):
        self.calls.append(('set_total_items', n))

    def set_items_per_page(self, n):
        self.calls.append(('set_items_per_page', n))

    def setVisible(self, v):
        self.calls.append(('setVisible', v))


class _FakeContentStack(object):
    def __init__(self):
        self.calls = []

    def setCurrentIndex(self, idx):
        self.calls.append(idx)


class _FakeMediaDisplay(object):
    """Pre-loaded with stale state, as if a previous, populated stack were
    already on screen -- exactly what must be cleared when the newly
    selected stack turns out to be gone."""

    def __init__(self):
        self.current_list_id = 'stale-list'
        self.current_elements = ['stale-element']
        self.current_tag_filter = ['stale-tag']
        self.pagination = _FakePagination()
        self.content_stack = _FakeContentStack()
        self.show_empty_state_calls = []

    def show_empty_state(self, message=None, hint=None):
        self.show_empty_state_calls.append((message, hint))

    def _display_current_page(self):
        pass


class _FakeDBStackGone(object):
    """get_stack_by_id returns None: the stack vanished between selection
    and this lookup."""

    def get_lists_by_stack(self, stack_id):
        return []

    def get_elements_by_list(self, list_id):
        return []

    def get_stack_by_id(self, stack_id):
        return None


class _FakePanel(object):
    def __init__(self, db):
        self.config = _FakeConfig()
        self.db = db
        self.media_display = _FakeMediaDisplay()
        self.status_calls = []

    def show_status(self, text):
        self.status_calls.append(text)


@pytest.mark.unit
def test_on_stack_selected_resets_empty_page_when_stack_is_gone():
    panel = _FakePanel(_FakeDBStackGone())

    nuke_launcher.StaXPanel.on_stack_selected(panel, 999999)

    # The regression: before the fix, a falsy `stack` skipped show_empty_state
    # entirely, so this list would be empty instead of holding one no-arg call.
    assert panel.media_display.show_empty_state_calls == [(None, None)]

    # The reset of list/elements/tag-filter state happens unconditionally
    # earlier in the method, on both branches -- confirm it still holds here.
    assert panel.media_display.current_list_id is None
    assert panel.media_display.current_elements == []
    assert panel.media_display.current_tag_filter == []

    # No stack -> no status-bar update.
    assert panel.status_calls == []
