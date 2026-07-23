import pytest

from nuke_bridge import NukeBridge


class _Knob(object):
    def __init__(self):
        self.v = None
    def setValue(self, v):
        self.v = v


class _Node(dict):
    def __init__(self):
        super(_Node, self).__init__()
        self["first"] = _Knob()
        self["last"] = _Knob()
    def setName(self, n):
        pass


@pytest.mark.nuke
@pytest.mark.parametrize("rng,first,last", [
    ("-5-10", -5, 10),      # negative first frame (old split('-') broke here)
    ("1-10x2", 1, 9),       # stepped range
    ("1001-1100", 1001, 1100),
])
def test_real_mode_frame_range_parsing(mock_nuke, rng, first, last):
    node = _Node()
    mock_nuke.nodes.Read = lambda **kw: node

    bridge = NukeBridge(mock_mode=False)
    bridge.nuke = mock_nuke
    bridge.create_read_node("/plates/shot.%04d.exr", frame_range=rng, node_name="R")

    assert node["first"].v == first
    assert node["last"].v == last
