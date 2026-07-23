import os

import pytest

from utils import appdirs  # flat import: src/ is on sys.path (conftest)


@pytest.mark.unit
def test_log_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(appdirs, "_is_windows", lambda: True)
    local = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    d = appdirs.get_log_dir()
    assert d == os.path.join(str(local), "StaX", "logs")
    assert os.path.isdir(d)
    assert os.access(d, os.W_OK)


@pytest.mark.unit
def test_log_dir_linux_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(appdirs, "_is_windows", lambda: False)
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    d = appdirs.get_log_dir()
    assert d == os.path.join(str(state), "StaX", "logs")
    assert os.path.isdir(d)


@pytest.mark.unit
def test_log_dir_linux_default_home(monkeypatch, tmp_path):
    monkeypatch.setattr(appdirs, "_is_windows", lambda: False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    d = appdirs.get_log_dir()
    assert d == os.path.join(str(tmp_path), ".local", "state", "StaX", "logs")
    assert os.path.isdir(d)


@pytest.mark.unit
def test_data_and_config_dirs_created(monkeypatch, tmp_path):
    monkeypatch.setattr(appdirs, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert os.path.isdir(appdirs.get_data_dir())
    assert os.path.isdir(appdirs.get_config_dir())
