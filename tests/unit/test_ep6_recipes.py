import pytest


@pytest.mark.unit
def test_create_and_parse_values(stax_db):
    rid = stax_db.create_ingest_recipe(
        "Plates", {"copy_policy": "hard", "duplicate_policy": "skip", "tags": "plate"})
    recipes = stax_db.get_ingest_recipes()
    assert recipes[0]["name"] == "Plates"
    assert recipes[0]["values"]["copy_policy"] == "hard"
    assert recipes[0]["recipe_id"] == rid


@pytest.mark.unit
def test_update_and_delete(stax_db):
    rid = stax_db.create_ingest_recipe("A", {"copy_policy": "soft"})
    stax_db.update_ingest_recipe(rid, name="B", values={"copy_policy": "hard"})
    r = stax_db.get_ingest_recipes()[0]
    assert r["name"] == "B" and r["values"]["copy_policy"] == "hard"
    stax_db.delete_ingest_recipe(rid)
    assert stax_db.get_ingest_recipes() == []
