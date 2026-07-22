# -*- coding: utf-8 -*-
"""
tests/conftest.py — shared fixtures for the StaX feature test suite.

Run the entire suite from the repo root:
    pytest tests/ -v

Run a single feature's tests:
    pytest tests/test_feature1_preview_worker.py -v

Requirements:
    pip install pytest pytest-mock pillow
    (imagehash optional — tests degrade gracefully without it)
"""

import os
import sys
import sqlite3
import tempfile
import shutil

import pytest

# Ensure src/ is importable whether pytest is run from repo root or tests/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Temporary directory
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path):
    """A temporary directory that is cleaned up after each test."""
    return str(tmp_path)


# ---------------------------------------------------------------------------
# In-memory SQLite database with full StaX schema + migrations
# ---------------------------------------------------------------------------

_BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS Stacks (
    stack_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    path       TEXT UNIQUE NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS Lists (
    list_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    stack_fk   INTEGER NOT NULL,
    name       TEXT NOT NULL,
    parent_list_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY (stack_fk) REFERENCES Stacks(stack_id)
);

CREATE TABLE IF NOT EXISTS Elements (
    element_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    list_fk        INTEGER NOT NULL,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL DEFAULT '2D',
    filepath_soft  TEXT,
    filepath_hard  TEXT,
    is_hard_copy   BOOLEAN NOT NULL DEFAULT 0,
    frame_range    TEXT,
    format         TEXT,
    comment        TEXT,
    tags           TEXT,
    preview_path   TEXT,
    is_deprecated  BOOLEAN DEFAULT 0,
    deprecated_reason TEXT,
    deprecated_at  TEXT,
    phash          TEXT,
    FOREIGN KEY (list_fk) REFERENCES Lists(list_id)
);

CREATE TABLE IF NOT EXISTS Playlists (
    playlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS PlaylistElements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_fk INTEGER NOT NULL,
    element_fk  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS Favorites (
    favorite_id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_fk  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS Users (
    user_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    role     TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS Sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_fk     INTEGER NOT NULL,
    machine     TEXT,
    started_at  TEXT DEFAULT (datetime('now')),
    ended_at    TEXT
);

CREATE TABLE IF NOT EXISTS InsertionLog (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    element_fk  INTEGER NOT NULL,
    user_fk     INTEGER,
    inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
    project     TEXT,
    host        TEXT,
    context     TEXT,
    FOREIGN KEY (element_fk) REFERENCES Elements(element_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inslog_element ON InsertionLog(element_fk);
CREATE INDEX IF NOT EXISTS idx_inslog_date    ON InsertionLog(inserted_at);

CREATE TABLE IF NOT EXISTS SchemaVersion (version INTEGER NOT NULL DEFAULT 4);
INSERT INTO SchemaVersion VALUES (4);
"""


@pytest.fixture
def db_conn():
    """
    An in-memory sqlite3.Connection with the full StaX schema applied.
    Returned as a raw connection so tests can call .execute() directly.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_BASELINE_SCHEMA)
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Minimal DatabaseManager stub (no file I/O, wraps the in-memory connection)
# ---------------------------------------------------------------------------

class FakeDB:
    """
    A thin stand-in for DatabaseManager that uses an in-memory SQLite
    connection.  Only the methods called by the features under test are
    implemented; others raise NotImplementedError so tests fail clearly.
    """

    def __init__(self, conn):
        self.conn  = conn
        self._lock = __import__('threading').Lock()

    def execute(self, sql, params=()):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    # --- Stacks / Lists / Elements ---

    def add_stack(self, name, path):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO Stacks (name, path) VALUES (?, ?)", (name, path)
            )
            self.conn.commit()
            return cur.lastrowid

    def get_all_stacks(self):
        with self._lock:
            return [dict(r) for r in
                    self.conn.execute("SELECT * FROM Stacks").fetchall()]

    def add_list(self, stack_fk, name, parent_list_id=None):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO Lists (stack_fk, name, parent_list_id) "
                "VALUES (?, ?, ?)",
                (stack_fk, name, parent_list_id),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_lists_by_stack(self, stack_id):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM Lists WHERE stack_fk = ?", (stack_id,)
            ).fetchall()]

    def add_element(self, list_fk, name, element_type='2D', filepath=None,
                    frame_range=None, fmt=None, comment=None, tags=None):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO Elements "
                "(list_fk, name, type, filepath_soft, frame_range, "
                " format, comment, tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (list_fk, name, element_type, filepath,
                 frame_range, fmt, comment, tags),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_element_by_id(self, element_id):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM Elements WHERE element_id = ?", (element_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_elements_by_list(self, list_id, limit=None, offset=0):
        with self._lock:
            if limit is not None:
                rows = self.conn.execute(
                    "SELECT * FROM Elements WHERE list_fk = ? "
                    "ORDER BY element_id LIMIT ? OFFSET ?",
                    (list_id, limit, offset),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM Elements WHERE list_fk = ? "
                    "ORDER BY element_id",
                    (list_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def count_elements_by_list(self, list_id):
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM Elements WHERE list_fk = ?", (list_id,)
            ).fetchone()
            return row[0]

    def update_element_phash(self, element_id, phash):
        with self._lock:
            self.conn.execute(
                "UPDATE Elements SET phash = ? WHERE element_id = ?",
                (phash, element_id),
            )
            self.conn.commit()

    def get_elements_with_phash(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT element_id, name, list_fk, format, phash, preview_path "
                "FROM Elements WHERE phash IS NOT NULL AND phash != ''"
            ).fetchall()]

    def update_element_metadata(self, element_id, **kwargs):
        allowed = {"name", "tags", "comment", "type",
                   "is_deprecated", "list_fk", "deprecated_reason"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        cols   = ", ".join("{} = ?".format(k) for k in updates)
        values = list(updates.values()) + [element_id]
        with self._lock:
            self.conn.execute(
                "UPDATE Elements SET {} WHERE element_id = ?".format(cols),
                values,
            )
            self.conn.commit()

    def get_top_inserted_elements(self, n=20):
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT e.element_id, e.name,
                       l.name AS list_name,
                       e.format, e.type,
                       COUNT(i.log_id) AS count
                FROM InsertionLog i
                JOIN Elements e ON e.element_id = i.element_fk
                LEFT JOIN Lists l ON l.list_id = e.list_fk
                GROUP BY i.element_fk
                ORDER BY count DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_insertions_by_month(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT strftime('%Y-%m', inserted_at) AS month, "
                "COUNT(*) AS count "
                "FROM InsertionLog GROUP BY month ORDER BY month"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_insertions_by_user(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT COALESCE(u.username, 'Guest') AS username, "
                "COUNT(i.log_id) AS count, MAX(i.inserted_at) AS last_active "
                "FROM InsertionLog i "
                "LEFT JOIN Users u ON u.user_id = i.user_fk "
                "GROUP BY i.user_fk ORDER BY count DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_total_insertions(self):
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM InsertionLog"
            ).fetchone()
            return row[0]

    def search_elements(self, query, prop="name", match="loose"):
        allowed = {"name", "format", "type", "comment", "tags"}
        if prop not in allowed:
            prop = "name"
        with self._lock:
            if match == "strict":
                rows = self.conn.execute(
                    "SELECT * FROM Elements WHERE {} = ?".format(prop),
                    (query,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM Elements WHERE {} LIKE ?".format(prop),
                    ("%{}%".format(query),),
                ).fetchall()
            return [dict(r) for r in rows]


@pytest.fixture
def fake_db(db_conn):
    """A FakeDB instance wrapping the in-memory connection."""
    return FakeDB(db_conn)


# ---------------------------------------------------------------------------
# Minimal PIL image factory
# ---------------------------------------------------------------------------

@pytest.fixture
def tiny_png(tmp_dir):
    """
    Create a tiny 64×64 PNG test image and return its path.
    Used by thumbnail / pHash tests.
    """
    try:
        from PIL import Image
        img_path = os.path.join(tmp_dir, "test_frame.png")
        img = Image.new("RGB", (64, 64), color=(128, 64, 32))
        img.save(img_path)
        return img_path
    except ImportError:
        pytest.skip("Pillow not installed")


@pytest.fixture
def tiny_png_similar(tmp_dir):
    """A second PNG very similar to tiny_png (slight brightness shift)."""
    try:
        from PIL import Image
        img_path = os.path.join(tmp_dir, "test_frame_similar.png")
        img = Image.new("RGB", (64, 64), color=(130, 66, 34))
        img.save(img_path)
        return img_path
    except ImportError:
        pytest.skip("Pillow not installed")


@pytest.fixture
def tiny_png_different(tmp_dir):
    """A PNG visually unrelated to tiny_png."""
    try:
        from PIL import Image
        img_path = os.path.join(tmp_dir, "test_frame_different.png")
        img = Image.new("RGB", (64, 64), color=(0, 200, 255))
        img.save(img_path)
        return img_path
    except ImportError:
        pytest.skip("Pillow not installed")
