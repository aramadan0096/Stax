# -*- coding: utf-8 -*-
"""
StaX — Database migration system
Handles incremental schema upgrades so existing databases are never broken.

Usage (already wired into DatabaseManager.__init__):
    from src.db_migrations import run_migrations
    run_migrations(conn)

Each migration is a function _migrate_vN(conn) that applies exactly one
schema change and is idempotent when called a second time.
"""

import sqlite3
import logging

log = logging.getLogger(__name__)

# Bump this constant every time you add a new _migrate_vN function below.
CURRENT_SCHEMA_VERSION = 4


# ---------------------------------------------------------------------------
# Bootstrap: ensure the SchemaVersion table exists
# ---------------------------------------------------------------------------

def _bootstrap_schema_version(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS SchemaVersion "
        "(version INTEGER NOT NULL DEFAULT 0)"
    )
    row = conn.execute("SELECT version FROM SchemaVersion LIMIT 1").fetchone()
    if row is None:
        # Fresh install — check whether Elements already exists (legacy DB)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "Elements" in tables:
            # Existing DB created before migrations — treat as v1 baseline
            conn.execute("INSERT INTO SchemaVersion VALUES (1)")
        else:
            conn.execute("INSERT INTO SchemaVersion VALUES (0)")
    conn.commit()


def _get_version(conn):
    row = conn.execute("SELECT version FROM SchemaVersion").fetchone()
    return row[0] if row else 0


def _set_version(conn, v):
    conn.execute("UPDATE SchemaVersion SET version = ?", (v,))
    conn.commit()


# ---------------------------------------------------------------------------
# Individual migrations
# ---------------------------------------------------------------------------

def _migrate_v1(conn):
    """
    v0 → v1: Baseline schema (Stacks, Lists, Elements, Playlists, Favorites,
    Users, Sessions).  Created by the original DatabaseManager.  This
    migration is a no-op — the tables are created by DatabaseManager itself;
    we just record that they exist.
    """
    pass  # tables already created by DatabaseManager._create_tables()


def _migrate_v2(conn):
    """
    v1 → v2: Add phash column to Elements for duplicate detection (Feature 3).
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(Elements)")}
    if "phash" not in cols:
        conn.execute("ALTER TABLE Elements ADD COLUMN phash TEXT")
        log.info("Migration v2: added Elements.phash")
    conn.commit()


def _migrate_v3(conn):
    """
    v2 → v3: Create InsertionLog table for usage analytics (Feature 6).
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS InsertionLog (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            element_fk  INTEGER NOT NULL,
            user_fk     INTEGER,
            inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
            project     TEXT,
            host        TEXT,
            context     TEXT,
            FOREIGN KEY (element_fk) REFERENCES Elements(element_id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inslog_element "
        "ON InsertionLog(element_fk)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inslog_date "
        "ON InsertionLog(inserted_at)"
    )
    log.info("Migration v3: created InsertionLog table")
    conn.commit()


def _migrate_v4(conn):
    """
    v3 → v4: Add sort_order columns to Stacks and Lists, and
    deprecated_reason / deprecated_at to Elements.
    """
    stacks_cols = {r[1] for r in conn.execute("PRAGMA table_info(Stacks)")}
    lists_cols  = {r[1] for r in conn.execute("PRAGMA table_info(Lists)")}
    elem_cols   = {r[1] for r in conn.execute("PRAGMA table_info(Elements)")}

    if "sort_order" not in stacks_cols:
        conn.execute(
            "ALTER TABLE Stacks ADD COLUMN sort_order INTEGER DEFAULT 0"
        )
        log.info("Migration v4: added Stacks.sort_order")

    if "sort_order" not in lists_cols:
        conn.execute(
            "ALTER TABLE Lists ADD COLUMN sort_order INTEGER DEFAULT 0"
        )
        log.info("Migration v4: added Lists.sort_order")

    if "deprecated_reason" not in elem_cols:
        conn.execute(
            "ALTER TABLE Elements ADD COLUMN deprecated_reason TEXT"
        )
        log.info("Migration v4: added Elements.deprecated_reason")

    if "deprecated_at" not in elem_cols:
        conn.execute(
            "ALTER TABLE Elements ADD COLUMN deprecated_at TEXT"
        )
        log.info("Migration v4: added Elements.deprecated_at")

    conn.commit()


# Ordered list of all migrations.  Index N corresponds to migration that
# upgrades from schema version N to N+1.
_MIGRATIONS = [
    None,           # index 0 — unused placeholder
    _migrate_v1,    # 0 → 1
    _migrate_v2,    # 1 → 2
    _migrate_v3,    # 2 → 3
    _migrate_v4,    # 3 → 4
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_migrations(conn):
    """
    Run all pending migrations against *conn* (sqlite3.Connection).
    Call this once in DatabaseManager.__init__ after _create_tables().

    The function is safe to call multiple times; already-applied migrations
    are skipped.
    """
    _bootstrap_schema_version(conn)
    current = _get_version(conn)
    log.debug("DB schema version: %d, target: %d", current, CURRENT_SCHEMA_VERSION)

    if current >= CURRENT_SCHEMA_VERSION:
        return  # nothing to do

    for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        if version < len(_MIGRATIONS) and _MIGRATIONS[version] is not None:
            log.info("Applying migration v%d …", version)
            try:
                _MIGRATIONS[version](conn)
                _set_version(conn, version)
                log.info("Migration v%d applied successfully.", version)
            except Exception as exc:
                log.error("Migration v%d FAILED: %s", version, exc)
                raise
