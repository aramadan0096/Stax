import os
import sys

import pytest

_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import stax_cli


@pytest.mark.unit
def test_base_builds_https_url():
    assert stax_cli._base("host", 443, "https") == "https://host:443/api/v1"


@pytest.mark.unit
def test_base_defaults_to_http():
    assert stax_cli._base("127.0.0.1", 17171) == "http://127.0.0.1:17171/api/v1"


@pytest.mark.unit
def test_env_token_wins_over_argv(monkeypatch):
    monkeypatch.setenv("STAX_API_TOKEN", "from-env")
    assert stax_cli.resolve_token("from-argv") == "from-env"


@pytest.mark.unit
def test_argv_token_used_when_env_absent(monkeypatch):
    monkeypatch.delenv("STAX_API_TOKEN", raising=False)
    assert stax_cli.resolve_token("from-argv") == "from-argv"
