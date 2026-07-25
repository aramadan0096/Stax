import numpy as np
import pytest


def _seed(stax_db, n=3):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for i in range(n):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')",
                         ("e{}".format(i),))


@pytest.mark.unit
def test_store_and_get_roundtrip(stax_db):
    _seed(stax_db)
    v = np.arange(512, dtype=np.float32) / 512.0
    stax_db.store_element_embedding(1, "m1", v)
    got = stax_db.get_element_embedding(1)
    assert got is not None
    assert np.allclose(got, v)


@pytest.mark.unit
def test_get_all_embeddings_shape(stax_db):
    _seed(stax_db)
    for eid in (1, 2):
        stax_db.store_element_embedding(eid, "m1", np.ones(512, dtype=np.float32) * eid)
    ids, matrix = stax_db.get_all_embeddings("m1")
    assert set(ids) == {1, 2}
    assert matrix.shape == (2, 512)


@pytest.mark.unit
def test_missing_embedding_includes_unindexed_and_stale(stax_db):
    _seed(stax_db)
    stax_db.store_element_embedding(1, "m1", np.zeros(512, dtype=np.float32))
    stax_db.store_element_embedding(2, "OLD", np.zeros(512, dtype=np.float32))
    missing = set(stax_db.get_elements_missing_embedding("m1"))
    assert missing == {2, 3}   # 2 is stale (model 'OLD'), 3 never indexed
