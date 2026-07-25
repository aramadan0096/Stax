import json
import zipfile
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type, comment, tags) "
                     "VALUES (1, 'plate_a', '2D', 'hi', 'fire,city')")
        conn.commit()
    return 1


@pytest.mark.unit
def test_export_writes_zip_with_manifest_and_elements(stax_db, tmp_path):
    lid = _seed(stax_db)
    from sync.metadata_bundle import export_list_bundle, read_manifest
    out = str(tmp_path / "list.staxbundle")
    path = export_list_bundle(stax_db, lid, out, source_site="siteA")
    assert path == out
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "elements.json" in names
        elements = json.loads(zf.read("elements.json").decode("utf-8"))
    assert elements[0]["name"] == "plate_a"
    assert elements[0]["tags"] == "fire,city"
    manifest = read_manifest(out)
    assert manifest["source_site"] == "siteA"
    assert manifest["element_count"] == 1
