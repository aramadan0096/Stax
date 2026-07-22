import pytest

from ui.batch_edit_dialog import BatchEditDialog


@pytest.mark.gui
@pytest.mark.xfail(reason="C1: batch edit calls update_element_metadata, missing until SP1",
                   strict=True)
def test_batch_edit_apply_resolves_db_method(qtbot, stax_db):
    # Seed one stack/list/element via the real DB, then attempt an apply.
    stack_id = stax_db.create_stack("S", "/tmp/S") if hasattr(stax_db, "create_stack") else None
    dlg = BatchEditDialog([1], stax_db)
    qtbot.addWidget(dlg)
    # The dialog constructs fine; the C1 failure is that its apply path calls
    # db.update_element_metadata which does not exist on the live DatabaseManager.
    assert hasattr(stax_db, "update_element_metadata")
