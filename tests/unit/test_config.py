import pytest

from config import Config


@pytest.mark.unit
def test_defaults_present_and_get_all_is_a_copy(stax_config):
    all_cfg = stax_config.get_all()
    assert isinstance(all_cfg, dict)
    # mutating the returned dict must not affect the Config
    all_cfg["__scratch__"] = 1
    assert stax_config.get("__scratch__") is None


@pytest.mark.unit
def test_stock_db_env_override(tmp_path, monkeypatch):
    db = str(tmp_path / "shared.db")
    monkeypatch.setenv("STOCK_DB", db)
    cfg = Config(config_path=str(tmp_path / "config.json"))
    assert cfg.get("database_path") == db
