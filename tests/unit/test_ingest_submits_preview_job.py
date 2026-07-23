import os
import pytest

import ingestion_core
from ingestion_core import IngestionCore


class _FakeQueue(object):
    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)

    def isRunning(self):
        return True


class _FakeDB(object):
    def __init__(self, previews_dir):
        self._pd = previews_dir
        self.phash_calls = []
        self._next = 42

    def get_list_by_id(self, list_id):
        return {"id": list_id, "name": "L", "stack_fk": 1}

    def get_stack_by_id(self, stack_id):
        return {"id": stack_id, "name": "S", "path": self._pd}

    def create_element(self, list_id, name, element_type, **kwargs):
        self.created = dict(kwargs)
        self.created["name"] = name
        return self._next

    def log_ingestion(self, **kwargs):
        pass

    def get_elements_with_phash(self):
        return []

    def update_element_phash(self, element_id, phash):
        self.phash_calls.append((element_id, phash))


@pytest.mark.unit
def test_ingest_submits_one_preview_job_and_stores_paths(tmp_path, monkeypatch, tiny_png):
    queue = _FakeQueue()
    monkeypatch.setattr(ingestion_core, "get_preview_queue", lambda: queue, raising=False)
    # Make sure NO synchronous ffmpeg/PIL decode happens.
    monkeypatch.setattr(ingestion_core, "get_ffmpeg",
                        lambda: (_ for _ in ()).throw(AssertionError("sync decode!")),
                        raising=False)

    db = _FakeDB(str(tmp_path))
    cfg = {"previews_path": str(tmp_path / "prev"),
           "generate_previews": True, "dedup_enabled": True}
    core = IngestionCore(db, cfg)

    result = core.ingest_file(tiny_png, target_list_id=1, copy_policy="soft")

    assert result["success"] is True
    assert len(queue.jobs) == 1
    job = queue.jobs[0]
    assert job.element_id == 42
    assert job.thumb_path == db.created.get("preview_path")
    assert job.thumb_path and job.thumb_path.endswith(".png")
    # phash stored after insert
    assert db.phash_calls and db.phash_calls[0][0] == 42


@pytest.mark.unit
def test_find_duplicates_not_called_when_skip_duplicates_disabled(tmp_path, monkeypatch, tiny_png):
    """M1: find_duplicates is an O(n) scan over every existing element's
    phash. When dedup_skip_duplicates is off (the default), its result is
    discarded -- so it must not be called at all. phash must still be
    computed and stored."""
    queue = _FakeQueue()
    monkeypatch.setattr(ingestion_core, "get_preview_queue", lambda: queue, raising=False)
    monkeypatch.setattr(ingestion_core, "get_ffmpeg",
                        lambda: (_ for _ in ()).throw(AssertionError("sync decode!")),
                        raising=False)

    calls = []
    monkeypatch.setattr(ingestion_core, "find_duplicates",
                        lambda *a, **k: calls.append((a, k)) or [],
                        raising=False)

    db = _FakeDB(str(tmp_path))
    cfg = {"previews_path": str(tmp_path / "prev"),
           "generate_previews": True, "dedup_enabled": True,
           "dedup_skip_duplicates": False}
    core = IngestionCore(db, cfg)

    result = core.ingest_file(tiny_png, target_list_id=1, copy_policy="soft")

    assert result["success"] is True
    assert calls == []  # find_duplicates NOT called -- result would be discarded
    assert db.phash_calls and db.phash_calls[0][0] == 42  # phash still stored


@pytest.mark.unit
def test_find_duplicates_called_when_skip_duplicates_enabled(tmp_path, monkeypatch, tiny_png):
    """M1 (preserve behavior): when dedup_skip_duplicates=True, the scan
    must still run so duplicates are actually skipped."""
    queue = _FakeQueue()
    monkeypatch.setattr(ingestion_core, "get_preview_queue", lambda: queue, raising=False)
    monkeypatch.setattr(ingestion_core, "get_ffmpeg",
                        lambda: (_ for _ in ()).throw(AssertionError("sync decode!")),
                        raising=False)

    calls = []
    monkeypatch.setattr(ingestion_core, "find_duplicates",
                        lambda *a, **k: calls.append((a, k)) or [],
                        raising=False)

    db = _FakeDB(str(tmp_path))
    cfg = {"previews_path": str(tmp_path / "prev"),
           "generate_previews": True, "dedup_enabled": True,
           "dedup_skip_duplicates": True}
    core = IngestionCore(db, cfg)

    result = core.ingest_file(tiny_png, target_list_id=1, copy_policy="soft")

    assert result["success"] is True
    assert len(calls) == 1  # find_duplicates WAS called
    assert db.phash_calls and db.phash_calls[0][0] == 42  # phash still stored
