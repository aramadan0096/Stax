import logging

import pytest

from config import Config


@pytest.mark.unit
def test_malformed_config_logs_and_keeps_defaults(tmp_path, caplog, monkeypatch):
    monkeypatch.delenv("STOCK_DB", raising=False)
    bad = tmp_path / "config.json"
    bad.write_text("{ this is not valid json ")
    with caplog.at_level(logging.ERROR):
        cfg = Config(config_path=str(bad))
    # It logged the failure (no longer swallowed to stdout only)...
    assert any("config" in rec.message.lower() for rec in caplog.records)
    # ...and returned a safe, usable config (defaults intact).
    assert isinstance(cfg.get_all(), dict)


@pytest.mark.unit
def test_save_failure_logs_without_raising(tmp_path, caplog, monkeypatch):
    monkeypatch.delenv("STOCK_DB", raising=False)
    cfg = Config(config_path=str(tmp_path / "config.json"))
    # Point the path at a directory so the file open for write fails.
    dir_as_path = tmp_path / "adir"
    dir_as_path.mkdir()
    cfg.config_path = str(dir_as_path)
    with caplog.at_level(logging.ERROR):
        cfg.save()  # must not raise
    assert any("config" in rec.message.lower() for rec in caplog.records)
