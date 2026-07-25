import pytest


@pytest.mark.unit
def test_create_and_list(stax_db):
    wid = stax_db.create_watch_folder("/inbox", target_list_id=1, interval_sec=15)
    rows = stax_db.get_watch_folders()
    assert rows[0]["path"] == "/inbox"
    assert rows[0]["interval_sec"] == 15
    assert rows[0]["watch_id"] == wid


@pytest.mark.unit
def test_enabled_only_filter_and_update(stax_db):
    a = stax_db.create_watch_folder("/a", enabled=True)
    b = stax_db.create_watch_folder("/b", enabled=True)
    stax_db.update_watch_folder(b, enabled=0)
    enabled = stax_db.get_watch_folders(enabled_only=True)
    assert [r["path"] for r in enabled] == ["/a"]


@pytest.mark.unit
def test_delete(stax_db):
    wid = stax_db.create_watch_folder("/x")
    stax_db.delete_watch_folder(wid)
    assert stax_db.get_watch_folders() == []
