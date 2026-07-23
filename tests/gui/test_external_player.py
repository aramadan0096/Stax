import pytest
from PySide2 import QtWidgets

from video_player_widget import VideoPlayerWidget
from config import Config


def _make_player(qtbot, stax_db, stax_config):
    w = VideoPlayerWidget(stax_db, stax_config)
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_get_config_player_reads_from_config(qtbot, stax_db, stax_config, monkeypatch):
    stax_config.set("external_player", "/usr/bin/mpv")
    monkeypatch.setattr(QtWidgets.QFileDialog, "exec_", lambda self: 0)
    monkeypatch.setattr(QtWidgets.QFileDialog, "selectedFiles", lambda self: [])
    w = _make_player(qtbot, stax_db, stax_config)
    assert w._get_config_player() == "/usr/bin/mpv"  # read path un-gated


@pytest.mark.gui
def test_get_config_player_persists_choice(qtbot, stax_db, stax_config, monkeypatch, tmp_path):
    picked = str(tmp_path / "player.exe")
    open(picked, "w").close()

    # Neutralise the file dialog: pretend the user accepted and picked `picked`.
    monkeypatch.setattr(QtWidgets.QFileDialog, "exec_", lambda self: 1)
    monkeypatch.setattr(QtWidgets.QFileDialog, "selectedFiles", lambda self: [picked])

    w = _make_player(qtbot, stax_db, stax_config)
    assert w._get_config_player() == picked
    assert stax_config.get("external_player") == picked

    # Persisted to disk: a fresh Config on the same path sees it.
    reloaded = Config(config_path=stax_config.config_path)
    assert reloaded.get("external_player") == picked
