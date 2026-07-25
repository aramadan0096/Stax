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
CURRENT_SCHEMA_VERSION = 23

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


def _migrate_v14(conn):
    """v13 -> v14: create notifications table for the in-app notification
    center (EP6)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            level      TEXT NOT NULL DEFAULT 'info',
            title      TEXT NOT NULL,
            body       TEXT,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    log.info("Migration v14: created notifications table")
    conn.commit()


def _migrate_v15(conn):
    """v14 -> v15: create watch_folders table for the folder-watcher
    ingestion-automation feature (EP6)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watch_folders (
            watch_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            path           TEXT NOT NULL,
            target_list_id INTEGER,
            recipe_id      INTEGER,
            interval_sec   INTEGER NOT NULL DEFAULT 30,
            enabled        INTEGER NOT NULL DEFAULT 1,
            last_scan      TIMESTAMP
        )
        """
    )
    log.info("Migration v15: created watch_folders table")
    conn.commit()


def _migrate_v16(conn):
    """v15 -> v16: create ingest_recipes table for saved ingest-option
    presets (EP6)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_recipes (
            recipe_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            values_json TEXT NOT NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    log.info("Migration v16: created ingest_recipes table")
    conn.commit()


def _migrate_v17(conn):
    """v16 -> v17: create proxy_profiles table + seed Low/Medium/High
    quality presets for proxy/transcode generation (EP6)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proxy_profiles (
            profile_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            kind        TEXT NOT NULL DEFAULT 'mp4',
            max_size    INTEGER NOT NULL DEFAULT 512,
            fps         INTEGER NOT NULL DEFAULT 24,
            duration    INTEGER,
            is_default  INTEGER NOT NULL DEFAULT 0,
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Seed default quality presets (F036) when the table is empty
    if conn.execute("SELECT COUNT(*) FROM proxy_profiles").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO proxy_profiles (name, kind, max_size, fps, is_default, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [("Low", "mp4", 256, 24, 0, 0),
             ("Medium", "mp4", 512, 24, 1, 1),
             ("High", "mp4", 1024, 24, 0, 2)])
        log.info("Seeded %d default proxy profiles", 3)
    log.info("Migration v17: created proxy_profiles table")
    conn.commit()


def _migrate_v18(conn):
    """v17 -> v18: create action_chains table for ordered, whitelisted
    ingest-automation action chains (EP6)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_chains (
            chain_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            steps_json TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    log.info("Migration v18: created action_chains table")
    conn.commit()


def _migrate_v19(conn):
    """v18 -> v19: create element_embeddings table for AI-embedding-based
    similarity search / discovery (EP7)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS element_embeddings (
            element_fk INTEGER PRIMARY KEY,
            model_id   TEXT NOT NULL,
            dim        INTEGER NOT NULL,
            vector     BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
        )
        """
    )
    log.info("Migration v19: created element_embeddings table")
    conn.commit()


def _migrate_v20(conn):
    """v19 -> v20: create element_colors table for non-AI color-signature /
    palette search (EP7, F004)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS element_colors (
            element_fk INTEGER PRIMARY KEY,
            histogram  BLOB NOT NULL,
            dominant   TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
        )
        """
    )
    log.info("Migration v20: created element_colors table")
    conn.commit()


def _seed_builtin_roles(conn):
    """Insert any missing built-in roles + their default permissions. Idempotent."""
    from permissions import BUILTIN_ROLES

    cur = conn.cursor()
    for name, perms in BUILTIN_ROLES.items():
        cur.execute("SELECT role_id FROM roles WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            continue
        cur.execute(
            "INSERT INTO roles (name, label, is_builtin) VALUES (?, ?, 1)",
            (name, name.capitalize()))
        role_id = cur.lastrowid
        for p in perms:
            cur.execute(
                "INSERT OR IGNORE INTO role_permissions (role_fk, permission) "
                "VALUES (?, ?)", (role_id, p))


def _migrate_v21(conn):
    """v20 -> v21: roles + role_permissions tables + seed built-in roles (EP8)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            role_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            label      TEXT,
            is_builtin INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_fk    INTEGER NOT NULL,
            permission TEXT NOT NULL,
            PRIMARY KEY (role_fk, permission),
            FOREIGN KEY (role_fk) REFERENCES roles(role_id) ON DELETE CASCADE
        )
        """
    )
    _seed_builtin_roles(conn)
    log.info("Migration v21: created roles/role_permissions tables + seeded built-in roles")
    conn.commit()


def _migrate_v22(conn):
    """v21 -> v22: relax users.role CHECK constraint (was hard-limited to
    'admin'/'user') so EP8 custom/built-in role names (reviewer, ingestor,
    viewer, ...) can be assigned to a user. SQLite has no ALTER TABLE ...
    DROP CONSTRAINT, so this rebuilds the table (idempotent: only runs the
    rebuild if the old CHECK is still present).

    IMPORTANT — table-rebuild ordering matters here. user_sessions.user_fk
    REFERENCES users(user_id). Renaming the *live* "users" table away (e.g.
    "ALTER TABLE users RENAME TO users_old") makes SQLite auto-rewrite
    user_sessions' FOREIGN KEY clause to point at "users_old" — verified
    empirically, and this happens regardless of PRAGMA foreign_keys. Once
    "users_old" is then dropped, user_sessions is left with a dangling FK
    and every login breaks (create_session -> "no such table: users_old").
    To avoid the rewrite entirely, this never renames the live "users"
    table: it builds "users_new" under an unrelated name, copies the data,
    drops the *old* "users" table (not a rename, so no other schema gets
    rewritten), then renames "users_new" -> "users" — renaming *into* a
    name other tables already reference does not trigger a rewrite (also
    verified empirically). foreign_keys is toggled OFF only around the
    DROP, because SQLite's FK enforcement otherwise refuses to drop a
    table that still has referencing child rows."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if row and row[0] and "CHECK(role IN ('admin', 'user'))" in row[0]:
        conn.commit()  # close any open txn so the pragma toggle below applies
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute(
                """
                CREATE TABLE users_v22_new (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    email TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    must_change_password INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                "INSERT INTO users_v22_new (user_id, username, password_hash, role, email, "
                "is_active, created_at, last_login, must_change_password) "
                "SELECT user_id, username, password_hash, role, email, is_active, "
                "created_at, last_login, must_change_password FROM users"
            )
            conn.execute("DROP TABLE users")
            conn.execute("ALTER TABLE users_v22_new RENAME TO users")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.commit()
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError("v22 left dangling FKs: {}".format(bad))
        log.info("Migration v22: relaxed users.role CHECK constraint for EP8 custom roles")
    conn.commit()


def _migrate_v23(conn):
    """v22 -> v23: activity_log table + indexes for the audit feed (EP8)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor       TEXT,
            action      TEXT NOT NULL,
            target_type TEXT,
            target_id   INTEGER,
            detail      TEXT,
            at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_at ON activity_log(at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log(action)")
    conn.commit()
    log.info("Migration v23: created activity_log table + indexes")


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
    _migrate_v14,  # 13 -> 14
    _migrate_v15,  # 14 -> 15
    _migrate_v16,  # 15 -> 16
    _migrate_v17,  # 16 -> 17
    _migrate_v18,  # 17 -> 18
    _migrate_v19,  # 18 -> 19
    _migrate_v20,  # 19 -> 20
    _migrate_v21,  # 20 -> 21
    _migrate_v22,  # 21 -> 22
    _migrate_v23,  # 22 -> 23
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
