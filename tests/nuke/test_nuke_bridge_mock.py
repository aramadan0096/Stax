import pytest

from nuke_bridge import NukeBridge


@pytest.mark.nuke
def test_mock_bridge_defaults_to_mock_mode():
    bridge = NukeBridge(mock_mode=True)
    assert bridge.mock_mode is True


@pytest.mark.nuke
def test_mock_create_read_node_returns_dict():
    bridge = NukeBridge(mock_mode=True)
    result = bridge.create_read_node("/tmp/plate.%04d.exr", frame_range="1-10")
    assert isinstance(result, dict)
