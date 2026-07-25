import pytest


@pytest.mark.unit
def test_add_and_unread_count(stax_db):
    stax_db.add_notification("Ingest complete", "5 ok / 0 skipped", level="success")
    stax_db.add_notification("Watch error", "path missing", level="error")
    assert stax_db.unread_notification_count() == 2
    unread = stax_db.get_notifications(unread_only=True)
    assert unread[0]["title"] == "Watch error"   # most recent first


@pytest.mark.unit
def test_mark_read_clears_unread(stax_db):
    stax_db.add_notification("x")
    stax_db.mark_notifications_read()
    assert stax_db.unread_notification_count() == 0
    assert len(stax_db.get_notifications()) == 1
