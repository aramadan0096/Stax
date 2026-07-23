import pytest


@pytest.mark.nuke
def test_advanced_search_result_wired_to_element_insert(qtbot, mock_nuke, monkeypatch, tmp_path):
    """M4 (embedded StaXPanel): show_advanced_search must connect
    AdvancedSearchDialog.result_activated to on_advanced_search_result, which
    routes to on_element_double_clicked -- the same path as a gallery
    double-click -- so double-clicking a result in the Nuke-embedded panel is
    no longer a silent no-op."""
    # StaXPanel builds its own Config() with a relative default path ('./config/
    # config.json'), which would otherwise resolve against (and could load/clobber)
    # this actual repo's real dev config. Redirect cwd to an empty tmp_path, and
    # force the DB/previews location via STOCK_DB, so no real dev data is touched.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))

    # ENV QUIRK: QMessageBox.critical/warning/information segfaults under
    # offscreen PySide2 5.15.2.1 in this environment -- stub defensively before
    # any code that could pop one runs.
    from PySide2 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)

    import nuke_launcher

    panel = nuke_launcher.StaXPanel()
    qtbot.addWidget(panel)

    assert callable(panel.on_advanced_search_result)

    # Don't actually pop/raise the real dialog window during the test.
    monkeypatch.setattr(nuke_launcher.AdvancedSearchDialog, "show", lambda self: None)
    monkeypatch.setattr(nuke_launcher.AdvancedSearchDialog, "raise_", lambda self: None)

    panel.show_advanced_search()

    dlg = panel.advanced_search_dialog
    assert isinstance(dlg, nuke_launcher.AdvancedSearchDialog)

    calls = []
    monkeypatch.setattr(panel, "on_element_double_clicked", lambda eid: calls.append(eid))

    sentinel_id = 424242
    dlg.result_activated.emit(sentinel_id)

    assert calls == [sentinel_id]
