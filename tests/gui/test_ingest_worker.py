import pytest

from ingest_worker import IngestWorker


class _FakeCore(object):
    """Stand-in for IngestionCore used by IngestWorker."""
    instances = []

    def __init__(self, db, config):
        self.config = config
        _FakeCore.instances.append(self)

    def ingest_file(self, source_path, target_list_id, copy_policy='soft'):
        if "bad" in source_path:
            return {"success": False, "message": "boom"}
        if "dup" in source_path:
            return {"success": False, "reason": "duplicate_skipped"}
        return {"success": True, "element_id": 1}


@pytest.mark.gui
def test_ingest_worker_tallies_and_emits_finished(qtbot, monkeypatch):
    import ingest_worker
    monkeypatch.setattr(ingest_worker, "IngestionCore", _FakeCore, raising=True)

    jobs = [("/a/ok.png", 1), ("/a/dup.png", 1), ("/a/bad.png", 1)]
    worker = IngestWorker(db=object(), config={"k": "v"}, jobs=jobs, copy_policy="soft")

    with qtbot.waitSignal(worker.ingest_finished, timeout=5000) as blocker:
        worker.start()
    assert blocker.args == [1, 1, 1]     # success, skipped, errors
    worker.wait(2000)


@pytest.mark.gui
def test_ingest_worker_passes_dict_config(qtbot, monkeypatch):
    import ingest_worker
    _FakeCore.instances = []
    monkeypatch.setattr(ingest_worker, "IngestionCore", _FakeCore, raising=True)

    worker = IngestWorker(db=object(), config={"k": "v"}, jobs=[("/a/ok.png", 1)],
                          copy_policy="soft")
    with qtbot.waitSignal(worker.ingest_finished, timeout=5000):
        worker.start()
    worker.wait(2000)
    assert _FakeCore.instances[0].config == {"k": "v"}
