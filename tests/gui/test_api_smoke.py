import pytest

from api_server import _build_flask_app


def _client(stax_db, stax_config):
    stax_config.set("api_token", "test-token")
    app = _build_flask_app(stax_db, stax_config)
    app.testing = True
    return app.test_client()


@pytest.mark.gui
def test_health_endpoint_ok(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.gui
def test_analytics_top_endpoint_no_server_error(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/analytics/top?n=5",
                      headers={"X-StaX-Token": "test-token"})
    assert resp.status_code != 500
