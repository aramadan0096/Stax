# -*- coding: utf-8 -*-
"""PySide2 5.15 + QtWebEngine on Windows intermittently crash *during interpreter
finalization* (Py_FinalizeEx) even after the app ran and closed correctly. The
process then exits with code 120 (the CPython "failed to flush std streams on
exit" code) although nothing the user did was wrong. The test harness already
dodges this (tests/conftest.py and the app-launch smoke both os._exit after
verifying), but main()'s real entry point used a plain `sys.exit(app.exec_())`,
so a normal user launch could still hit the crash on close.

main() must hand its exit code to a `_hard_exit` guard that flushes stdio +
logging and then bypasses the fragile finalization on Windows.
"""

import pytest


@pytest.mark.gui
def test_hard_exit_bypasses_finalize_on_windows(monkeypatch):
    import main

    seen = {}
    flushed = []
    monkeypatch.setattr(main.sys, "platform", "win32")
    monkeypatch.setattr(main.os, "_exit", lambda code: seen.__setitem__("code", code))
    monkeypatch.setattr(main.sys.stdout, "flush", lambda: flushed.append("out"))
    monkeypatch.setattr(main.sys.stderr, "flush", lambda: flushed.append("err"))

    main._hard_exit(0)

    assert seen.get("code") == 0          # exited via os._exit, not finalization
    assert "out" in flushed and "err" in flushed   # streams flushed first


@pytest.mark.gui
def test_hard_exit_preserves_nonzero_code(monkeypatch):
    import main

    seen = {}
    monkeypatch.setattr(main.sys, "platform", "win32")
    monkeypatch.setattr(main.os, "_exit", lambda code: seen.__setitem__("code", code))
    monkeypatch.setattr(main.sys.stdout, "flush", lambda: None)
    monkeypatch.setattr(main.sys.stderr, "flush", lambda: None)

    main._hard_exit(2)

    assert seen.get("code") == 2


@pytest.mark.gui
def test_hard_exit_uses_sys_exit_off_windows(monkeypatch):
    import main

    monkeypatch.setattr(main.sys, "platform", "linux")
    # os._exit must NOT be used off-Windows (nothing to work around there)
    monkeypatch.setattr(main.os, "_exit",
                        lambda code: pytest.fail("os._exit used on non-Windows"))

    with pytest.raises(SystemExit) as ei:
        main._hard_exit(3)
    assert ei.value.code == 3
