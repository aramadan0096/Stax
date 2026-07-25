import os
import pytest
from watch_scanner import WatchFolderScanner
from ui.preflight_dialog import PreflightDialog


@pytest.mark.gui
def test_scan_once_emits_new_files(qtbot, tmp_path):
    (tmp_path / "a.exr").write_bytes(b"x")
    folders = [{"watch_id": 1, "path": str(tmp_path), "recipe_id": None,
                "target_list_id": 2}]
    scanner = WatchFolderScanner(folders, exts={".exr"})
    detected = scanner.scan_once()
    assert detected and detected[0][0] == 1
    assert os.path.basename(detected[0][1][0]) == "a.exr"
    # second pass: nothing new
    assert scanner.scan_once() == []


@pytest.mark.gui
def test_preflight_dialog_blocks_on_error(qtbot):
    issues = [{"level": "error", "code": "missing", "path": "/x", "message": "gone"}]
    dlg = PreflightDialog(issues)
    qtbot.addWidget(dlg)
    assert dlg.can_ingest() is False
    assert dlg.issues_table.rowCount() == 1


@pytest.mark.gui
def test_preflight_dialog_allows_on_warning_only(qtbot):
    issues = [{"level": "warning", "code": "unknown_ext", "path": "/x.abc", "message": "?"}]
    dlg = PreflightDialog(issues)
    qtbot.addWidget(dlg)
    assert dlg.can_ingest() is True
