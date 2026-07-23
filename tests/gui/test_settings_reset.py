import pytest
from PySide2 import QtCore, QtWidgets

from ui.settings_panel import SettingsPanel


@pytest.mark.gui
def test_reset_does_not_emit_layout_warning(qtbot, stax_config, stax_db, monkeypatch):
    panel = SettingsPanel(stax_config, stax_db)
    qtbot.addWidget(panel)

    # Confirm the reset dialog + suppress the info popup.
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))

    messages = []
    QtCore.qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
    try:
        panel.reset_settings()
    finally:
        QtCore.qInstallMessageHandler(None)

    assert not any("already has a layout" in m for m in messages)
    assert panel.layout() is not None
