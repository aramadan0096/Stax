import pytest
from PySide2 import QtGui

from geometry_viewer import GeometryViewerWidget


@pytest.mark.gui
def test_geometry_viewer_close_event_calls_shutdown(qtbot, tmp_path, monkeypatch):
    previews = tmp_path / "previews"
    previews.mkdir()

    widget = GeometryViewerWidget(str(tmp_path), previews_root=str(previews))
    qtbot.addWidget(widget)

    calls = []
    monkeypatch.setattr(widget, "shutdown", lambda: calls.append(1), raising=False)

    widget.closeEvent(QtGui.QCloseEvent())

    assert calls == [1]
