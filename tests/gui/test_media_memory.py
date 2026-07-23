import pytest
from PySide2 import QtGui, QtWidgets

from ui.media_display_widget import MediaDisplayWidget
from src.icon_loader import IconLoader, get_icon
from nuke_bridge import NukeBridge


def _make_widget(qtbot, stax_db, stax_config):
    mw = QtWidgets.QMainWindow()
    mw.is_admin = False
    qtbot.addWidget(mw)
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True), main_window=mw)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_gif_movies_cleared_on_refresh(qtbot, stax_db, stax_config):
    w = _make_widget(qtbot, stax_db, stax_config)
    movie = QtGui.QMovie()
    movie.frameChanged.connect(lambda n: None)
    w.gif_movies[123] = movie
    w._update_views_with_elements([])  # a refresh with no elements
    assert w.gif_movies == {}  # cleared + disconnected


@pytest.mark.gui
def test_icon_cache_is_bounded_and_caches_misses():
    loader = IconLoader()
    loader.clear_cache()
    bound = IconLoader._MAX_CACHE_ENTRIES
    # Request more distinct (name,size) keys than the bound.
    for size in range(1, bound + 60):
        get_icon("add", size=size)
    assert len(IconLoader._icon_cache) <= bound

    # A missing icon is cached (no repeated disk stat / no unbounded growth).
    loader.clear_cache()
    get_icon("definitely_not_a_real_icon_name", size=24)
    assert any("definitely_not_a_real_icon_name" in k for k in IconLoader._icon_cache)


@pytest.mark.gui
def test_size_slider_is_debounced(qtbot, stax_db, stax_config, monkeypatch):
    w = _make_widget(qtbot, stax_db, stax_config)
    calls = []
    monkeypatch.setattr(w, "_apply_pending_size", lambda: calls.append(1), raising=False)
    w.current_elements = [{"element_id": 1, "name": "x", "type": "2D"}]

    w.on_size_changed(256)
    assert w._size_debounce.isActive()  # deferred, not run inline
    assert calls == []  # not called synchronously

    qtbot.waitUntil(lambda: calls == [1], timeout=2000)  # fires exactly once
