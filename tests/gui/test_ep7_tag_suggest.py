import pytest
from ui.tag_suggest_dialog import TagSuggestDialog


@pytest.mark.gui
def test_only_checked_tags_are_returned(qtbot):
    dlg = TagSuggestDialog([("fire", 0.9), ("smoke", 0.7), ("city", 0.3)])
    qtbot.addWidget(dlg)
    dlg.set_checked("fire", True)
    dlg.set_checked("smoke", False)
    dlg.set_checked("city", False)
    assert dlg.accepted_tags() == ["fire"]


@pytest.mark.gui
def test_merge_tags_dedupes(qtbot):
    assert TagSuggestDialog.merge_tags("fire, city", ["fire", "smoke"]) == "fire, city, smoke"
