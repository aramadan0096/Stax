import os
import pytest

from geometry_viewer import _is_within, GeometryViewerServer


@pytest.mark.unit
def test_is_within_accepts_and_rejects(tmp_path):
    base = tmp_path / "previews"
    base.mkdir()
    assert _is_within(str(base), str(base / "a" / "m.glb")) is True
    assert _is_within(str(base), str(tmp_path / "outside.glb")) is False
    assert _is_within(str(base), os.path.join(str(base), "..", "x.glb")) is False


@pytest.mark.unit
def test_register_model_accepts_inside_previews(tmp_path):
    previews = tmp_path / "previews"
    previews.mkdir()
    glb = previews / "asset.glb"
    glb.write_bytes(b"glTF")
    srv = GeometryViewerServer.__new__(GeometryViewerServer)
    srv._init_registry(str(tmp_path), str(previews))
    assert srv.register_model(str(glb)) == os.path.realpath(str(glb))
    assert os.path.realpath(str(glb)) in srv._allowed


@pytest.mark.unit
def test_register_model_rejects_outside_previews(tmp_path):
    previews = tmp_path / "previews"
    previews.mkdir()
    outside = tmp_path / "secret.glb"
    outside.write_bytes(b"glTF")
    srv = GeometryViewerServer.__new__(GeometryViewerServer)
    srv._init_registry(str(tmp_path), str(previews))
    assert srv.register_model(str(outside)) is None


@pytest.mark.unit
def test_register_model_rejects_nonexistent(tmp_path):
    previews = tmp_path / "previews"
    previews.mkdir()
    srv = GeometryViewerServer.__new__(GeometryViewerServer)
    srv._init_registry(str(tmp_path), str(previews))
    assert srv.register_model(str(previews / "missing.glb")) is None
