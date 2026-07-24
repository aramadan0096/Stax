import pytest


@pytest.mark.unit
def test_create_list_shared(stax_db):
    cid = stax_db.create_smart_collection("Un-reviewed plates",
                                          {"types": ["2D"], "rating_min": 0}, created_by="alice")
    cols = stax_db.get_smart_collections()
    assert cols[0]["name"] == "Un-reviewed plates"
    assert cols[0]["filter"]["types"] == ["2D"]
    assert cols[0]["collection_id"] == cid


@pytest.mark.unit
def test_update_and_delete(stax_db):
    cid = stax_db.create_smart_collection("A", {"text": "x"})
    stax_db.update_smart_collection(cid, name="B")
    assert stax_db.get_smart_collections()[0]["name"] == "B"
    stax_db.delete_smart_collection(cid)
    assert stax_db.get_smart_collections() == []
