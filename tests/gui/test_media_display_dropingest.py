import pytest


@pytest.mark.gui
def test_drop_ingest_passes_dict_config_and_default_copy_policy(
        qtbot, stax_db, stax_config, monkeypatch):
    import ingest_worker

    captured = {}

    class _SpyWorker(ingest_worker.IngestWorker):
        def __init__(self, db, config, jobs, copy_policy="soft", parent=None):
            captured["config"] = config
            captured["copy_policy"] = copy_policy
            super(_SpyWorker, self).__init__(db, config, jobs, copy_policy, parent)

        def start(self):
            # don't actually run a thread in the test
            self.ingest_finished.emit(0, 0, 0)

    monkeypatch.setattr(ingest_worker, "IngestWorker", _SpyWorker, raising=True)

    from ui.media_display_widget import MediaDisplayWidget
    from nuke_bridge import NukeBridge

    stax_config.set("default_copy_policy", "hard")
    widget = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(widget)
    widget.current_list_id = 1

    # IngestProgressDialog.exec_ would block; stub it.
    monkeypatch.setattr("ui.dialogs.IngestProgressDialog.exec_", lambda self: 0)

    widget.ingest_dropped_files(["/some/file.png"])

    assert isinstance(captured["config"], dict)          # H7: dict, not Config
    assert captured["copy_policy"] == "hard"             # H7: default_copy_policy
    assert getattr(widget, "_ingest_worker", None) is not None  # H7: member ref
