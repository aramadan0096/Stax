# -*- coding: utf-8 -*-
"""EP3 Task 6: InspectorPanel — persistent editable inspector for the
selected element in the right pane.

Brief tests (kept intact): test_shows_element_fields, test_rating_edit_writes_through.

Additional tests cover the correctness requirements called out in the task
brief -- the reference implementation in the brief has real bugs (a Qt
signal feedback loop that would write a *display* operation straight back
to the DB, and can corrupt the wrong row when switching selection; stale
text left behind by clear(); labels added after construction never
appearing) that this implementation must not ship.
"""

import pytest


def _element(stax_db):
    """Insert one stack/list/element and return the *real* new element id.

    The brief's helper hardcodes ``return 1``; we capture the actual
    ``lastrowid`` instead so the helper is safe to reason about even though
    in practice (fresh temp DB, first insert) it is 1.
    """
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        cur = conn.execute(
            "INSERT INTO elements (list_fk,name,type,file_size) VALUES (1,'e','2D',2048)"
        )
        return cur.lastrowid


def _two_elements(stax_db):
    """Insert one stack/list and two distinct elements (A, B) with different
    initial rating/label_fk/tags/comment so cross-contamination is detectable.
    Returns (id_a, id_b, label_id_1, label_id_2).
    """
    stax_db.create_stack("S", "/tmp/S")
    labels = stax_db.get_labels()
    label_1, label_2 = labels[0]["label_id"], labels[1]["label_id"]
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        cur_a = conn.execute(
            "INSERT INTO elements (list_fk,name,type,file_size,rating,label_fk,tags,comment) "
            "VALUES (1,'elem_a','2D',1000,3,?,'tag_a','comment_a')",
            (label_1,),
        )
        cur_b = conn.execute(
            "INSERT INTO elements (list_fk,name,type,file_size,rating,label_fk,tags,comment) "
            "VALUES (1,'elem_b','2D',2000,1,?,'tag_b','comment_b')",
            (label_2,),
        )
        return cur_a.lastrowid, cur_b.lastrowid, label_1, label_2


@pytest.mark.gui
def test_shows_element_fields(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel
    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)
    assert "e" in ip.name_edit.text()


@pytest.mark.gui
def test_rating_edit_writes_through(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel
    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)
    ip.set_rating(4)
    assert stax_db.get_element_by_id(eid)["rating"] == 4


# ---------------------------------------------------------------------------
# Correctness requirement 1: showing an element is a pure display operation
# and must not write anything back to the DB (signal feedback loop guard).
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_show_element_does_not_write_to_db(qtbot, stax_db, monkeypatch):
    from ui.inspector_panel import InspectorPanel

    eid = _element(stax_db)
    row_before = dict(stax_db.get_element_by_id(eid))

    calls = []
    monkeypatch.setattr(
        stax_db, "update_element",
        lambda *a, **k: calls.append(("update_element", a, k)) or True,
    )
    monkeypatch.setattr(
        stax_db, "set_element_rating",
        lambda *a, **k: calls.append(("set_element_rating", a, k)),
    )
    monkeypatch.setattr(
        stax_db, "set_element_label",
        lambda *a, **k: calls.append(("set_element_label", a, k)),
    )

    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)

    assert calls == [], "show_element() must not write to the DB, wrote: {}".format(calls)
    assert dict(stax_db.get_element_by_id(eid)) == row_before


# ---------------------------------------------------------------------------
# Correctness requirement 1 (continued): switching the displayed element
# from A to B must not write A's (or B's freshly-displayed) values to the
# wrong row via the rating/label widget signals.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_switching_selection_does_not_corrupt_other_element(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel

    id_a, id_b, label_1, label_2 = _two_elements(stax_db)
    row_a_before = dict(stax_db.get_element_by_id(id_a))
    row_b_before = dict(stax_db.get_element_by_id(id_b))

    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)

    ip.show_element(id_a)
    assert ip.rating_spin.value() == 3
    ip.show_element(id_b)
    assert ip.rating_spin.value() == 1
    assert ip.name_edit.text() == "elem_b"

    # Neither row must have been mutated by the act of displaying the other.
    assert dict(stax_db.get_element_by_id(id_a)) == row_a_before
    assert dict(stax_db.get_element_by_id(id_b)) == row_b_before


# ---------------------------------------------------------------------------
# Correctness requirement 2: clear() must not leave stale text/values from
# the previously displayed element visible.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_clear_leaves_no_stale_text(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel

    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)
    assert ip.name_edit.text() != ""

    ip.clear()

    assert ip.name_edit.text() == ""
    assert ip.tags_edit.text() == ""
    assert ip.comment_edit.text() == ""
    assert ip.rating_spin.value() == 0
    for w in ip.readonly_labels.values():
        assert w.text() == ""
    assert ip.isEnabled() is False


# ---------------------------------------------------------------------------
# Correctness requirement 4: a label created after InspectorPanel
# construction (e.g. via the EP1 admin Labels settings tab) must still
# appear in the label combo -- get_labels() must not be a one-shot,
# __init__-only snapshot.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_label_added_after_construction_appears(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel

    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)

    new_id = stax_db.create_label("BrandNewLabel", "#123456", "custom")

    ip.show_element(eid)

    found = [ip.label_combo.itemText(i) for i in range(ip.label_combo.count())]
    assert "BrandNewLabel" in found
    assert ip.label_combo.findData(new_id) >= 0


# ---------------------------------------------------------------------------
# Design SS3.4: rating/label edits refresh the gallery item's badge in
# place. InspectorPanel signals this via element_updated(element_id); it
# must fire for a real rating/label commit and never for a pure
# show_element() display.
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_rating_and_label_commits_emit_element_updated(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel

    eid = _element(stax_db)
    labels = stax_db.get_labels()
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)

    received = []
    ip.element_updated.connect(received.append)

    ip.set_rating(4)
    assert received == [eid]

    ip.label_combo.setCurrentIndex(ip.label_combo.findData(labels[0]["label_id"]))
    assert received == [eid, eid]


@pytest.mark.gui
def test_show_element_never_emits_element_updated(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel

    id_a, id_b, _l1, _l2 = _two_elements(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)

    received = []
    ip.element_updated.connect(received.append)

    ip.show_element(id_a)
    ip.show_element(id_b)
    ip.clear()

    assert received == []


# ---------------------------------------------------------------------------
# Whole-branch review Finding 3: name/tags/comment commits must also emit
# element_updated -- previously only set_rating/_commit_label did, so a
# rename/retag/comment via the inspector left the gallery caption and the
# table's Name/Comment cells stale until a full reload. (The gallery/table
# refresh itself is exercised end-to-end in test_ep3_inspector_wiring.py;
# these tests cover the signal contract in isolation.)
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_name_tags_comment_commits_emit_element_updated(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel

    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)

    received = []
    ip.element_updated.connect(received.append)

    ip.name_edit.setText("renamed")
    ip._commit_name()
    assert received == [eid]

    ip.tags_edit.setText("new_tag")
    ip._commit_tags()
    assert received == [eid, eid]

    ip.comment_edit.setText("new comment")
    ip._commit_comment()
    assert received == [eid, eid, eid]

    assert stax_db.get_element_by_id(eid)["name"] == "renamed"
    assert stax_db.get_element_by_id(eid)["tags"] == "new_tag"
    assert stax_db.get_element_by_id(eid)["comment"] == "new comment"


@pytest.mark.gui
def test_failed_commit_does_not_emit_element_updated(qtbot, stax_db, monkeypatch):
    from ui.inspector_panel import InspectorPanel

    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)

    monkeypatch.setattr(
        stax_db, "update_element",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    received = []
    ip.element_updated.connect(received.append)

    ip.name_edit.setText("renamed")
    ip._commit_name()  # must not raise

    assert received == []
