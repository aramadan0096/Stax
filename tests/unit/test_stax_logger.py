import logging

import pytest

import stax_logger


@pytest.fixture(autouse=True)
def _reset_logger():
    # Ensure each test starts from a clean singleton + handler set.
    stax_logger._logger = None
    logging.getLogger("stax").handlers = []
    yield
    stax_logger._logger = None
    logging.getLogger("stax").handlers = []


@pytest.mark.unit
def test_logs_go_to_per_user_dir(monkeypatch, tmp_path):
    logdir = tmp_path / "stax-logs"
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(logdir))
    logdir.mkdir()
    log = stax_logger.init_logger()
    log.info("hello sp7")
    for h in logging.getLogger("stax").handlers:
        h.flush()
    logfile = logdir / "stax.log"
    assert logfile.is_file()
    assert "hello sp7" in logfile.read_text(encoding="utf-8")


@pytest.mark.unit
def test_public_api_methods_exist():
    log = stax_logger.get_logger()
    for name in ("debug", "info", "warning", "error", "critical", "exception", "separator"):
        assert callable(getattr(log, name))


@pytest.mark.unit
def test_initialized_once_does_not_duplicate_handlers(monkeypatch, tmp_path):
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(tmp_path))
    stax_logger.init_logger()
    n1 = len(logging.getLogger("stax").handlers)
    stax_logger.init_logger()   # re-init from a second entry point
    n2 = len(logging.getLogger("stax").handlers)
    assert n1 == n2  # no handler pile-up -> no second log file per process


@pytest.mark.unit
def test_uses_rotating_file_handler(monkeypatch, tmp_path):
    from logging.handlers import RotatingFileHandler
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(tmp_path))
    stax_logger.init_logger()
    handlers = logging.getLogger("stax").handlers
    assert any(isinstance(h, RotatingFileHandler) for h in handlers)


@pytest.mark.unit
def test_forwards_variadic_logging_args(monkeypatch, tmp_path):
    monkeypatch.setattr(stax_logger, "get_log_dir", lambda: str(tmp_path))
    log = stax_logger.init_logger()
    log.warning("item=%s count=%d", "shot", 7)
    for h in logging.getLogger("stax").handlers:
        h.flush()
    text = (tmp_path / "stax.log").read_text(encoding="utf-8")
    assert "item=shot count=7" in text
