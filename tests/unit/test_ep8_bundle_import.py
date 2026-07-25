import pytest


def _seed_source(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'SRC')")
        conn.execute("INSERT INTO elements (list_fk, name, type, comment) "
                     "VALUES (1, 'plate_a', '2D', 'v1')")
        conn.commit()
    return 1


def _make_target_list(stax_db):
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'DST')")
        conn.commit()
    return 2


@pytest.mark.unit
def test_roundtrip_add_then_skip(stax_db, tmp_path):
    src = _seed_source(stax_db)
    dst = _make_target_list(stax_db)
    from sync.metadata_bundle import export_list_bundle, import_bundle
    bundle = str(tmp_path / "b.staxbundle")
    export_list_bundle(stax_db, src, bundle)

    first = import_bundle(stax_db, bundle, dst)
    assert first == {"added": 1, "updated": 0, "skipped": 0}
    # re-import same bundle -> identical timestamps -> skip
    second = import_bundle(stax_db, bundle, dst)
    assert second == {"added": 0, "updated": 0, "skipped": 1}


@pytest.mark.unit
def test_newer_bundle_updates(stax_db, tmp_path):
    src = _seed_source(stax_db)
    dst = _make_target_list(stax_db)
    from sync.metadata_bundle import export_list_bundle, import_bundle
    # bring plate_a into DST first
    export_list_bundle(stax_db, src, str(tmp_path / "b1.staxbundle"))
    import_bundle(stax_db, str(tmp_path / "b1.staxbundle"), dst)
    # edit the source (bumps updated_at) and re-export a newer bundle
    import time; time.sleep(1.1)
    src_el = [e for e in stax_db.get_elements_by_list(src) if e["name"] == "plate_a"][0]
    stax_db.update_element(src_el["element_id"], comment="v2")
    export_list_bundle(stax_db, src, str(tmp_path / "b2.staxbundle"))
    res = import_bundle(stax_db, str(tmp_path / "b2.staxbundle"), dst)
    assert res == {"added": 0, "updated": 1, "skipped": 0}
    dst_el = [e for e in stax_db.get_elements_by_list(dst) if e["name"] == "plate_a"][0]
    assert dst_el["comment"] == "v2"
