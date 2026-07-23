import logging
import sys

import pytest

from debug_manager import DebugManager


@pytest.mark.unit
def test_initialize_does_not_replace_interpreter_streams():
    """H8: DebugManager must never replace sys.stdout / sys.stderr."""
    before_out, before_err = sys.stdout, sys.stderr
    DebugManager.initialize(enabled=False)
    try:
        assert sys.stdout is before_out
        assert sys.stderr is before_err
    finally:
        DebugManager.set_enabled(True)


@pytest.mark.unit
def test_stderr_is_never_swallowed_when_debug_off(capsys):
    """H8: with debug disabled, a stderr write must still reach stderr — the
    old proxy dropped ALL writes, silencing Nuke's own console."""
    DebugManager.initialize(enabled=False)
    try:
        sys.stderr.write("real-error-from-nuke\n")
        captured = capsys.readouterr()
        assert "real-error-from-nuke" in captured.err
    finally:
        DebugManager.set_enabled(True)


@pytest.mark.unit
def test_enabled_state_maps_to_stax_logger_level():
    """H8: suppression is scoped to StaX's own logger, not global streams."""
    DebugManager.set_enabled(False)
    assert logging.getLogger("stax").level == logging.WARNING
    DebugManager.set_enabled(True)
    assert logging.getLogger("stax").level == logging.DEBUG
