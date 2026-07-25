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
CURRENT_SCHEMA_VERSION = 13

# Default color-label palette (EP1). Seed order defines labels.sort_order.
DEFAULT_LABELS = [
    ("Reject",   "#E5484D", "Rejected / do not use"),
    ("Review",   "#F5D90A", "Needs review"),
    ("Approved", "#30A46C", "Approved for use"),
    ("Blue",     "#3E63DD", ""),
    ("Purple",   "#8E4EC6", ""),
    ("Orange",   "#F76B15", ""),
    ("Gray",     "#8B8D98", ""),
]


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


def _seed_default_labels(conn):
    """Insert the default label palette if the labels table is empty.

    Guarded on COUNT(*) so re-running never duplicates rows and never
    resurrects a label an admin has since deleted.
    """
    count = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO labels (name, color_hex, meaning, sort_order) "
            "VALUES (?, ?, ?, ?)",
            [
                (name, color, meaning, i)
                for i, (name, color, meaning) in enumerate(DEFAULT_LABELS)
            ],
        )
        log.info("Seeded %d default labels", len(DEFAULT_LABELS))


def _migrate_v3(conn):
    """v2 -> v3: add elements.rating/label_fk and the labels table (EP1)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)")}
    if "rating" not in cols:
        conn.execute("ALTER TABLE elements ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
        log.info("Migration v3: added elements.rating")
    if "label_fk" not in cols:
        conn.execute("ALTER TABLE elements ADD COLUMN label_fk INTEGER")
        log.info("Migration v3: added elements.label_fk")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS labels (
            label_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            color_hex  TEXT NOT NULL,
            meaning    TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    _seed_default_labels(conn)
    log.info("Migration v3: created labels table")
    conn.commit()


def _migrate_v4(conn):
    """v3 -> v4: create saved_searches table for personal saved filters (EP2)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_searches (
            saved_search_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name    TEXT NOT NULL,
            machine_name TEXT,
            name         TEXT NOT NULL,
            filter_json  TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    log.info("Migration v4: created saved_searches table")
    conn.commit()


def _migrate_v5(conn):
    """v4 -> v5: create smart_collections table for shared smart collections (EP2)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS smart_collections (
            collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            filter_json TEXT NOT NULL,
            created_by  TEXT,
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    log.info("Migration v5: created smart_collections table")
    conn.commit()


def _migrate_v6(conn):
    """v5 -> v6: create search_synonyms table for term expansion (EP2)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_synonyms (
            synonym_id INTEGER PRIMARY KEY AUTOINCREMENT,
            term       TEXT NOT NULL,
            group_key  TEXT NOT NULL
        )
        """
    )
    log.info("Migration v6: created search_synonyms table")
    conn.commit()


def _migrate_v7(conn):
    """v6 -> v7: create recent_searches table for capped per-user search history (EP2)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_searches (
            recent_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name  TEXT NOT NULL,
            query_text TEXT NOT NULL,
            ran_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    log.info("Migration v7: created recent_searches table")
    conn.commit()


def _migrate_v8(conn):
    """v7 -> v8: create metadata_fields/element_metadata/metadata_defaults
    EAV tables for stack-defined custom metadata (EP4)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_fields (
            field_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            stack_fk     INTEGER NOT NULL,
            key          TEXT NOT NULL,
            label        TEXT NOT NULL,
            field_type   TEXT NOT NULL,
            choices_json TEXT,
            required     INTEGER NOT NULL DEFAULT 0,
            sort_order   INTEGER NOT NULL DEFAULT 0,
            UNIQUE(stack_fk, key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS element_metadata (
            element_fk INTEGER NOT NULL,
            field_key  TEXT NOT NULL,
            value      TEXT,
            PRIMARY KEY (element_fk, field_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_defaults (
            default_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_type TEXT NOT NULL,
            scope_id   INTEGER NOT NULL,
            field_key  TEXT NOT NULL,
            value      TEXT,
            UNIQUE(scope_type, scope_id, field_key)
        )
        """
    )
    log.info("Migration v8: created metadata_fields/element_metadata/metadata_defaults tables")
    conn.commit()


def _migrate_v9(conn):
    """v8 -> v9: create metadata_templates table for per-stack metadata
    templates that can be applied to elements in one shot (EP4)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_templates (
            template_id INTEGER PRIMARY KEY AUTOINCREMENT,
            stack_fk    INTEGER NOT NULL,
            name        TEXT NOT NULL,
            values_json TEXT NOT NULL
        )
        """
    )
    log.info("Migration v9: created metadata_templates table")
    conn.commit()


def _migrate_v10(conn):
    """v9 -> v10: create autotag_rules table for pattern-based auto-tagging
    on ingest (EP4)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS autotag_rules (
            rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            stack_fk    INTEGER,
            pattern     TEXT NOT NULL,
            match_type  TEXT NOT NULL,
            tags        TEXT,
            field_values_json TEXT,
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    log.info("Migration v10: created autotag_rules table")
    conn.commit()


def _migrate_v11(conn):
    """v10 -> v11: create quality_rules table for element quality checks
    (required-field / naming-convention rules) (EP4)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quality_rules (
            rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            stack_fk    INTEGER,
            kind        TEXT NOT NULL,
            config_json TEXT NOT NULL
        )
        """
    )
    log.info("Migration v11: created quality_rules table")
    conn.commit()


def _migrate_v12(conn):
    """v11 -> v12: create element_relationships table for typed links
    between elements (e.g. variant_of, related) (EP4)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS element_relationships (
            rel_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_element_fk INTEGER NOT NULL,
            to_element_fk   INTEGER NOT NULL,
            rel_type        TEXT NOT NULL,
            UNIQUE(from_element_fk, to_element_fk, rel_type)
        )
        """
    )
    log.info("Migration v12: created element_relationships table")
    conn.commit()


def _migrate_v13(conn):
    """v12 -> v13: create ingest_jobs table for the durable ingestion-automation
    job ledger (EP6)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_jobs (
            job_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            kind           TEXT NOT NULL DEFAULT 'ingest',
            source_path    TEXT,
            target_list_id INTEGER,
            recipe_id      INTEGER,
            status         TEXT NOT NULL DEFAULT 'pending',
            message        TEXT,
            attempts       INTEGER NOT NULL DEFAULT 0,
            payload_json   TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    log.info("Migration v13: created ingest_jobs table")
    conn.commit()


# Index N upgrades schema version N-1 -> N.
_MIGRATIONS = [
    None,          # index 0 — unused placeholder
    _migrate_v1,   # 0 -> 1
    _migrate_v2,   # 1 -> 2
    _migrate_v3,   # 2 -> 3
    _migrate_v4,   # 3 -> 4
    _migrate_v5,   # 4 -> 5
    _migrate_v6,   # 5 -> 6
    _migrate_v7,   # 6 -> 7
    _migrate_v8,   # 7 -> 8
    _migrate_v9,   # 8 -> 9
    _migrate_v10,  # 9 -> 10
    _migrate_v11,  # 10 -> 11
    _migrate_v12,  # 11 -> 12
    _migrate_v13,  # 12 -> 13
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
