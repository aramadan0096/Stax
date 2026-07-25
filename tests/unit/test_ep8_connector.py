import pytest


@pytest.mark.unit
def test_base_connector_is_unavailable_by_default():
    from sync.connector import CollaborationConnector
    c = CollaborationConnector()
    assert c.is_available() is False
    assert c.capabilities() == set()


@pytest.mark.unit
def test_local_bundle_connector_registered_with_capabilities():
    from sync.connector import get_connectors, LocalBundleConnector
    instances = get_connectors()
    assert any(isinstance(c, LocalBundleConnector) for c in instances)
    local = [c for c in instances if isinstance(c, LocalBundleConnector)][0]
    assert local.capabilities() == {"push", "pull"}
    assert local.is_available() is True
    assert local.key == "local_bundle"
