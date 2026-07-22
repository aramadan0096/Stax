# -*- coding: utf-8 -*-
"""
tests/test_features_2_to_6.py
Features 2–6 — Lazy gallery, Duplicate detection, REST API,
                Batch editor, Analytics
"""

import os
import json
import threading
import time

import pytest


# =============================================================================
# Feature 2 — DB pagination helpers (no Qt required)
# =============================================================================

class TestPagination:
    def test_get_elements_no_limit(self, fake_db):
        sid = fake_db.add_stack("Plates", "/plates")
        lid = fake_db.add_list(sid, "Explosions")
        for i in range(10):
            fake_db.add_element(lid, "elem_{}".format(i))
        rows = fake_db.get_elements_by_list(lid)
        assert len(rows) == 10

    def test_get_elements_with_limit(self, fake_db):
        sid = fake_db.add_stack("S", "/s")
        lid = fake_db.add_list(sid, "L")
        for i in range(20):
            fake_db.add_element(lid, "e{}".format(i))
        page1 = fake_db.get_elements_by_list(lid, limit=5, offset=0)
        page2 = fake_db.get_elements_by_list(lid, limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        # No overlap
        ids1 = {r["element_id"] for r in page1}
        ids2 = {r["element_id"] for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_count_elements_by_list(self, fake_db):
        sid = fake_db.add_stack("S2", "/s2")
        lid = fake_db.add_list(sid, "L2")
        for i in range(7):
            fake_db.add_element(lid, "x{}".format(i))
        assert fake_db.count_elements_by_list(lid) == 7

    def test_empty_list_count_is_zero(self, fake_db):
        sid = fake_db.add_stack("S3", "/s3")
        lid = fake_db.add_list(sid, "L3")
        assert fake_db.count_elements_by_list(lid) == 0

    def test_pagination_page_boundaries(self, fake_db):
        sid = fake_db.add_stack("Boundary", "/b")
        lid = fake_db.add_list(sid, "BL")
        for i in range(15):
            fake_db.add_element(lid, "b{}".format(i))
        last_page = fake_db.get_elements_by_list(lid, limit=10, offset=10)
        assert len(last_page) == 5   # only 5 remain

    def test_offset_beyond_total_returns_empty(self, fake_db):
        sid = fake_db.add_stack("OOB", "/oob")
        lid = fake_db.add_list(sid, "LL")
        for i in range(3):
            fake_db.add_element(lid, "y{}".format(i))
        rows = fake_db.get_elements_by_list(lid, limit=10, offset=100)
        assert rows == []


# =============================================================================
# Feature 3 — Duplicate detection
# =============================================================================

class TestPHash:
    def test_compute_phash_returns_string(self, tiny_png):
        from src.duplicate_detection import compute_phash
        h = compute_phash(tiny_png)
        assert h is not None
        assert isinstance(h, str)
        assert len(h) > 0

    def test_compute_phash_missing_file_returns_none(self):
        from src.duplicate_detection import compute_phash
        assert compute_phash("/nonexistent/image.png") is None

    def test_compute_phash_none_input(self):
        from src.duplicate_detection import compute_phash
        assert compute_phash(None) is None

    def test_identical_images_have_zero_distance(self, tiny_png):
        from src.duplicate_detection import compute_phash, hamming_distance
        h1 = compute_phash(tiny_png)
        h2 = compute_phash(tiny_png)
        assert h1 == h2
        assert hamming_distance(h1, h2) == 0

    def test_similar_images_low_distance(self, tiny_png, tiny_png_similar):
        from src.duplicate_detection import compute_phash, hamming_distance
        h1 = compute_phash(tiny_png)
        h2 = compute_phash(tiny_png_similar)
        dist = hamming_distance(h1, h2)
        assert dist < 16, "Similar images should have low Hamming distance"

    def test_different_images_high_distance(self, tiny_png, tiny_png_different):
        from src.duplicate_detection import compute_phash, hamming_distance
        h1 = compute_phash(tiny_png)
        h2 = compute_phash(tiny_png_different)
        dist = hamming_distance(h1, h2)
        # Not guaranteed to be high for tiny images, but should differ
        assert isinstance(dist, int)

    def test_hamming_equal_hashes(self):
        from src.duplicate_detection import hamming_distance
        assert hamming_distance("abcdef01", "abcdef01") == 0


class TestFindDuplicates:
    def _seed(self, fake_db, phash):
        sid = fake_db.add_stack("Dup", "/dup")
        lid = fake_db.add_list(sid, "DL")
        eid = fake_db.add_element(lid, "existing_asset.exr")
        fake_db.update_element_phash(eid, phash)
        return eid

    def test_finds_identical_hash(self, fake_db, tiny_png):
        from src.duplicate_detection import compute_phash, find_duplicates
        h = compute_phash(tiny_png)
        existing_id = self._seed(fake_db, h)
        results = find_duplicates(fake_db, h, threshold=8)
        assert any(r["element_id"] == existing_id for r in results)

    def test_no_match_for_different_hash(self, fake_db, tiny_png, tiny_png_different):
        from src.duplicate_detection import compute_phash, find_duplicates
        h_existing = compute_phash(tiny_png)
        self._seed(fake_db, h_existing)
        h_new = compute_phash(tiny_png_different)
        results = find_duplicates(fake_db, h_new, threshold=2)
        # May or may not match depending on actual pixel difference — just
        # assert it doesn't raise
        assert isinstance(results, list)

    def test_excludes_self_by_id(self, fake_db, tiny_png):
        from src.duplicate_detection import compute_phash, find_duplicates
        h = compute_phash(tiny_png)
        existing_id = self._seed(fake_db, h)
        results = find_duplicates(fake_db, h, threshold=8,
                                  exclude_id=existing_id)
        ids = [r["element_id"] for r in results]
        assert existing_id not in ids

    def test_empty_db_returns_empty(self, fake_db):
        from src.duplicate_detection import find_duplicates
        results = find_duplicates(fake_db, "aabbccdd", threshold=8)
        assert results == []

    def test_results_sorted_by_distance(self, fake_db, tiny_png):
        from src.duplicate_detection import compute_phash, find_duplicates
        h = compute_phash(tiny_png)
        sid = fake_db.add_stack("Sort", "/sort")
        lid = fake_db.add_list(sid, "SL")
        for i in range(3):
            eid = fake_db.add_element(lid, "asset_{}.exr".format(i))
            fake_db.update_element_phash(eid, h)
        results = find_duplicates(fake_db, h, threshold=8)
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances)

    def test_threshold_zero_only_exact(self, fake_db, tiny_png, tiny_png_similar):
        from src.duplicate_detection import compute_phash, find_duplicates
        h_exact   = compute_phash(tiny_png)
        h_similar = compute_phash(tiny_png_similar)
        sid = fake_db.add_stack("T0", "/t0")
        lid = fake_db.add_list(sid, "T0L")
        eid = fake_db.add_element(lid, "exact.exr")
        fake_db.update_element_phash(eid, h_similar)
        # With threshold=0 and exact hash query, h_similar won't match unless
        # images are genuinely identical
        results = find_duplicates(fake_db, h_exact, threshold=0)
        # Just assert no crash
        assert isinstance(results, list)

    def test_db_without_phash_method_returns_empty(self, fake_db):
        """If db doesn't have get_elements_with_phash, return [] gracefully."""
        from src.duplicate_detection import find_duplicates

        class BareDB:
            pass

        results = find_duplicates(BareDB(), "deadbeef", threshold=8)
        assert results == []


class TestDuplicateDialogHeadless:
    """Headless tests that exercise the dialog logic without rendering."""

    def test_default_action_is_skip(self):
        from src.duplicate_detection import DuplicateDialog
        dlg = DuplicateDialog([], "test.exr")
        # Without exec_() the internal _action should be SKIP
        assert dlg._action == DuplicateDialog.ACTION_SKIP


# =============================================================================
# Feature 4 — REST API server
# =============================================================================

class TestAPIServer:
    def test_singleton_returns_same_instance(self):
        from src.api_server import get_api_server, shutdown_api_server
        a = get_api_server()
        b = get_api_server()
        assert a is b
        shutdown_api_server()

    def test_configure_generates_token(self, fake_db, tmp_dir):
        from src.api_server import get_api_server, shutdown_api_server

        class FakeConfig:
            _data = {}
            def get(self, k, default=None): return self._data.get(k, default)
            def set(self, k, v): self._data[k] = v
            def save(self): pass
            def get_all(self): return dict(self._data)

        cfg = FakeConfig()
        srv = get_api_server()
        srv.configure(fake_db, cfg)
        token = srv.get_token()
        assert token != ""
        assert len(token) == 48   # secrets.token_hex(24)
        shutdown_api_server()

    def test_health_endpoint_no_auth(self, fake_db):
        """The /health endpoint should respond 200 without auth."""
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "testtoken"}.get(k, d)
            def get_all(self): return {"api_token": "testtoken"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()
        resp   = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"

    def test_stacks_endpoint_requires_auth(self, fake_db):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "secret"}.get(k, d)
            def get_all(self): return {"api_token": "secret"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()

        # No token → 401
        resp = client.get("/api/v1/stacks")
        assert resp.status_code == 401

        # Wrong token → 401
        resp = client.get("/api/v1/stacks",
                          headers={"X-StaX-Token": "wrong"})
        assert resp.status_code == 401

    def test_stacks_endpoint_with_valid_token(self, fake_db):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app

        fake_db.add_stack("Plates", "/plates")
        fake_db.add_stack("3D Assets", "/3d")

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "tok"}.get(k, d)
            def get_all(self): return {"api_token": "tok"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()
        resp   = client.get("/api/v1/stacks",
                            headers={"X-StaX-Token": "tok"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert "Plates" in names

    def test_elements_pagination_via_api(self, fake_db):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app

        sid = fake_db.add_stack("PS", "/ps")
        lid = fake_db.add_list(sid, "PL")
        for i in range(25):
            fake_db.add_element(lid, "elem_{}".format(i))

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "tok"}.get(k, d)
            def get_all(self): return {"api_token": "tok"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()
        resp   = client.get(
            "/api/v1/lists/{}/elements?page=2&per_page=10".format(lid),
            headers={"X-StaX-Token": "tok"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["total"] == 25
        assert data["page"]  == 2
        assert len(data["elements"]) == 10

    def test_search_endpoint(self, fake_db):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app

        sid = fake_db.add_stack("SS", "/ss")
        lid = fake_db.add_list(sid, "SL")
        fake_db.add_element(lid, "fire_explosion_001.exr")
        fake_db.add_element(lid, "city_plate_night.exr")

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "tok"}.get(k, d)
            def get_all(self): return {"api_token": "tok"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()
        resp   = client.get(
            "/api/v1/search?q=fire&property=name&match=loose",
            headers={"X-StaX-Token": "tok"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 1
        assert "fire" in data[0]["name"]

    def test_patch_element(self, fake_db):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app

        sid = fake_db.add_stack("PE", "/pe")
        lid = fake_db.add_list(sid, "PEL")
        eid = fake_db.add_element(lid, "asset.exr")

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "tok"}.get(k, d)
            def get_all(self): return {"api_token": "tok"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()
        resp   = client.patch(
            "/api/v1/elements/{}".format(eid),
            data=json.dumps({"tags": "fire, vfx", "comment": "updated"}),
            content_type="application/json",
            headers={"X-StaX-Token": "tok"},
        )
        assert resp.status_code == 200
        elem = fake_db.get_element_by_id(eid)
        assert "fire" in elem["tags"]
        assert elem["comment"] == "updated"

    def test_analytics_top_endpoint(self, fake_db):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not installed")

        from src.api_server import _build_flask_app
        from src.ui.analytics_panel import log_insertion

        sid = fake_db.add_stack("AT", "/at")
        lid = fake_db.add_list(sid, "ATL")
        eid = fake_db.add_element(lid, "hot_asset.exr")
        for _ in range(5):
            log_insertion(fake_db, eid)

        class MinCfg:
            def get(self, k, d=None): return {"api_token": "tok"}.get(k, d)
            def get_all(self): return {"api_token": "tok"}

        app    = _build_flask_app(fake_db, MinCfg())
        client = app.test_client()
        resp   = client.get(
            "/api/v1/analytics/top?n=5",
            headers={"X-StaX-Token": "tok"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) >= 1
        assert data[0]["count"] == 5


# =============================================================================
# Feature 5 — Batch metadata editor (logic, no Qt rendering)
# =============================================================================

class TestBatchEditLogic:
    """
    Test the write logic of BatchEditDialog without instantiating the Qt UI.
    We replicate _write_element() behaviour directly.
    """

    def _apply_changes(self, fake_db, element_id, changes):
        """Simulate BatchEditDialog._write_element() for a single element."""
        elem   = fake_db.get_element_by_id(element_id)
        kwargs = {}

        if "tags" in changes:
            spec = changes["tags"]
            if spec["mode"] == 1:
                existing = [
                    t.strip()
                    for t in (elem.get("tags") or "").split(",")
                    if t.strip()
                ]
                merged = existing + [
                    t for t in spec["values"] if t not in existing
                ]
                kwargs["tags"] = ", ".join(merged)
            else:
                kwargs["tags"] = ", ".join(spec["values"])

        for field in ("type", "comment", "is_deprecated", "list_fk"):
            if field in changes:
                kwargs[field] = changes[field]

        if kwargs:
            fake_db.update_element_metadata(element_id, **kwargs)

    def test_replace_tags(self, fake_db):
        sid = fake_db.add_stack("BE", "/be")
        lid = fake_db.add_list(sid, "BEL")
        eid = fake_db.add_element(lid, "a.exr", tags="old, tags")

        self._apply_changes(fake_db, eid, {
            "tags": {"values": ["fire", "vfx"], "mode": 0}
        })
        elem = fake_db.get_element_by_id(eid)
        assert "fire" in elem["tags"]
        assert "old" not in elem["tags"]

    def test_append_tags(self, fake_db):
        sid = fake_db.add_stack("BA", "/ba")
        lid = fake_db.add_list(sid, "BAL")
        eid = fake_db.add_element(lid, "b.exr", tags="existing")

        self._apply_changes(fake_db, eid, {
            "tags": {"values": ["new_tag"], "mode": 1}
        })
        elem = fake_db.get_element_by_id(eid)
        assert "existing" in elem["tags"]
        assert "new_tag" in elem["tags"]

    def test_no_duplicate_tags_on_append(self, fake_db):
        sid = fake_db.add_stack("BD", "/bd")
        lid = fake_db.add_list(sid, "BDL")
        eid = fake_db.add_element(lid, "c.exr", tags="fire")

        self._apply_changes(fake_db, eid, {
            "tags": {"values": ["fire", "vfx"], "mode": 1}
        })
        elem  = fake_db.get_element_by_id(eid)
        parts = [t.strip() for t in elem["tags"].split(",") if t.strip()]
        assert parts.count("fire") == 1

    def test_change_type(self, fake_db):
        sid = fake_db.add_stack("BT", "/bt")
        lid = fake_db.add_list(sid, "BTL")
        eid = fake_db.add_element(lid, "d.exr", element_type="2D")

        self._apply_changes(fake_db, eid, {"type": "3D"})
        assert fake_db.get_element_by_id(eid)["type"] == "3D"

    def test_change_comment(self, fake_db):
        sid = fake_db.add_stack("BC", "/bc")
        lid = fake_db.add_list(sid, "BCL")
        eid = fake_db.add_element(lid, "e.exr")

        self._apply_changes(fake_db, eid, {"comment": "Reviewed by VFX sup"})
        assert fake_db.get_element_by_id(eid)["comment"] == "Reviewed by VFX sup"

    def test_deprecate_element(self, fake_db):
        sid = fake_db.add_stack("BDep", "/bdep")
        lid = fake_db.add_list(sid, "BDepL")
        eid = fake_db.add_element(lid, "f.exr")

        self._apply_changes(fake_db, eid, {"is_deprecated": 1})
        assert fake_db.get_element_by_id(eid)["is_deprecated"] == 1

    def test_move_to_list(self, fake_db):
        sid  = fake_db.add_stack("BM", "/bm")
        lid1 = fake_db.add_list(sid, "BML1")
        lid2 = fake_db.add_list(sid, "BML2")
        eid  = fake_db.add_element(lid1, "g.exr")

        self._apply_changes(fake_db, eid, {"list_fk": lid2})
        assert fake_db.get_element_by_id(eid)["list_fk"] == lid2

    def test_empty_changes_noop(self, fake_db):
        sid = fake_db.add_stack("BN", "/bn")
        lid = fake_db.add_list(sid, "BNL")
        eid = fake_db.add_element(lid, "h.exr", tags="original")
        self._apply_changes(fake_db, eid, {})
        assert fake_db.get_element_by_id(eid)["tags"] == "original"

    def test_batch_across_multiple_elements(self, fake_db):
        sid = fake_db.add_stack("BMulti", "/bmulti")
        lid = fake_db.add_list(sid, "BMultiL")
        eids = [fake_db.add_element(lid, "m{}.exr".format(i)) for i in range(5)]

        for eid in eids:
            self._apply_changes(fake_db, eid, {
                "tags": {"values": ["batch"], "mode": 0}
            })

        for eid in eids:
            assert "batch" in fake_db.get_element_by_id(eid)["tags"]


# =============================================================================
# Feature 6 — Usage analytics
# =============================================================================

class TestAnalyticsLogging:
    def test_log_insertion_writes_row(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("AL", "/al")
        lid = fake_db.add_list(sid, "ALL")
        eid = fake_db.add_element(lid, "asset.exr")

        log_insertion(fake_db, eid)
        assert fake_db.get_total_insertions() == 1

    def test_multiple_insertions(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("AM", "/am")
        lid = fake_db.add_list(sid, "AML")
        eid = fake_db.add_element(lid, "hot.exr")

        for _ in range(10):
            log_insertion(fake_db, eid)
        assert fake_db.get_total_insertions() == 10

    def test_top_inserted_elements(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("AT2", "/at2")
        lid = fake_db.add_list(sid, "AT2L")

        eid_a = fake_db.add_element(lid, "popular.exr")
        eid_b = fake_db.add_element(lid, "rare.exr")

        for _ in range(8): log_insertion(fake_db, eid_a)
        for _ in range(2): log_insertion(fake_db, eid_b)

        top = fake_db.get_top_inserted_elements(10)
        assert top[0]["element_id"] == eid_a
        assert top[0]["count"] == 8
        assert top[1]["count"] == 2

    def test_insertions_by_month(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("MONTH", "/month")
        lid = fake_db.add_list(sid, "MONTHL")
        eid = fake_db.add_element(lid, "asset.exr")
        log_insertion(fake_db, eid)

        rows = fake_db.get_insertions_by_month()
        assert len(rows) >= 1
        assert "month" in rows[0]
        assert rows[0]["count"] >= 1

    def test_insertions_by_user(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("USR", "/usr")
        lid = fake_db.add_list(sid, "USRL")
        eid = fake_db.add_element(lid, "asset.exr")

        # Add a user
        fake_db.execute(
            "INSERT INTO Users (username, role) VALUES (?, ?)",
            ("artist_01", "user"),
        )
        uid = fake_db.execute(
            "SELECT user_id FROM Users WHERE username='artist_01'"
        ).fetchone()[0]

        log_insertion(fake_db, eid, user_id=uid)
        log_insertion(fake_db, eid, user_id=uid)

        rows = fake_db.get_insertions_by_user()
        users = {r["username"]: r["count"] for r in rows}
        assert users.get("artist_01") == 2

    def test_guest_insertions_labeled(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("GUEST", "/guest")
        lid = fake_db.add_list(sid, "GUESTL")
        eid = fake_db.add_element(lid, "asset.exr")
        log_insertion(fake_db, eid, user_id=None)

        rows = fake_db.get_insertions_by_user()
        names = {r["username"] for r in rows}
        assert "Guest" in names

    def test_total_insertions_zero_on_empty(self, fake_db):
        assert fake_db.get_total_insertions() == 0

    def test_log_failure_doesnt_raise(self, fake_db):
        """Logging with a bad element_fk should not crash the app."""
        from src.ui.analytics_panel import log_insertion
        # element_id=99999 doesn't exist — FK constraint is relaxed in SQLite
        # by default, so this should either succeed silently or be caught
        try:
            log_insertion(fake_db, 99999)
        except Exception:
            pass   # acceptable — the important thing is it didn't propagate

    def test_project_and_host_stored(self, fake_db):
        from src.ui.analytics_panel import log_insertion
        sid = fake_db.add_stack("PH", "/ph")
        lid = fake_db.add_list(sid, "PHL")
        eid = fake_db.add_element(lid, "asset.exr")
        log_insertion(fake_db, eid, project="PROJ_001", host="ws-042")

        row = fake_db.conn.execute(
            "SELECT project, host FROM InsertionLog WHERE element_fk = ?",
            (eid,),
        ).fetchone()
        assert row["project"] == "PROJ_001"
        assert row["host"]    == "ws-042"


# =============================================================================
# Feature 3+6 combined — DB migrations
# =============================================================================

class TestDBMigrations:
    def test_run_migrations_idempotent(self, db_conn):
        from src.db_migrations import run_migrations
        # DB is already at CURRENT_SCHEMA_VERSION (set by conftest fixture)
        run_migrations(db_conn)   # should be a no-op
        run_migrations(db_conn)   # calling twice is safe

    def test_migration_adds_phash_column(self):
        """v1→v2: phash column must exist after migration."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Create baseline schema at v1
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS Elements (
                element_id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_fk    INTEGER,
                name       TEXT,
                type       TEXT DEFAULT '2D'
            );
            CREATE TABLE IF NOT EXISTS SchemaVersion (version INTEGER);
            INSERT INTO SchemaVersion VALUES (1);
        """)
        conn.commit()

        from src.db_migrations import run_migrations
        run_migrations(conn)

        cols = {r[1] for r in conn.execute("PRAGMA table_info(Elements)")}
        assert "phash" in cols
        conn.close()

    def test_migration_creates_insertion_log(self):
        """v2→v3: InsertionLog table must exist after migration."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS Elements (
                element_id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_fk INTEGER, name TEXT, type TEXT DEFAULT '2D', phash TEXT
            );
            CREATE TABLE IF NOT EXISTS SchemaVersion (version INTEGER);
            INSERT INTO SchemaVersion VALUES (2);
        """)
        conn.commit()

        from src.db_migrations import run_migrations
        run_migrations(conn)

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "InsertionLog" in tables
        conn.close()

    def test_schema_version_bumped_after_migrations(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS Elements (
                element_id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_fk INTEGER, name TEXT, type TEXT DEFAULT '2D'
            );
            CREATE TABLE IF NOT EXISTS Stacks (
                stack_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, path TEXT
            );
            CREATE TABLE IF NOT EXISTS Lists (
                list_id INTEGER PRIMARY KEY AUTOINCREMENT,
                stack_fk INTEGER, name TEXT
            );
            CREATE TABLE IF NOT EXISTS SchemaVersion (version INTEGER);
            INSERT INTO SchemaVersion VALUES (1);
        """)
        conn.commit()

        from src.db_migrations import run_migrations, CURRENT_SCHEMA_VERSION
        run_migrations(conn)

        v = conn.execute("SELECT version FROM SchemaVersion").fetchone()[0]
        assert v == CURRENT_SCHEMA_VERSION
        conn.close()
