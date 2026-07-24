import pytest

from ui.multi_select_action_tray import MultiSelectActionTray


class _FakeDB:
    def __init__(self):
        self.rated = None
        self.labeled = None
    def bulk_set_rating(self, ids, rating):
        self.rated = (list(ids), rating); return len(ids)
    def bulk_set_label(self, ids, label_fk):
        self.labeled = (list(ids), label_fk); return len(ids)
    def get_labels(self):
        return [{"label_id": 1, "name": "Reject", "color_hex": "#E5484D", "meaning": ""}]


class _FakeMain:
    def __init__(self, admin=True):
        self.is_admin = admin
    def check_admin_permission(self):
        return self.is_admin


@pytest.mark.gui
def test_hidden_below_two_selected(qtbot):
    tray = MultiSelectActionTray(_FakeDB(), _FakeMain())
    qtbot.addWidget(tray)
    tray.set_selection([1])
    assert tray.isHidden() is True
    tray.set_selection([1, 2, 3])
    assert tray.isHidden() is False
    assert "3" in tray.count_label.text()


@pytest.mark.gui
def test_rate_button_calls_bulk_rating(qtbot):
    db = _FakeDB()
    tray = MultiSelectActionTray(db, _FakeMain())
    qtbot.addWidget(tray)
    tray.set_selection([4, 5])
    tray.apply_rating(3)          # invoked by the star popup
    assert db.rated == ([4, 5], 3)


@pytest.mark.gui
def test_delete_gated_for_non_admin(qtbot):
    tray = MultiSelectActionTray(_FakeDB(), _FakeMain(admin=False))
    qtbot.addWidget(tray)
    tray.set_selection([1, 2])
    assert tray.delete_button.isEnabled() is False
