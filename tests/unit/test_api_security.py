import pytest

from api_server import _build_flask_app, path_within_roots


@pytest.mark.unit
def test_path_within_roots_accepts_and_rejects(tmp_path):
    root = tmp_path / "ingest"
    root.mkdir()
    ok = root / "plate.exr"
    ok.write_bytes(b"x")
    outside = tmp_path / "secret.exr"
    outside.write_bytes(b"x")
    assert path_within_roots(str(ok), [str(root)]) is True
    assert path_within_roots(str(outside), [str(root)]) is False
    assert path_within_roots(str(ok), []) is False  # empty roots => deny


def _client(stax_db, stax_config):
    stax_config.set("api_token", "right-token")
    app = _build_flask_app(stax_db, stax_config)
    app.testing = True
    return app.test_client()


@pytest.mark.gui
def test_wrong_token_rejected(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/stacks", headers={"X-StaX-Token": "wrong"})
    assert resp.status_code == 401


@pytest.mark.gui
def test_empty_token_rejected(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/stacks", headers={"X-StaX-Token": ""})
    assert resp.status_code == 401


@pytest.mark.gui
def test_right_token_accepted(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/stacks", headers={"X-StaX-Token": "right-token"})
    assert resp.status_code == 200


@pytest.mark.gui
def test_ingest_rejects_path_outside_roots(stax_db, stax_config, tmp_path):
    outside = tmp_path / "evil.exr"
    outside.write_bytes(b"x")
    stax_config.set("api_ingest_roots", [str(tmp_path / "allowed")])
    client = _client(stax_db, stax_config)
    resp = client.post(
        "/api/v1/elements/ingest",
        headers={"X-StaX-Token": "right-token"},
        json={"filepath": str(outside), "list_id": 1},
    )
    assert resp.status_code == 403
