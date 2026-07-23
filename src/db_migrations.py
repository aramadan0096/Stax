# -*- coding: utf-8 -*-
"""
StaX — Database migration system (lowercase live schema)
========================================================
A small, version-tracked migration runner that upgrades an existing StaX
database in place. It targets the LIVE lowercase schema created by
DatabaseManager._create_schema (elements/lists/stacks/...), NOT the orphaned
capitalized layer.

Wired into DatabaseManager.__init__ via DatabaseManager._run_versioned_migrations().
Each _migrate_vN(conn) applies exactly one change and is idempotent.
"""

import logging

log = logging.getLogger(__name__)

# Bump this every time a new _migrate_vN is appended below.
CURRENT_SCHEMA_VERSION = 2


def _bootstrap_schema_version(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER NOT NULL DEFAULT 0)"
    )
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    conn.commit()


def _get_version(conn):
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0


def _set_version(conn, v):
    conn.execute("UPDATE schema_version SET version = ?", (v,))
    conn.commit()


# ---------------------------------------------------------------------------
# Individual migrations (lowercase schema)
# ---------------------------------------------------------------------------

def _migrate_v1(conn):
    """v0 -> v1: add elements.phash for perceptual-hash duplicate detection."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)")}
    if "phash" not in cols:
        conn.execute("ALTER TABLE elements ADD COLUMN phash TEXT")
        log.info("Migration v1: added elements.phash")
    conn.commit()


def _migrate_v2(conn):
    """v1 -> v2: create insertion_log for usage analytics."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS insertion_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            element_fk  INTEGER NOT NULL,
            user_fk     INTEGER,
            inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
            project     TEXT,
            host        TEXT,
            context     TEXT,
            FOREIGN KEY (element_fk) REFERENCES elements(element_id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inslog_element ON insertion_log(element_fk)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inslog_date ON insertion_log(inserted_at)"
    )
    log.info("Migration v2: created insertion_log table")
    conn.commit()


# Index N upgrades schema version N-1 -> N.
_MIGRATIONS = [
    None,          # index 0 — unused placeholder
    _migrate_v1,   # 0 -> 1
    _migrate_v2,   # 1 -> 2
]


def run_migrations(conn):
    """
    Apply all pending migrations against *conn* (sqlite3.Connection).
    Safe to call repeatedly; already-applied migrations are skipped.
    """
    _bootstrap_schema_version(conn)
    current = _get_version(conn)
    log.debug("DB schema version: %d, target: %d", current, CURRENT_SCHEMA_VERSION)

    if current >= CURRENT_SCHEMA_VERSION:
        return

    for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        if version < len(_MIGRATIONS) and _MIGRATIONS[version] is not None:
            log.info("Applying migration v%d ...", version)
            try:
                _MIGRATIONS[version](conn)
                _set_version(conn, version)
                log.info("Migration v%d applied.", version)
            except Exception as exc:
                log.error("Migration v%d FAILED: %s", version, exc)
                raise
