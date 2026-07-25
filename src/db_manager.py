# -*- coding: utf-8 -*-
"""
Database Manager for StaX
Handles SQLite operations with network-aware file locking
"""

import sqlite3
import os
import time
import json
import hashlib
import hmac
import secrets
import logging
import re
from contextlib import contextmanager
from file_lock import FileLockManager
from filter_spec import normalize
from metadata_rules import validate_field_type
from permissions import PERMISSIONS, BUILTIN_ROLES, is_valid_permission

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 260000


def hash_password(password, iterations=_PBKDF2_ITERATIONS, salt=None):
    """Return a self-describing salted PBKDF2 hash: pbkdf2_sha256$iters$salt$hash."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256${0}${1}${2}'.format(iterations, salt.hex(), dk.hex())


def is_legacy_hash(stored):
    """True for the old unsalted format: a bare 64-char hex sha256 digest."""
    return bool(stored) and '$' not in stored and len(stored) == 64


def verify_password(stored, password):
    """Constant-time verify against a PBKDF2 or a legacy unsalted-sha256 hash."""
    if not stored:
        return False
    if is_legacy_hash(stored):
        legacy = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return hmac.compare_digest(legacy, stored)
    try:
        scheme, iters, salt_hex, hash_hex = stored.split('$')
    except ValueError:
        return False
    if scheme != 'pbkdf2_sha256':
        return False
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                             bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(dk.hex(), hash_hex)


class DatabaseManager(object):
    """
    Manages SQLite database operations for StaX.
    Implements network-aware file locking and connection pooling.
    """

    # Column whitelists — guard against .format()-into-SQL injection (M1).
    SEARCHABLE_ELEMENT_COLUMNS = {"name", "format", "type", "comment", "tags"}
    UPDATABLE_ELEMENT_COLUMNS = {
        "list_fk", "name", "type", "filepath_soft", "filepath_hard",
        "is_hard_copy", "frame_range", "format", "comment", "tags",
        "preview_path", "gif_preview_path", "video_preview_path",
        "geometry_preview_path", "is_deprecated", "file_size", "phash",
    }

    # Label validation and whitelists
    _COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
    _LABEL_FIELDS = {"name", "color_hex", "meaning", "sort_order"}

    # Smart collection field whitelist
    _COLLECTION_FIELDS = {"name", "filter_json", "created_by", "sort_order"}

    def __init__(self, db_path, enable_logging=False, use_file_lock=True):
        """
        Initialize database manager.
        
        Args:
            db_path (str): Path to SQLite database file
            enable_logging (bool): Enable detailed operation logging
            use_file_lock (bool): Enable external file locking for network shares
        """
        self.db_path = db_path
        self.max_retries = 10  # Increased for network environments
        self.retry_delay = 0.3  # seconds (exponential backoff)
        self.enable_logging = enable_logging
        self.use_file_lock = use_file_lock
        self.lock_file_path = db_path + '.lock'  # Lock file next to database
        
        # Ensure database directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                # Convert relative path to absolute to avoid permission issues in Nuke
                if not os.path.isabs(db_dir):
                    # Get the root directory (where the main script is located)
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    root_dir = os.path.dirname(script_dir)  # Go up from src/
                    abs_db_dir = os.path.join(root_dir, db_dir)
                else:
                    abs_db_dir = db_dir
                
                print("[DatabaseManager] Creating database directory: {}".format(abs_db_dir))
                os.makedirs(abs_db_dir)
                print("[DatabaseManager]   [OK] Database directory created")
                
                # Update db_path to use absolute path
                if not os.path.isabs(self.db_path):
                    self.db_path = os.path.join(root_dir, self.db_path)
                    self.lock_file_path = self.db_path + '.lock'
                    print("[DatabaseManager] Using absolute database path: {}".format(self.db_path))
            except OSError as e:
                print("[DatabaseManager]   [WARN] Failed to create directory: {}".format(e))
                # Try to use absolute path anyway
                if not os.path.isabs(self.db_path):
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    root_dir = os.path.dirname(script_dir)
                    self.db_path = os.path.join(root_dir, self.db_path)
                    self.lock_file_path = self.db_path + '.lock'
        
        # Initialize schema if database doesn't exist
        if not os.path.exists(self.db_path):
            self._create_schema()
        else:
            # Apply migrations for existing databases
            self._apply_migrations()

        # Versioned migrations (phash column, insertion_log table).
        # Idempotent; runs on every start so fresh and existing DBs converge.
        self._run_versioned_migrations()

    def _log(self, message):
        """Log message if logging is enabled."""
        if self.enable_logging:
            print("[DB] {}".format(message))
    
    @contextmanager
    def get_connection(self, write=True):
        """
        Context manager for database connections with file locking and retry logic.
        Implements external file locking for network-shared databases with exponential backoff.
        
        Yields:
            sqlite3.Connection: Database connection
            
        Raises:
            sqlite3.OperationalError: If connection fails after all retries
        """
        conn = None
        last_error = None
        file_lock = None
        
        try:
            # Acquire the external file lock only for writes (L6): concurrent
            # read connections no longer serialize behind one global OS lock.
            if self.use_file_lock and write:
                self._log("Acquiring file lock: {}".format(self.lock_file_path))
                file_lock = FileLockManager(
                    self.lock_file_path,
                    timeout=30.0,
                    retry_delay=0.1,
                    max_retries=100
                )
                file_lock.acquire()
                self._log("File lock acquired")
            
            for attempt in range(self.max_retries):
                try:
                    self._log("Connection attempt {} of {}".format(attempt + 1, self.max_retries))
                    
                    conn = sqlite3.connect(
                        self.db_path,
                        timeout=60.0,  # 60 second timeout for network locks
                        isolation_level='DEFERRED',
                        check_same_thread=False  # Allow multi-threaded access
                    )
                    conn.row_factory = sqlite3.Row  # Enable dict-like access
                    
                    # Enable foreign keys
                    conn.execute("PRAGMA foreign_keys = ON")
                    
                    # Optimize for network file systems
                    conn.execute("PRAGMA synchronous = NORMAL")  # Balance between safety and speed
                    conn.execute("PRAGMA journal_mode = DELETE")  # network-share safe (H1); no -wal/-shm sidecars
                    conn.execute("PRAGMA cache_size = -16000")  # 16MB cache
                    
                    self._log("Connection successful")
                    
                    yield conn
                    conn.commit()
                    self._log("Transaction committed")
                    break
                    
                except sqlite3.OperationalError as e:
                    last_error = e
                    error_msg = str(e).lower()
                    
                    # Detect lock-related errors
                    if 'locked' in error_msg or 'busy' in error_msg:
                        if attempt < self.max_retries - 1:
                            # Exponential backoff with jitter
                            delay = self.retry_delay * (2 ** attempt) + (time.time() % 0.1)
                            self._log("Database locked, retrying in {:.2f}s...".format(delay))
                            time.sleep(delay)
                            continue
                        else:
                            self._log("Max retries reached. Database still locked.")
                            raise RuntimeError(
                                "Database locked after {} retries. "
                                "Another process may be holding a long transaction. "
                                "Error: {}".format(self.max_retries, str(e))
                            )
                    else:
                        # Non-lock error, raise immediately
                        self._log("Database error: {}".format(str(e)))
                        raise
                        
                except Exception as e:
                    last_error = e
                    self._log("Unexpected error: {}".format(str(e)))
                    raise
        
        finally:
            # Always clean up connection and file lock
            if conn:
                try:
                    conn.close()
                    self._log("Connection closed")
                except Exception:
                    logger.debug("Error closing DB connection", exc_info=True)

            # Release file lock if acquired
            if file_lock:
                try:
                    file_lock.release()
                    self._log("File lock released")
                except Exception:
                    logger.debug("Error releasing file lock", exc_info=True)
    
    def _create_schema(self):
        """Create database schema with all required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Table 1: Stacks (Primary Categories)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stacks (
                    stack_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    path TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table 2: Lists (Sub-Categories with Hierarchical Support)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lists (
                    list_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stack_fk INTEGER NOT NULL,
                    parent_list_fk INTEGER,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stack_fk) REFERENCES stacks(stack_id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_list_fk) REFERENCES lists(list_id) ON DELETE CASCADE
                )
            """)
            
            # Create index for parent lookup
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lists_parent ON lists(parent_list_fk)")
            
            # Table 3: Elements (Assets)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS elements (
                    element_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_fk INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('2D', '3D', 'Toolset')),
                    filepath_soft TEXT,
                    filepath_hard TEXT,
                    is_hard_copy BOOLEAN NOT NULL DEFAULT 0,
                    frame_range TEXT,
                    format TEXT,
                    comment TEXT,
                    tags TEXT,
                    preview_path TEXT,
                    gif_preview_path TEXT,
                    video_preview_path TEXT,
                    geometry_preview_path TEXT,
                    is_deprecated BOOLEAN DEFAULT 0,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (list_fk) REFERENCES lists(list_id) ON DELETE CASCADE
                )
            """)
            
            # Table 4: Favorites (Per-user/machine)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    favorite_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    element_fk INTEGER NOT NULL,
                    machine_name TEXT NOT NULL,
                    user_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE,
                    UNIQUE(element_fk, machine_name, user_name)
                )
            """)
            
            # Table 5: Playlists (Shared collaborative lists)
            # Include creator tracking (created_by, created_on_machine)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    playlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_by TEXT,
                    created_on_machine TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table 6: Playlist Items (Many-to-many)
            # Use column names expected by code: item_id, order_index, added_at
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlist_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_fk INTEGER NOT NULL,
                    element_fk INTEGER NOT NULL,
                    order_index INTEGER DEFAULT 0,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (playlist_fk) REFERENCES playlists(playlist_id) ON DELETE CASCADE,
                    FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE,
                    UNIQUE(playlist_fk, element_fk)
                )
            """)
            
            # Table 7: Ingestion History
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    element_fk INTEGER,
                    action TEXT NOT NULL,
                    source_path TEXT,
                    target_list TEXT,
                    status TEXT NOT NULL,
                    message TEXT,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE SET NULL
                )
            """)
            
            # Table 8: Users and Permissions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'user')) DEFAULT 'user',
                    email TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    must_change_password INTEGER DEFAULT 0
                )
            """)
            
            # Table 9: User Sessions (for tracking logged-in users)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_fk INTEGER NOT NULL,
                    machine_name TEXT NOT NULL,
                    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_fk) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            # Settings table for storing configuration in database
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lists_stack ON lists(stack_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_list ON elements(list_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_type ON elements(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_name ON elements(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_deprecated ON elements(is_deprecated)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_element ON favorites(element_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(machine_name, user_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist ON playlist_items(playlist_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_items_element ON playlist_items(element_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_element ON ingestion_history(element_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON ingestion_history(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_fk)")
            
            # Create the initial admin user with a random password if none exist
            cursor.execute("SELECT COUNT(*) as count FROM users")
            if cursor.fetchone()['count'] == 0:
                self._seed_initial_admin(cursor)
            
            self._log("Database schema created with optimized indexes")
    
    def _apply_migrations(self):
        """
        Apply database migrations to existing database files.
        Checks for missing columns/tables and adds them.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Migration 1: Add parent_list_fk to lists table (for hierarchical sub-lists)
            try:
                cursor.execute("SELECT parent_list_fk FROM lists LIMIT 1")
                self._log("Migration 1: parent_list_fk already exists")
            except sqlite3.OperationalError:
                self._log("Migration 1: Adding parent_list_fk column to lists table")
                cursor.execute("ALTER TABLE lists ADD COLUMN parent_list_fk INTEGER")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_lists_parent ON lists(parent_list_fk)")
                self._log("Migration 1: Complete")
            
            # Migration 2: Add gif_preview_path to elements table (for future GIF previews)
            try:
                cursor.execute("SELECT gif_preview_path FROM elements LIMIT 1")
                self._log("Migration 2: gif_preview_path already exists")
            except sqlite3.OperationalError:
                self._log("Migration 2: Adding gif_preview_path column to elements table")
                cursor.execute("ALTER TABLE elements ADD COLUMN gif_preview_path TEXT")
                self._log("Migration 2: Complete")
            
            # Migration 2.5: Add video_preview_path column for sequence video previews
            try:
                cursor.execute("SELECT video_preview_path FROM elements LIMIT 1")
                self._log("Migration 2.5: video_preview_path already exists")
            except sqlite3.OperationalError:
                self._log("Migration 2.5: Adding video_preview_path column to elements table")
                cursor.execute("ALTER TABLE elements ADD COLUMN video_preview_path TEXT")
                self._log("Migration 2.5: Complete")

            # Migration 3.1: Add geometry_preview_path column for 3D assets
            try:
                cursor.execute("SELECT geometry_preview_path FROM elements LIMIT 1")
                self._log("Migration 3.1: geometry_preview_path already exists")
            except sqlite3.OperationalError:
                self._log("Migration 3.1: Adding geometry_preview_path column to elements table")
                cursor.execute("ALTER TABLE elements ADD COLUMN geometry_preview_path TEXT")
                self._log("Migration 3.1: Complete")
            
            # Migration 3: Create users table if it doesn't exist
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='table' AND name='users'
            """)
            if not cursor.fetchone():
                self._log("Migration 3: Creating users table")
                cursor.execute("""
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('admin', 'user')) DEFAULT 'user',
                        email TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        must_change_password INTEGER DEFAULT 0
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

                # Create the initial admin user with a random password
                self._seed_initial_admin(cursor)
                self._log("Migration 3: Complete - Initial admin user created")
            
            # Migration 4: Create user_sessions table if it doesn't exist
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='table' AND name='user_sessions'
            """)
            if not cursor.fetchone():
                self._log("Migration 4: Creating user_sessions table")
                cursor.execute("""
                    CREATE TABLE user_sessions (
                        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_fk INTEGER NOT NULL,
                        machine_name TEXT NOT NULL,
                        login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1,
                        FOREIGN KEY (user_fk) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_fk)")
                self._log("Migration 4: Complete")
            
            # Migration 5: Ensure playlists table has created_by and created_on_machine
            try:
                cursor.execute("SELECT created_by FROM playlists LIMIT 1")
                self._log("Migration 5: playlists already has created_by")
            except sqlite3.OperationalError:
                self._log("Migration 5: Adding created_by and created_on_machine to playlists")
                try:
                    cursor.execute("ALTER TABLE playlists ADD COLUMN created_by TEXT")
                except sqlite3.OperationalError:
                    pass
                try:
                    cursor.execute("ALTER TABLE playlists ADD COLUMN created_on_machine TEXT")
                except sqlite3.OperationalError:
                    pass
                self._log("Migration 5: Complete")

            # Migration 6: Ensure playlist_items uses item_id, order_index, added_at
            try:
                cursor.execute("SELECT item_id FROM playlist_items LIMIT 1")
                self._log("Migration 6: playlist_items already migrated")
            except sqlite3.OperationalError:
                # If playlist_items exists but has old column names, attempt to migrate safely
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlist_items'")
                if cursor.fetchone():
                    self._log("Migration 6: Migrating playlist_items table schema")
                    # Create new temporary table with correct schema
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS playlist_items_new (
                            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            playlist_fk INTEGER NOT NULL,
                            element_fk INTEGER NOT NULL,
                            order_index INTEGER DEFAULT 0,
                            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (playlist_fk) REFERENCES playlists(playlist_id) ON DELETE CASCADE,
                            FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE,
                            UNIQUE(playlist_fk, element_fk)
                        )
                    """)
                    # Count the source rows so we can verify nothing is lost.
                    src_count = cursor.execute(
                        "SELECT COUNT(*) FROM playlist_items"
                    ).fetchone()[0]

                    # Map older column names if present.
                    cursor.execute("PRAGMA table_info(playlist_items)")
                    cols = [r[1] for r in cursor.fetchall()]
                    select_cols = []
                    select_cols.append('playlist_fk' if 'playlist_fk' in cols else 'playlist')
                    select_cols.append('element_fk' if 'element_fk' in cols else 'element')
                    if 'order_index' in cols:
                        select_cols.append('order_index')
                    elif 'sort_order' in cols:
                        select_cols.append('sort_order')
                    else:
                        select_cols.append('0')

                    # L11: the timestamp source must be conditional too — a
                    # legacy playlist_items may have neither created_at nor
                    # added_at, and referencing a missing column unconditionally
                    # raises sqlite3.OperationalError (uncaught here, crashing
                    # DatabaseManager construction).
                    if 'created_at' in cols:
                        timestamp_expr = 'COALESCE(created_at, CURRENT_TIMESTAMP)'
                    elif 'added_at' in cols:
                        timestamp_expr = 'COALESCE(added_at, CURRENT_TIMESTAMP)'
                    else:
                        timestamp_expr = 'CURRENT_TIMESTAMP'

                    # INSERT OR IGNORE so a UNIQUE clash drops a row instead of
                    # aborting mid-statement — the count guard below then catches it.
                    copy_sql = (
                        "INSERT OR IGNORE INTO playlist_items_new "
                        "(playlist_fk, element_fk, order_index, added_at) "
                        "SELECT {cols}, {ts} "
                        "FROM playlist_items".format(
                            cols=','.join(select_cols), ts=timestamp_expr
                        )
                    )
                    cursor.execute(copy_sql)

                    # L11: verify row counts BEFORE the destructive swap. On
                    # mismatch, raise so the get_connection context rolls back
                    # (no commit) and the original playlist_items is preserved.
                    new_count = cursor.execute(
                        "SELECT COUNT(*) FROM playlist_items_new"
                    ).fetchone()[0]
                    if new_count != src_count:
                        raise RuntimeError(
                            "Migration 6: playlist_items copy lost rows "
                            "(source={}, copied={}); aborting to avoid data loss".format(
                                src_count, new_count
                            )
                        )

                    # Counts match — safe to swap.
                    cursor.execute("ALTER TABLE playlist_items RENAME TO playlist_items_old")
                    cursor.execute("ALTER TABLE playlist_items_new RENAME TO playlist_items")
                    cursor.execute("DROP TABLE IF EXISTS playlist_items_old")
                    self._log("Migration 6: Complete ({} rows preserved)".format(src_count))
                else:
                    self._log("Migration 6: playlist_items table does not exist; skipping")

            # Migration 7: Create settings table if it doesn't exist
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='table' AND name='settings'
            """)
            if not cursor.fetchone():
                self._log("Migration 7: Creating settings table")
                cursor.execute("""
                    CREATE TABLE settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                self._log("Migration 7: Complete")
            else:
                self._log("Migration 7: settings table already exists")

            # Migration 8: add must_change_password to users (SP4/H2)
            try:
                cursor.execute("SELECT must_change_password FROM users LIMIT 1")
                self._log("Migration 8: must_change_password already exists")
            except sqlite3.OperationalError:
                self._log("Migration 8: Adding must_change_password to users")
                cursor.execute(
                    "ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0"
                )
                self._log("Migration 8: Complete")

            self._log("All migrations applied successfully")

    def _run_versioned_migrations(self):
        """Run the versioned migration runner (elements.phash, insertion_log)."""
        from db_migrations import run_migrations
        with self.get_connection() as conn:
            run_migrations(conn)

    # ======================
    # STACK OPERATIONS
    # ======================
    
    def create_stack(self, name, path):
        """
        Create a new stack.
        
        Args:
            name (str): Stack name
            path (str): Physical path on network
            
        Returns:
            int: stack_id of created stack
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO stacks (name, path) VALUES (?, ?)",
                (name, path)
            )
            return cursor.lastrowid
    
    def get_all_stacks(self):
        """
        Get all stacks.
        
        Returns:
            list: List of stack dictionaries
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stacks ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stack_by_id(self, stack_id):
        """Get stack by ID."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stacks WHERE stack_id = ?", (stack_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def delete_stack(self, stack_id):
        """Delete stack (cascades to lists and elements)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stacks WHERE stack_id = ?", (stack_id,))
            return cursor.rowcount > 0
    
    # ======================
    # LIST OPERATIONS
    # ======================
    
    def create_list(self, stack_id, name, parent_list_id=None):
        """
        Create a new list within a stack (or as a sub-list).
        
        Args:
            stack_id (int): Parent stack ID
            name (str): List name
            parent_list_id (int): Optional parent list ID for sub-lists
            
        Returns:
            int: list_id of created list
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO lists (stack_fk, name, parent_list_fk) VALUES (?, ?, ?)",
                (stack_id, name, parent_list_id)
            )
            return cursor.lastrowid
    
    def get_lists_by_stack(self, stack_id, parent_list_id=None):
        """
        Get all lists for a stack (optionally filtered by parent).
        
        Args:
            stack_id (int): Stack ID
            parent_list_id (int): If None, returns top-level lists only.
                                  If provided, returns sub-lists of that parent.
            
        Returns:
            list: List of list dictionaries
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            if parent_list_id is None:
                # Get top-level lists (no parent)
                cursor.execute(
                    "SELECT * FROM lists WHERE stack_fk = ? AND parent_list_fk IS NULL ORDER BY name",
                    (stack_id,)
                )
            else:
                # Get sub-lists of a specific parent
                cursor.execute(
                    "SELECT * FROM lists WHERE stack_fk = ? AND parent_list_fk = ? ORDER BY name",
                    (stack_id, parent_list_id)
                )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_sub_lists(self, parent_list_id):
        """
        Get all direct sub-lists of a parent list.
        
        Args:
            parent_list_id (int): Parent list ID
            
        Returns:
            list: List of sub-list dictionaries
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM lists WHERE parent_list_fk = ? ORDER BY name",
                (parent_list_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_list_by_id(self, list_id):
        """Get list by ID."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lists WHERE list_id = ?", (list_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_list_hierarchy(self, list_id):
        """Return list ancestors from top-level to the specified list."""
        hierarchy = []
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            current_id = list_id
            while current_id:
                cursor.execute("SELECT * FROM lists WHERE list_id = ?", (current_id,))
                row = cursor.fetchone()
                if not row:
                    break
                hierarchy.append(dict(row))
                current_id = row['parent_list_fk']
        hierarchy.reverse()
        return hierarchy

    def get_repository_path_for_list(self, list_id):
        """Return the repository path on disk for a list hierarchy."""
        hierarchy = self.get_list_hierarchy(list_id)
        if not hierarchy:
            return None

        top_entry = hierarchy[0]
        stack = self.get_stack_by_id(top_entry['stack_fk']) if top_entry else None
        stack_path = stack.get('path') if stack else None
        if not stack_path:
            return None

        parts = [stack_path] + [entry['name'] for entry in hierarchy]
        path = parts[0]
        if len(parts) > 1:
            path = os.path.join(*parts)
        return os.path.normpath(path)

    def get_list_display_path(self, list_id, separator=' / '):
        """Return a human-readable Stack/List path."""
        hierarchy = self.get_list_hierarchy(list_id)
        if not hierarchy:
            return ''

        stack = self.get_stack_by_id(hierarchy[0]['stack_fk']) if hierarchy else None
        names = []
        if stack and stack.get('name'):
            names.append(stack['name'])
        names.extend([entry['name'] for entry in hierarchy])
        return separator.join(names)

    def delete_list(self, list_id):
        """Delete list (cascades to elements)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM lists WHERE list_id = ?", (list_id,))
            return cursor.rowcount > 0
    
    # ======================
    # ELEMENT OPERATIONS
    # ======================
    
    def create_element(self, list_id, name, element_type, **kwargs):
        """
        Create a new element (asset).
        
        Args:
            list_id (int): Parent list ID
            name (str): Element name
            element_type (str): '2D', '3D', or 'Toolset'
            **kwargs: Additional fields (filepath_soft, filepath_hard, is_hard_copy, etc.)
            
        Returns:
            int: element_id of created element
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build query dynamically
            fields = ['list_fk', 'name', 'type']
            values = [list_id, name, element_type]
            
            for key, value in kwargs.items():
                if key in ['filepath_soft', 'filepath_hard', 'is_hard_copy', 
                          'frame_range', 'format', 'comment', 'tags', 
                          'preview_path', 'gif_preview_path', 'video_preview_path', 'geometry_preview_path', 'is_deprecated', 'file_size']:
                    fields.append(key)
                    values.append(value)

            # EP8: always stamp updated_at on insert so every element has a
            # non-null value from creation, regardless of whether the v24
            # migration's plain ADD COLUMN (no DEFAULT, upgraded-DB) or
            # DEFAULT CURRENT_TIMESTAMP (fresh-DB) branch ran -- required for
            # the sync newest-wins merge to compare it safely.
            fields.append('updated_at')
            values.append(self._now_iso())

            placeholders = ','.join(['?'] * len(values))
            field_names = ','.join(fields)

            cursor.execute(
                "INSERT INTO elements ({}) VALUES ({})".format(field_names, placeholders),
                values
            )
            return cursor.lastrowid
    
    def get_elements_by_list(self, list_id, include_deprecated=False, limit=None, offset=0):
        """
        Get elements for a list with optional pagination.
        
        Args:
            list_id (int): List ID
            include_deprecated (bool): Include deprecated elements
            limit (int): Maximum number of results (None = all)
            offset (int): Number of results to skip (for pagination)
            
        Returns:
            list: List of element dictionaries
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM elements WHERE list_fk = ?"
            params = [list_id]
            
            if not include_deprecated:
                query += " AND is_deprecated = 0"
            
            query += " ORDER BY name"
            
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_elements_count(self, list_id, include_deprecated=False):
        """
        Get total count of elements in a list.
        
        Args:
            list_id (int): List ID
            include_deprecated (bool): Include deprecated elements
            
        Returns:
            int: Total element count
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) FROM elements WHERE list_fk = ?"
            params = [list_id]
            
            if not include_deprecated:
                query += " AND is_deprecated = 0"
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]
    
    def get_element_by_id(self, element_id):
        """Get element by ID."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM elements WHERE element_id = ?", (element_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recent_elements(self, limit=12):
        """Most recently created elements, newest first.

        Rows inserted within the same second share a `created_at`, so
        `element_id DESC` is used as a tiebreaker (elements are inserted
        with an AUTOINCREMENT primary key, so a higher id is always newer).

        Deprecated elements are excluded, matching the same
        `is_deprecated = 0` filter get_elements_by_list()/
        get_elements_count() apply -- otherwise a deprecated element could
        surface in the start page's Recent section and be double-clicked
        straight into Nuke (final whole-branch review "also fix").

        Args:
            limit (int): Maximum number of results.

        Returns:
            list: List of element dicts.
        """
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM elements WHERE is_deprecated = 0 "
                "ORDER BY created_at DESC, element_id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def update_element(self, element_id, _actor=None, **kwargs):
        """
        Update element fields.

        Args:
            element_id (int): Element ID
            _actor (str): Optional actor name; when given, records an
                EP8 activity_log "metadata_edit" entry on success.
            **kwargs: Fields to update

        Returns:
            bool: True if updated
        """
        updates = {
            k: v for k, v in kwargs.items() if k in self.UPDATABLE_ELEMENT_COLUMNS
        }
        if not updates:
            return False
        updates["updated_at"] = self._now_iso()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            set_clause = ', '.join(["{} = ?".format(k) for k in updates.keys()])
            values = list(updates.values()) + [element_id]

            cursor.execute(
                "UPDATE elements SET {} WHERE element_id = ?".format(set_clause),
                values
            )
            updated = cursor.rowcount > 0

        if updated and _actor:
            self.log_activity(_actor, "metadata_edit", "element", element_id,
                               ",".join(sorted(updates.keys())))
        return updated

    @staticmethod
    def _now_iso():
        import datetime
        return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def delete_element(self, element_id, actor=None):
        """Delete element.

        Args:
            element_id (int): Element ID
            actor (str): Optional actor name; when given, records an
                EP8 activity_log "delete" entry on success.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM elements WHERE element_id = ?", (element_id,))
            deleted = cursor.rowcount > 0

        if deleted and actor:
            self.log_activity(actor, "delete", "element", element_id)
        return deleted

    @staticmethod
    def _validate_rating(rating):
        if not isinstance(rating, int) or rating < 0 or rating > 5:
            raise ValueError("rating must be an integer 0..5, got {!r}".format(rating))

    def set_element_rating(self, element_id, rating):
        """Set the team-shared 0..5 star rating on an element."""
        self._validate_rating(rating)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE elements SET rating = ? WHERE element_id = ?",
                (rating, element_id),
            )

    def bulk_set_rating(self, element_ids, rating):
        """Set the rating on many elements. Returns rows affected."""
        self._validate_rating(rating)
        if not element_ids:
            return 0
        placeholders = ",".join("?" for _ in element_ids)
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE elements SET rating = ? WHERE element_id IN ({})".format(placeholders),
                [rating] + list(element_ids),
            )
            return cur.rowcount

    def get_labels(self):
        """Return all labels ordered by sort_order."""
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT label_id, name, color_hex, meaning, sort_order "
                "FROM labels ORDER BY sort_order, label_id"
            ).fetchall()
            return [dict(r) for r in rows]

    def create_label(self, name, color_hex, meaning="", sort_order=0):
        """Create a label. Returns the new label_id."""
        if not self._COLOR_RE.match(color_hex or ""):
            raise ValueError("color_hex must match #RRGGBB, got {!r}".format(color_hex))
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO labels (name, color_hex, meaning, sort_order) VALUES (?, ?, ?, ?)",
                (name, color_hex, meaning, sort_order),
            )
            return cur.lastrowid

    def update_label(self, label_id, **fields):
        """Update whitelisted label fields."""
        updates = {k: v for k, v in fields.items() if k in self._LABEL_FIELDS}
        if "color_hex" in updates and not self._COLOR_RE.match(updates["color_hex"] or ""):
            raise ValueError("color_hex must match #RRGGBB")
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE labels SET {} WHERE label_id = ?".format(set_clause),
                list(updates.values()) + [label_id],
            )

    def delete_label(self, label_id):
        """Delete a label; null it out on any referencing elements (SET NULL)."""
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE elements SET label_fk = NULL WHERE label_fk = ?", (label_id,))
            cur.execute("DELETE FROM labels WHERE label_id = ?", (label_id,))

    def set_element_label(self, element_id, label_fk):
        """Set (or clear with None) the label on an element."""
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE elements SET label_fk = ? WHERE element_id = ?",
                (label_fk, element_id),
            )

    def bulk_set_label(self, element_ids, label_fk):
        """Set the label on many elements. Returns rows affected."""
        if not element_ids:
            return 0
        placeholders = ",".join("?" for _ in element_ids)
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE elements SET label_fk = ? WHERE element_id IN ({})".format(placeholders),
                [label_fk] + list(element_ids),
            )
            return cur.rowcount

    def search_elements(self, search_text, property_name='name', match_type='loose'):
        """
        Search elements by property.
        
        Args:
            search_text (str): Search term
            property_name (str): Property to search ('name', 'format', 'type', 'comment')
            match_type (str): 'loose' (LIKE) or 'strict' (exact match)
            
        Returns:
            list: Matching elements
        """
        if property_name not in self.SEARCHABLE_ELEMENT_COLUMNS:
            self._log("search_elements: rejected column '{}', using 'name'".format(property_name))
            property_name = "name"

        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()

            if match_type == 'loose':
                query = "SELECT * FROM elements WHERE {} LIKE ? ORDER BY name".format(property_name)
                cursor.execute(query, ('%' + search_text + '%',))
            else:  # strict
                query = "SELECT * FROM elements WHERE {} = ? ORDER BY name".format(property_name)
                cursor.execute(query, (search_text,))
            
            return [dict(row) for row in cursor.fetchall()]

    # Tag boundary match: normalize ", " to "," then wrap and LIKE %,tag,%
    # The bound value must be routed through _escape_like() so a literal
    # '_' or '%' in a tag is matched literally rather than as a wildcard.
    _TAG_MATCH = ("(',' || REPLACE(IFNULL(tags,''), ', ', ',') || ',') "
                  "LIKE '%,' || ? || ',%' ESCAPE '\\'")

    @staticmethod
    def _escape_like(value):
        """Escape LIKE wildcards so a tag matches literally."""
        return (str(value).replace('\\', '\\\\')
                          .replace('%', '\\%')
                          .replace('_', '\\_'))

    @staticmethod
    def _build_filter_where(filter_spec):
        """Return (where_sql, params) for a normalized FilterSpec. Column names
        are code literals; all user values are parameterized."""
        s = normalize(filter_spec)
        clauses, params = [], []

        if s["text"]:
            like = "%" + s["text"] + "%"
            clauses.append("(name LIKE ? OR IFNULL(comment,'') LIKE ? OR IFNULL(tags,'') LIKE ?)")
            params += [like, like, like]

        if s["types"]:
            clauses.append("type IN ({})".format(",".join("?" for _ in s["types"])))
            params += s["types"]

        if s["formats"]:
            clauses.append("format IN ({})".format(",".join("?" for _ in s["formats"])))
            params += s["formats"]
        if s["formats_exclude"]:
            clauses.append("IFNULL(format,'') NOT IN ({})".format(
                ",".join("?" for _ in s["formats_exclude"])))
            params += s["formats_exclude"]

        for tag in s["tags_all"]:
            clauses.append(DatabaseManager._TAG_MATCH)
            params.append(DatabaseManager._escape_like(tag))
        if s["tags_any"]:
            ors = " OR ".join(DatabaseManager._TAG_MATCH for _ in s["tags_any"])
            clauses.append("(" + ors + ")")
            params += [DatabaseManager._escape_like(t) for t in s["tags_any"]]
        for tag in s["tags_exclude"]:
            clauses.append("NOT " + DatabaseManager._TAG_MATCH)
            params.append(DatabaseManager._escape_like(tag))

        if s["rating_min"]:
            clauses.append("rating >= ?")
            params.append(s["rating_min"])
        if s["label_fks"]:
            clauses.append("label_fk IN ({})".format(",".join("?" for _ in s["label_fks"])))
            params += s["label_fks"]

        if s["is_deprecated"] is not None:
            clauses.append("is_deprecated = ?")
            params.append(1 if s["is_deprecated"] else 0)
        if s["is_hard_copy"] is not None:
            clauses.append("is_hard_copy = ?")
            params.append(1 if s["is_hard_copy"] else 0)

        if s["list_fk"]:
            clauses.append("list_fk = ?")
            params.append(s["list_fk"])
        if s["stack_fk"]:
            clauses.append("list_fk IN (SELECT list_id FROM lists WHERE stack_fk = ?)")
            params.append(s["stack_fk"])

        where = " AND ".join(clauses) if clauses else "1=1"
        return where, params

    def search_elements_advanced(self, filter_spec, limit=None, offset=0):
        where, params = self._build_filter_where(filter_spec)
        sql = "SELECT * FROM elements WHERE {} ORDER BY name".format(where)
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = params + [limit, offset]
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def count_elements_advanced(self, filter_spec):
        where, params = self._build_filter_where(filter_spec)
        sql = "SELECT COUNT(*) FROM elements WHERE {}".format(where)
        with self.get_connection(write=False) as conn:
            return conn.execute(sql, params).fetchone()[0]

    def _facet_count_query(self, filter_spec, drop_key, group_col):
        """Count rows grouped by group_col, applying the filter minus drop_key."""
        spec = normalize(filter_spec)
        # zero-out the facet's own clause so counts reflect siblings only
        if drop_key:
            spec = dict(spec)
            spec[drop_key] = [] if isinstance(spec[drop_key], list) else (0 if drop_key == "rating_min" else None)
        where, params = self._build_filter_where(spec)
        sql = "SELECT {c}, COUNT(*) FROM elements WHERE {w} GROUP BY {c}".format(c=group_col, w=where)
        with self.get_connection(write=False) as conn:
            return {row[0]: row[1] for row in conn.execute(sql, params).fetchall() if row[0] is not None}

    def get_facet_counts(self, filter_spec):
        counts = {
            "type":   self._facet_count_query(filter_spec, "types", "type"),
            "format": self._facet_count_query(filter_spec, "formats", "format"),
            "rating": self._facet_count_query(filter_spec, "rating_min", "rating"),
            "label":  self._facet_count_query(filter_spec, "label_fks", "label_fk"),
            "status": {},
        }
        # status: active/deprecated tally, with is_deprecated's own clause
        # dropped so both buckets are always present and each reflects what
        # selecting it would yield (no hard-copy tally -- outside this facet's
        # interface)
        status_spec = normalize(filter_spec)
        status_spec["is_deprecated"] = None
        where, params = self._build_filter_where(status_spec)
        with self.get_connection(write=False) as conn:
            dep = conn.execute(
                "SELECT is_deprecated, COUNT(*) FROM elements WHERE {} GROUP BY is_deprecated".format(where),
                params).fetchall()
            counts["status"] = {("deprecated" if k else "active"): v for k, v in dep}
        # tag facet: parse comma-joined tags of the sibling-filtered set --
        # the tag clauses (tags_any/tags_all/tags_exclude) are dropped so an
        # active tags_any doesn't OR-widen the rows a sibling tag is counted
        # against
        tag_spec = normalize(filter_spec)
        tag_spec["tags_any"] = []
        tag_spec["tags_all"] = []
        tag_spec["tags_exclude"] = []
        rows = self.search_elements_advanced(tag_spec)
        tag_counts = {}
        for r in rows:
            for t in [x.strip() for x in (r.get("tags") or "").split(",") if x.strip()]:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        counts["tag"] = tag_counts
        return counts

    # ======================
    # FAVORITES OPERATIONS
    # ======================
    
    # ======================
    # HISTORY OPERATIONS
    # ======================
    
    def log_ingestion(self, action, source_path, target_list, status, message=None,
                       element_id=None, actor=None):
        """
        Log an ingestion event.

        Args:
            action (str): Action performed
            source_path (str): Source file path
            target_list (str): Target list name
            status (str): 'success' or 'error'
            message (str): Optional message
            element_id (int): Optional element ID if created
            actor (str): Optional actor name; when given and status is
                "success", records an EP8 activity_log "ingest" entry.

        Returns:
            int: history_id
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO ingestion_history
                   (element_fk, action, source_path, target_list, status, message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (element_id, action, source_path, target_list, status, message)
            )
            history_id = cursor.lastrowid

        if status == "success" and actor:
            self.log_activity(actor, "ingest", "element", element_id, source_path)
        return history_id
    
    def get_ingestion_history(self, limit=100):
        """
        Get recent ingestion history.
        
        Args:
            limit (int): Number of records to return
            
        Returns:
            list: History records
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM ingestion_history ORDER BY ingested_at DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def export_history_to_csv(self, output_path, limit=None):
        """
        Export ingestion history to CSV.
        
        Args:
            output_path (str): CSV file path
            limit (int): Optional limit on records
        """
        import csv
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM ingestion_history ORDER BY ingested_at DESC"
            if limit:
                query += " LIMIT {}".format(limit)
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if rows:
                with open(output_path, 'wb') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(dict(row))
    
    # Favorites management
    
    def add_favorite(self, element_id, user_name=None, machine_name=None):
        """
        Add element to favorites.
        
        Args:
            element_id (int): Element ID
            user_name (str): User name (optional, uses config if None)
            machine_name (str): Machine name (optional, uses config if None)
            
        Returns:
            int: Favorite ID or None if already exists
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if already favorited
            cursor.execute(
                "SELECT favorite_id FROM favorites WHERE element_fk = ? AND user_name = ? AND machine_name = ?",
                (element_id, user_name or '', machine_name or '')
            )
            if cursor.fetchone():
                return None  # Already favorited
            
            cursor.execute(
                "INSERT INTO favorites (element_fk, user_name, machine_name) VALUES (?, ?, ?)",
                (element_id, user_name or '', machine_name or '')
            )
            conn.commit()
            return cursor.lastrowid
    
    def remove_favorite(self, element_id, user_name=None, machine_name=None):
        """
        Remove element from favorites.
        
        Args:
            element_id (int): Element ID
            user_name (str): User name
            machine_name (str): Machine name
            
        Returns:
            bool: True if removed, False if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM favorites WHERE element_fk = ? AND user_name = ? AND machine_name = ?",
                (element_id, user_name or '', machine_name or '')
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def is_favorite(self, element_id, user_name=None, machine_name=None):
        """
        Check if element is in favorites.
        
        Args:
            element_id (int): Element ID
            user_name (str): User name
            machine_name (str): Machine name
            
        Returns:
            bool: True if favorited, False otherwise
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM favorites WHERE element_fk = ? AND user_name = ? AND machine_name = ?",
                (element_id, user_name or '', machine_name or '')
            )
            return cursor.fetchone() is not None
    
    def get_favorites(self, user_name=None, machine_name=None):
        """
        Get all favorite elements for user/machine.
        
        Args:
            user_name (str): User name
            machine_name (str): Machine name
            
        Returns:
            list: List of element dicts
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.* FROM elements e
                INNER JOIN favorites f ON e.element_id = f.element_fk
                WHERE f.user_name = ? AND f.machine_name = ?
                ORDER BY f.created_at DESC
            """, (user_name or '', machine_name or ''))
            return [dict(row) for row in cursor.fetchall()]
    
    # Playlists management
    
    def create_playlist(self, name, description=None, user_name=None, machine_name=None):
        """
        Create a new playlist.
        
        Args:
            name (str): Playlist name
            description (str): Optional description
            user_name (str): Creator user name
            machine_name (str): Creator machine name
            
        Returns:
            int: Playlist ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO playlists (name, description, created_by, created_on_machine) VALUES (?, ?, ?, ?)",
                (name, description or '', user_name or '', machine_name or '')
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_all_playlists(self):
        """
        Get all playlists.
        
        Returns:
            list: List of playlist dicts
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM playlists ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_playlist_by_id(self, playlist_id):
        """
        Get playlist by ID.
        
        Args:
            playlist_id (int): Playlist ID
            
        Returns:
            dict: Playlist data or None
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM playlists WHERE playlist_id = ?", (playlist_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_playlist(self, playlist_id, name=None, description=None):
        """
        Update playlist details.
        
        Args:
            playlist_id (int): Playlist ID
            name (str): New name (optional)
            description (str): New description (optional)
            
        Returns:
            bool: True if updated
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if name:
                cursor.execute("UPDATE playlists SET name = ? WHERE playlist_id = ?", (name, playlist_id))
            if description is not None:
                cursor.execute("UPDATE playlists SET description = ? WHERE playlist_id = ?", (description, playlist_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_playlist(self, playlist_id):
        """
        Delete a playlist and all its items.
        
        Args:
            playlist_id (int): Playlist ID
            
        Returns:
            bool: True if deleted
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Delete items first
            cursor.execute("DELETE FROM playlist_items WHERE playlist_fk = ?", (playlist_id,))
            # Delete playlist
            cursor.execute("DELETE FROM playlists WHERE playlist_id = ?", (playlist_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def add_element_to_playlist(self, playlist_id, element_id, order_index=None):
        """
        Add element to playlist.
        
        Args:
            playlist_id (int): Playlist ID
            element_id (int): Element ID
            order_index (int): Optional order index
            
        Returns:
            int: Playlist item ID or None if already exists
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if already in playlist
            cursor.execute(
                "SELECT item_id FROM playlist_items WHERE playlist_fk = ? AND element_fk = ?",
                (playlist_id, element_id)
            )
            if cursor.fetchone():
                return None  # Already in playlist
            
            # Get max order if not specified
            if order_index is None:
                cursor.execute("SELECT MAX(order_index) FROM playlist_items WHERE playlist_fk = ?", (playlist_id,))
                max_order = cursor.fetchone()[0]
                order_index = (max_order or 0) + 1
            
            cursor.execute(
                "INSERT INTO playlist_items (playlist_fk, element_fk, order_index) VALUES (?, ?, ?)",
                (playlist_id, element_id, order_index)
            )
            conn.commit()
            return cursor.lastrowid
    
    def remove_element_from_playlist(self, playlist_id, element_id):
        """
        Remove element from playlist.
        
        Args:
            playlist_id (int): Playlist ID
            element_id (int): Element ID
            
        Returns:
            bool: True if removed
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM playlist_items WHERE playlist_fk = ? AND element_fk = ?",
                (playlist_id, element_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_playlist_elements(self, playlist_id):
        """
        Get all elements in a playlist.
        
        Args:
            playlist_id (int): Playlist ID
            
        Returns:
            list: List of element dicts with order_index
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.*, pi.order_index, pi.added_at as playlist_added_at
                FROM elements e
                INNER JOIN playlist_items pi ON e.element_id = pi.element_fk
                WHERE pi.playlist_fk = ?
                ORDER BY pi.order_index ASC
            """, (playlist_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def is_element_in_playlist(self, playlist_id, element_id):
        """
        Check if element is in playlist.
        
        Args:
            playlist_id (int): Playlist ID
            element_id (int): Element ID
            
        Returns:
            bool: True if in playlist
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM playlist_items WHERE playlist_fk = ? AND element_fk = ?",
                (playlist_id, element_id)
            )
            return cursor.fetchone() is not None
    
    def reorder_playlist_items(self, playlist_id, element_order):
        """
        Reorder elements in playlist.
        
        Args:
            playlist_id (int): Playlist ID
            element_order (list): List of element IDs in desired order
            
        Returns:
            bool: True if successful
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for index, element_id in enumerate(element_order):
                cursor.execute(
                    "UPDATE playlist_items SET order_index = ? WHERE playlist_fk = ? AND element_fk = ?",
                    (index, playlist_id, element_id)
                )
            conn.commit()
            return True
    
    # ==================== Tag Management Methods ====================
    
    def get_all_tags(self):
        """
        Get all unique tags used across all elements.
        
        Returns:
            list: Sorted list of unique tags
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT tags FROM elements WHERE tags IS NOT NULL AND tags != ''")
            
            # Parse comma-separated tags
            all_tags = set()
            for row in cursor.fetchall():
                if row['tags']:
                    tags = [t.strip() for t in row['tags'].split(',') if t.strip()]
                    all_tags.update(tags)
            
            return sorted(list(all_tags), key=lambda x: x.lower())
    
    def search_elements_by_tags(self, tags, match_all=False):
        """
        Search elements by tags.
        
        Args:
            tags (list): List of tag strings to search for
            match_all (bool): If True, element must have all tags; if False, any tag matches
            
        Returns:
            list: List of matching element dicts
        """
        if not tags:
            return []

        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()

            if match_all:
                # Element must contain all specified tags
                query = "SELECT * FROM elements WHERE "
                conditions = []
                params = []
                
                for tag in tags:
                    conditions.append("(tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags = ?)")
                    # Match: start, middle, end, or exact
                    params.extend([
                        tag + ',%',  # At start
                        '%,' + tag + ',%',  # In middle
                        '%,' + tag,  # At end
                        tag  # Exact match (single tag)
                    ])
                
                query += " AND ".join(conditions)
                cursor.execute(query, params)
            else:
                # Element must contain at least one tag
                query = "SELECT * FROM elements WHERE "
                conditions = []
                params = []
                
                for tag in tags:
                    conditions.append("(tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags = ?)")
                    params.extend([
                        tag + ',%',
                        '%,' + tag + ',%',
                        '%,' + tag,
                        tag
                    ])
                
                query += " OR ".join(conditions)
                cursor.execute(query, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_elements_by_tag(self, tag):
        """
        Get all elements with a specific tag.
        
        Args:
            tag (str): Tag to search for
            
        Returns:
            list: List of element dicts
        """
        return self.search_elements_by_tags([tag], match_all=False)
    
    def add_tag_to_element(self, element_id, tag):
        """
        Add a tag to an element (if not already present).
        
        Args:
            element_id (int): Element ID
            tag (str): Tag to add
            
        Returns:
            bool: True if successful
        """
        tag = tag.strip()
        if not tag:
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tags FROM elements WHERE element_id = ?", (element_id,))
            row = cursor.fetchone()
            
            if not row:
                return False
            
            current_tags = row['tags'] or ''
            tag_list = [t.strip() for t in current_tags.split(',') if t.strip()]
            
            # Add tag if not already present
            if tag not in tag_list:
                tag_list.append(tag)
                new_tags = ', '.join(sorted(tag_list, key=lambda x: x.lower()))
                cursor.execute("UPDATE elements SET tags = ? WHERE element_id = ?", (new_tags, element_id))
                conn.commit()
            
            return True
    
    def remove_tag_from_element(self, element_id, tag):
        """
        Remove a tag from an element.
        
        Args:
            element_id (int): Element ID
            tag (str): Tag to remove
            
        Returns:
            bool: True if successful
        """
        tag = tag.strip()
        if not tag:
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tags FROM elements WHERE element_id = ?", (element_id,))
            row = cursor.fetchone()
            
            if not row:
                return False
            
            current_tags = row['tags'] or ''
            tag_list = [t.strip() for t in current_tags.split(',') if t.strip()]
            
            # Remove tag if present
            if tag in tag_list:
                tag_list.remove(tag)
                new_tags = ', '.join(sorted(tag_list, key=lambda x: x.lower())) if tag_list else ''
                cursor.execute("UPDATE elements SET tags = ? WHERE element_id = ?", (new_tags, element_id))
                conn.commit()
            
            return True
    
    def replace_element_tags(self, element_id, tags):
        """
        Replace all tags for an element.
        
        Args:
            element_id (int): Element ID
            tags (list or str): List of tags or comma-separated string
            
        Returns:
            bool: True if successful
        """
        if isinstance(tags, list):
            tag_list = [t.strip() for t in tags if t.strip()]
            tags_str = ', '.join(sorted(tag_list, key=lambda x: x.lower()))
        else:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            tags_str = ', '.join(sorted(tag_list, key=lambda x: x.lower()))
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE elements SET tags = ? WHERE element_id = ?", (tags_str, element_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # ==================== User Management Methods ====================
    
    def _seed_initial_admin(self, cursor):
        """Create the initial admin with a RANDOM password (never admin/admin).

        The password is logged once so a deployer can capture it; the account
        is flagged must_change_password so the login UI forces a reset (SP4/H2).
        """
        initial = secrets.token_urlsafe(12)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password) "
            "VALUES (?, ?, ?, 1)",
            ("admin", hash_password(initial), "admin"),
        )
        self._log("Initial admin created. One-time password: {0} "
                  "(change on first login)".format(initial))

    def create_user(self, username, password, role='user', email=None):
        """
        Create a new user with hashed password.
        
        Args:
            username (str): Username (must be unique)
            password (str): Plain text password (will be hashed)
            role (str): User role ('admin' or 'user')
            email (str, optional): User email
            
        Returns:
            int: user_id if successful, None if failed
        """
        password_hash = hash_password(password)

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
                    (username, password_hash, role, email)
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Username already exists
            return None
    
    def authenticate_user(self, username, password):
        """
        Authenticate user with username and password.
        
        Args:
            username (str): Username
            password (str): Plain text password
            
        Returns:
            dict: User dict if authenticated, None if failed
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username,)
            )
            row = cursor.fetchone()
            if row is None:
                return None

            stored = row['password_hash']
            if not verify_password(stored, password):
                return None

            # Transparent upgrade of a legacy unsalted hash on successful login.
            if is_legacy_hash(stored):
                try:
                    cursor.execute(
                        "UPDATE users SET password_hash = ? WHERE user_id = ?",
                        (hash_password(password), row['user_id'])
                    )
                except sqlite3.Error:
                    self._log("Password upgrade failed (read-only?); login allowed")

            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?",
                (row['user_id'],)
            )
            conn.commit()
            return dict(row)
    
    def get_user_by_id(self, user_id):
        """
        Get user by ID.
        
        Args:
            user_id (int): User ID
            
        Returns:
            dict: User dict or None
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_by_username(self, username):
        """
        Get user by username.
        
        Args:
            username (str): Username
            
        Returns:
            dict: User dict or None
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_users(self):
        """
        Get all users.
        
        Returns:
            list: List of user dicts
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY username")
            return [dict(row) for row in cursor.fetchall()]
    
    def update_user(self, user_id, **kwargs):
        """
        Update user fields.
        
        Args:
            user_id (int): User ID
            **kwargs: Fields to update (username, email, role, is_active)
            
        Returns:
            bool: True if successful
        """
        allowed_fields = ['username', 'email', 'role', 'is_active']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        set_clause = ', '.join(["{} = ?".format(k) for k in updates.keys()])
        values = list(updates.values()) + [user_id]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET {} WHERE user_id = ?".format(set_clause),
                values
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def change_user_password(self, user_id, new_password):
        """
        Change user password.
        
        Args:
            user_id (int): User ID
            new_password (str): New plain text password
            
        Returns:
            bool: True if successful
        """
        password_hash = hash_password(new_password)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                (password_hash, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_user(self, user_id):
        """
        Delete user (soft delete by setting is_active = 0).
        
        Args:
            user_id (int): User ID
            
        Returns:
            bool: True if successful
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_active = 0 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def create_session(self, user_id, machine_name):
        """
        Create a new user session.
        
        Args:
            user_id (int): User ID
            machine_name (str): Machine identifier
            
        Returns:
            int: session_id
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO user_sessions (user_fk, machine_name) VALUES (?, ?)",
                (user_id, machine_name)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_active_session(self, user_id, machine_name):
        """
        Get active session for user on machine.
        
        Args:
            user_id (int): User ID
            machine_name (str): Machine name
            
        Returns:
            dict: Session dict or None
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM user_sessions
                   WHERE user_fk = ? AND machine_name = ? AND is_active = 1 
                   ORDER BY login_time DESC LIMIT 1""",
                (user_id, machine_name)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def end_session(self, session_id):
        """
        End user session.
        
        Args:
            session_id (int): Session ID
            
        Returns:
            bool: True if successful
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE user_sessions SET is_active = 0 WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    # ============================================================================
    # Settings Management (Database-stored configuration)
    # ============================================================================
    
    def get_setting(self, key, default=None):
        """
        Get setting value from database.
        
        Args:
            key (str): Setting key
            default: Default value if key not found
            
        Returns:
            str or default: Setting value or default
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
    
    def set_setting(self, key, value):
        """
        Set setting value in database.
        
        Args:
            key (str): Setting key
            value (str): Setting value
            
        Returns:
            bool: True if successful
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO settings (key, value, updated_at) 
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (key, value)
            )
            conn.commit()
            return True
    
    def get_all_settings(self):
        """
        Get all settings from database.

        Returns:
            dict: Dictionary of all settings
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            return {row['key']: row['value'] for row in rows}

    # ============================================================
    # Consolidated methods merged from db_manager_additions (C1)
    # ============================================================

    def execute(self, sql, params=()):
        """Execute a write statement (INSERT/UPDATE/DELETE) and return the cursor.

        Used by analytics_panel.log_insertion. The context manager commits.
        """
        with self.get_connection() as conn:
            return conn.execute(sql, params)

    def get_top_inserted_elements(self, n=20):
        """Top N most-inserted elements with insertion counts.

        Returns list[dict] keys: element_id, name, list_name, format, type, count.
        """
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.element_id,
                       e.name,
                       l.name   AS list_name,
                       e.format,
                       e.type,
                       COUNT(i.log_id) AS count
                FROM insertion_log i
                JOIN elements e ON e.element_id = i.element_fk
                LEFT JOIN lists l ON l.list_id = e.list_fk
                GROUP BY i.element_fk
                ORDER BY count DESC
                LIMIT ?
                """,
                (n,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_insertions_by_month(self):
        """Insertion counts by calendar month. Returns list[dict] keys: month, count."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT strftime('%Y-%m', inserted_at) AS month,
                       COUNT(*)                        AS count
                FROM insertion_log
                GROUP BY month
                ORDER BY month ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_insertions_by_user(self):
        """Insertion counts per user. Returns list[dict] keys: username, count, last_active."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(u.username, 'Guest') AS username,
                       COUNT(i.log_id)               AS count,
                       MAX(i.inserted_at)            AS last_active
                FROM insertion_log i
                LEFT JOIN users u ON u.user_id = i.user_fk
                GROUP BY i.user_fk
                ORDER BY count DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_total_insertions(self):
        """Total number of rows in insertion_log."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM insertion_log")
            row = cursor.fetchone()
            return row[0] if row else 0

    def count_elements_by_list(self, list_id):
        """Count of non-deprecated elements in a list."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM elements "
                "WHERE list_fk = ? AND is_deprecated = 0",
                (list_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    # Fields the batch editor / API PATCH may set.
    METADATA_ELEMENT_COLUMNS = {
        "name", "tags", "comment", "type", "is_deprecated", "list_fk",
    }

    def update_element_metadata(self, element_id, **kwargs):
        """Update whitelisted metadata fields on an element (batch edit / API PATCH).

        Unknown keys are ignored. Routes through the whitelisted update_element.
        """
        updates = {
            k: v for k, v in kwargs.items() if k in self.METADATA_ELEMENT_COLUMNS
        }
        if not updates:
            return False
        return self.update_element(element_id, **updates)

    def update_element_phash(self, element_id, phash):
        """Store the perceptual hash for an element (SP2 duplicate detection)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE elements SET phash = ? WHERE element_id = ?",
                (phash, element_id),
            )
            return cursor.rowcount > 0

    def get_elements_with_phash(self):
        """All elements that have a stored phash (SP2 duplicate detection)."""
        with self.get_connection(write=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT element_id, name, list_fk, format, phash, preview_path "
                "FROM elements WHERE phash IS NOT NULL AND phash != ''"
            )
            return [dict(row) for row in cursor.fetchall()]

    # ======================
    # SAVED SEARCHES (EP2)
    # ======================

    def create_saved_search(self, name, filter_spec, user_name, machine_name=None):
        """Create a personal saved search.

        Args:
            name (str): Name of the saved search
            filter_spec (dict): FilterSpec dict to serialize as JSON
            user_name (str): User who owns this saved search
            machine_name (str): Optional machine identifier

        Returns:
            int: saved_search_id of the created search
        """
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO saved_searches (user_name, machine_name, name, filter_json) "
                "VALUES (?, ?, ?, ?)",
                (user_name, machine_name, name, json.dumps(filter_spec)),
            )
            return cur.lastrowid

    def get_saved_searches(self, user_name):
        """Get all saved searches for a user, scoped by user_name.

        Args:
            user_name (str): User to query

        Returns:
            list[dict]: List of saved search dicts with parsed 'filter' key
        """
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM saved_searches WHERE user_name = ? ORDER BY name",
                (user_name,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["filter"] = json.loads(d["filter_json"])
                out.append(d)
            return out

    def delete_saved_search(self, saved_search_id):
        """Delete a saved search by ID.

        Args:
            saved_search_id (int): ID of the saved search to delete
        """
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM saved_searches WHERE saved_search_id = ?", (saved_search_id,))

    def create_smart_collection(self, name, filter_spec, created_by=None, sort_order=0):
        """Create a shared smart collection.

        Args:
            name (str): Unique name of the smart collection
            filter_spec (dict): FilterSpec dict to serialize as JSON
            created_by (str): Optional user who created this collection
            sort_order (int): Sort order for display (default 0)

        Returns:
            int: collection_id of the created collection
        """
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO smart_collections (name, filter_json, created_by, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (name, json.dumps(filter_spec), created_by, sort_order))
            return cur.lastrowid

    def get_smart_collections(self):
        """Get all shared smart collections.

        Returns:
            list[dict]: List of smart collection dicts with parsed 'filter' key,
                       ordered by sort_order, name
        """
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM smart_collections ORDER BY sort_order, name").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["filter"] = json.loads(d["filter_json"])
                out.append(d)
            return out

    def update_smart_collection(self, collection_id, **fields):
        """Update whitelisted smart collection fields.

        Args:
            collection_id (int): ID of the collection to update
            **fields: Field updates (e.g., name="New Name", filter_spec={...}, sort_order=1)
                      filter_spec is translated to filter_json; other fields are whitelisted
        """
        if "filter_spec" in fields:
            fields["filter_json"] = json.dumps(fields.pop("filter_spec"))
        updates = {k: v for k, v in fields.items() if k in self._COLLECTION_FIELDS}
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE smart_collections SET {} WHERE collection_id = ?".format(set_clause),
                list(updates.values()) + [collection_id])

    def delete_smart_collection(self, collection_id):
        """Delete a smart collection by ID.

        Args:
            collection_id (int): ID of the collection to delete
        """
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM smart_collections WHERE collection_id = ?", (collection_id,))

    def add_synonym(self, term, group_key):
        """Add a synonym term to a group.

        Args:
            term (str): The synonym term to add (will be normalized to lowercase)
            group_key (str): The group key this term belongs to

        Returns:
            int: The lastrowid (synonym_id) of the inserted row
        """
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO search_synonyms (term, group_key) VALUES (?, ?)",
                        (term.strip().lower(), group_key))
            return cur.lastrowid

    def get_synonyms(self):
        """Get all synonyms ordered by group_key and term.

        Returns:
            list[dict]: List of synonym dicts with keys: synonym_id, term, group_key
        """
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM search_synonyms ORDER BY group_key, term").fetchall()]

    def delete_synonym(self, synonym_id):
        """Delete a synonym by ID.

        Args:
            synonym_id (int): ID of the synonym to delete
        """
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM search_synonyms WHERE synonym_id = ?", (synonym_id,))

    def expand_terms(self, text):
        """Expand each whitespace token to its synonym group's members.

        For each word in the input text:
        - If the word belongs to a synonym group, return all terms in that group
        - If the word is not in any group, return the word unchanged
        - Deduplicate while preserving order

        Args:
            text (str): Whitespace-separated search terms

        Returns:
            list[str]: List of unique expanded terms, order-preserving
        """
        words = [w.strip().lower() for w in (text or "").split() if w.strip()]
        if not words:
            return []
        with self.get_connection(write=False) as conn:
            result = []
            for w in words:
                groups = [r[0] for r in conn.execute(
                    "SELECT group_key FROM search_synonyms WHERE term = ?", (w,)).fetchall()]
                if groups:
                    placeholders = ",".join("?" for _ in groups)
                    siblings = [r[0] for r in conn.execute(
                        "SELECT DISTINCT term FROM search_synonyms WHERE group_key IN ({})".format(placeholders),
                        groups).fetchall()]
                    result.extend(siblings)
                else:
                    result.append(w)
            # dedupe preserving order
            seen, out = set(), []
            for t in result:
                if t not in seen:
                    seen.add(t); out.append(t)
            return out

    def suggest_correction(self, query):
        """Return the closest tag/name term to `query`, or None.

        Uses difflib to find a near match in the vocabulary of all tags
        and element names. Returns None if the query exactly matches a
        vocabulary term or if no match is close enough (cutoff=0.7).

        Args:
            query (str): The search query to check

        Returns:
            str: The suggested correction, or None if no match found or already exact
        """
        import difflib
        q = (query or "").strip().lower()
        if not q:
            return None
        vocab = set(t.lower() for t in self.get_all_tags())
        with self.get_connection(write=False) as conn:
            for r in conn.execute("SELECT name FROM elements").fetchall():
                if r[0]:
                    vocab.add(r[0].lower())
        if q in vocab:
            return None
        matches = difflib.get_close_matches(q, list(vocab), n=1, cutoff=0.7)
        return matches[0] if matches else None

    def add_recent_search(self, user_name, query_text, cap=20):
        """Record a search query and trim older searches to cap per user.

        Args:
            user_name (str): User who ran the search
            query_text (str): The search query text
            cap (int): Maximum number of searches to retain per user (default 20)
        """
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO recent_searches (user_name, query_text) VALUES (?, ?)",
                        (user_name, query_text))
            # trim to cap most-recent per user
            cur.execute(
                "DELETE FROM recent_searches WHERE user_name = ? AND recent_id NOT IN "
                "(SELECT recent_id FROM recent_searches WHERE user_name = ? "
                " ORDER BY recent_id DESC LIMIT ?)",
                (user_name, user_name, cap))

    def get_recent_searches(self, user_name):
        """Get recent search queries for a user, most recent first.

        Args:
            user_name (str): User to query

        Returns:
            list: List of query strings, most recent first
        """
        with self.get_connection(write=False) as conn:
            return [r[0] for r in conn.execute(
                "SELECT query_text FROM recent_searches WHERE user_name = ? "
                "ORDER BY recent_id DESC", (user_name,)).fetchall()]

    # ======================
    # METADATA FIELD CRUD (EP4)
    # ======================

    _FIELD_UPDATE = {"label", "field_type", "choices_json", "required", "sort_order"}

    def create_metadata_field(self, stack_fk, key, label, field_type, choices=None,
                              required=False, sort_order=0):
        import json
        validate_field_type(field_type, choices)
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO metadata_fields (stack_fk, key, label, field_type, "
                "choices_json, required, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (stack_fk, key, label, field_type,
                 json.dumps(choices) if choices else None,
                 1 if required else 0, sort_order))
            return cur.lastrowid

    def get_metadata_fields(self, stack_fk):
        import json
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM metadata_fields WHERE stack_fk = ? ORDER BY sort_order, field_id",
                (stack_fk,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["choices"] = json.loads(d["choices_json"]) if d["choices_json"] else []
                out.append(d)
            return out

    def update_metadata_field(self, field_id, **fields):
        updates = {k: v for k, v in fields.items() if k in self._FIELD_UPDATE}
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE metadata_fields SET {} WHERE field_id = ?".format(set_clause),
                list(updates.values()) + [field_id])

    def delete_metadata_field(self, field_id):
        """Delete a metadata field definition and its values (EP4 I1 fix).

        Because ``metadata_fields`` allows the same ``key`` to exist in
        multiple stacks (UNIQUE(stack_fk, key)), scoping the cleanup by key
        alone would wipe that key's element values/defaults in EVERY stack.
        Scope all cleanup to this field's own stack_fk.
        """
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT key, stack_fk FROM metadata_fields WHERE field_id = ?",
                              (field_id,)).fetchone()
            if row:
                key, stack_fk = row[0], row[1]
                cur.execute(
                    "DELETE FROM element_metadata WHERE field_key = ? AND element_fk IN "
                    "(SELECT e.element_id FROM elements e JOIN lists l ON e.list_fk = l.list_id "
                    "WHERE l.stack_fk = ?)",
                    (key, stack_fk))
                cur.execute(
                    "DELETE FROM metadata_defaults WHERE field_key = ? AND ("
                    "(scope_type = 'stack' AND scope_id = ?) OR "
                    "(scope_type = 'list' AND scope_id IN "
                    "(SELECT list_id FROM lists WHERE stack_fk = ?)))",
                    (key, stack_fk, stack_fk))
            cur.execute("DELETE FROM metadata_fields WHERE field_id = ?", (field_id,))

    # ======================
    # METADATA VALUES + INHERITANCE (EP4)
    # ======================

    def set_element_metadata(self, element_id, field_key, value):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "INSERT INTO element_metadata (element_fk, field_key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(element_fk, field_key) DO UPDATE SET value = excluded.value",
                (element_id, field_key, value if value is None else str(value)))

    def get_element_metadata(self, element_id):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT field_key, value FROM element_metadata WHERE element_fk = ?",
                (element_id,)).fetchall()
            return {r[0]: r[1] for r in rows}

    def set_metadata_default(self, scope_type, scope_id, field_key, value):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "INSERT INTO metadata_defaults (scope_type, scope_id, field_key, value) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(scope_type, scope_id, field_key) DO UPDATE SET value = excluded.value",
                (scope_type, scope_id, field_key, value))

    def _list_ancestry(self, list_id, conn):
        """Return ([list_id, parent, grandparent, ...] nearest-first, stack_fk)."""
        chain, cur_id, stack_fk = [], list_id, None
        while cur_id is not None:
            row = conn.execute("SELECT list_id, parent_list_fk, stack_fk FROM lists WHERE list_id = ?",
                               (cur_id,)).fetchone()
            if not row:
                break
            chain.append(row["list_id"])
            stack_fk = row["stack_fk"]
            cur_id = row["parent_list_fk"]
        return chain, stack_fk

    def get_effective_metadata(self, element_id):
        with self.get_connection(write=False) as conn:
            el = conn.execute("SELECT list_fk FROM elements WHERE element_id = ?",
                              (element_id,)).fetchone()
            if not el:
                return {}
            list_chain, stack_fk = self._list_ancestry(el["list_fk"], conn)
            fields = conn.execute("SELECT key FROM metadata_fields WHERE stack_fk = ?",
                                  (stack_fk,)).fetchall()
            overrides = {r[0]: r[1] for r in conn.execute(
                "SELECT field_key, value FROM element_metadata WHERE element_fk = ?",
                (element_id,)).fetchall()}
            result = {}
            for f in fields:
                key = f[0]
                if key in overrides:
                    result[key] = overrides[key]
                    continue
                val = None
                for lid in list_chain:   # nearest list first
                    row = conn.execute(
                        "SELECT value FROM metadata_defaults WHERE scope_type='list' "
                        "AND scope_id=? AND field_key=?", (lid, key)).fetchone()
                    if row:
                        val = row[0]; break
                if val is None:
                    row = conn.execute(
                        "SELECT value FROM metadata_defaults WHERE scope_type='stack' "
                        "AND scope_id=? AND field_key=?", (stack_fk, key)).fetchone()
                    if row:
                        val = row[0]
                result[key] = val
            return result

    # ======================
    # METADATA TEMPLATES (EP4)
    # ======================

    def create_metadata_template(self, stack_fk, name, values):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO metadata_templates (stack_fk, name, values_json) VALUES (?, ?, ?)",
                (stack_fk, name, json.dumps(values)))
            return cur.lastrowid

    def get_metadata_templates(self, stack_fk):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM metadata_templates WHERE stack_fk = ? ORDER BY name",
                (stack_fk,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["values"] = json.loads(d["values_json"])
                out.append(d)
            return out

    def apply_template(self, element_id, template_id):
        with self.get_connection(write=True) as conn:
            row = conn.execute(
                "SELECT values_json FROM metadata_templates WHERE template_id = ?",
                (template_id,)).fetchone()
            if not row:
                return
            values = json.loads(row[0])
            tmpl_tags = values.pop("tags", "")
            for key, val in values.items():
                conn.execute(
                    "INSERT INTO element_metadata (element_fk, field_key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(element_fk, field_key) DO UPDATE SET value = excluded.value",
                    (element_id, key, str(val)))
            if tmpl_tags:
                cur = conn.execute("SELECT tags FROM elements WHERE element_id = ?", (element_id,))
                existing = (cur.fetchone()[0] or "")
                merged = self._merge_tags(existing, tmpl_tags)
                conn.execute("UPDATE elements SET tags = ? WHERE element_id = ?", (merged, element_id))

    @staticmethod
    def _merge_tags(existing, added):
        cur = [t.strip() for t in (existing or "").split(",") if t.strip()]
        for t in [x.strip() for x in (added or "").split(",") if x.strip()]:
            if t not in cur:
                cur.append(t)
        return ",".join(cur)

    def delete_metadata_template(self, template_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM metadata_templates WHERE template_id = ?", (template_id,))

    # ======================
    # AUTOTAG RULES (EP4)
    # ======================

    def create_autotag_rule(self, pattern, match_type, tags="", field_values=None,
                             stack_fk=None, sort_order=0):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO autotag_rules (stack_fk, pattern, match_type, tags, "
                "field_values_json, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (stack_fk, pattern, match_type, tags,
                 json.dumps(field_values or {}), sort_order))
            return cur.lastrowid

    def get_autotag_rules(self, stack_fk=None):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM autotag_rules WHERE stack_fk IS ? OR stack_fk IS NULL "
                "ORDER BY sort_order, rule_id", (stack_fk,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["fields"] = json.loads(d["field_values_json"]) if d["field_values_json"] else {}
                out.append(d)
            return out

    def delete_autotag_rule(self, rule_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM autotag_rules WHERE rule_id = ?", (rule_id,))

    # ======================
    # QUALITY RULES (EP4)
    # ======================

    def create_quality_rule(self, kind, config, stack_fk=None):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO quality_rules (stack_fk, kind, config_json) VALUES (?, ?, ?)",
                (stack_fk, kind, json.dumps(config)))
            return cur.lastrowid

    def get_quality_rules(self, stack_fk=None):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM quality_rules WHERE stack_fk IS ? OR stack_fk IS NULL",
                (stack_fk,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["config"] = json.loads(d["config_json"])
                out.append(d)
            return out

    def naming_pattern_for_stack(self, stack_fk):
        """Return the stack's `naming_regex` quality-rule pattern, if any (EP4).

        ``get_quality_rules`` has no ORDER BY, so when both a stack-scoped
        and a global (stack_fk IS NULL) naming_regex rule exist the winner
        would otherwise be undefined (I4 fix). Deterministically prefer the
        rule whose stack_fk matches this stack; fall back to the global one.
        """
        stack_pattern = None
        global_pattern = None
        for rule in self.get_quality_rules(stack_fk):
            if rule.get("kind") != "naming_regex":
                continue
            pattern = (rule.get("config") or {}).get("pattern")
            if not pattern:
                continue
            if rule.get("stack_fk") == stack_fk and stack_pattern is None:
                stack_pattern = pattern
            elif rule.get("stack_fk") is None and global_pattern is None:
                global_pattern = pattern
        return stack_pattern if stack_pattern is not None else global_pattern

    def check_element_quality(self, element_id):
        from metadata_rules import check_element_quality as _check_element_quality
        el = self.get_element_by_id(element_id)
        if not el:
            return []
        with self.get_connection(write=False) as conn:
            lst = conn.execute("SELECT stack_fk FROM lists WHERE list_id = ?",
                               (el["list_fk"],)).fetchone()
        stack_fk = lst["stack_fk"] if lst else None
        fields = self.get_metadata_fields(stack_fk) if stack_fk else []
        effective = self.get_effective_metadata(element_id)
        rules = self.get_quality_rules(stack_fk)
        return _check_element_quality(el, effective, fields, rules)

    def get_quality_summary(self, list_id):
        total = 0
        for el in self.get_elements_by_list(list_id):
            total += len(self.check_element_quality(el["element_id"]))
        return {"issues": total}

    # ======================
    # ELEMENT RELATIONSHIPS (EP4)
    # ======================

    def add_relationship(self, from_id, to_id, rel_type):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO element_relationships "
                "(from_element_fk, to_element_fk, rel_type) VALUES (?, ?, ?)",
                (from_id, to_id, rel_type))
            return cur.lastrowid

    def get_relationships(self, element_id):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT rel_id, from_element_fk, to_element_fk, rel_type "
                "FROM element_relationships WHERE from_element_fk = ? OR to_element_fk = ?",
                (element_id, element_id)).fetchall()
            return [dict(r) for r in rows]

    def remove_relationship(self, rel_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM element_relationships WHERE rel_id = ?", (rel_id,))

    # ======================
    # INGEST JOB LEDGER (EP6)
    # ======================

    _FINISHED_JOB_STATES = ("done", "skipped", "cancelled")

    def create_job(self, kind, source_path, target_list_id=None, recipe_id=None,
                   payload=None, status="pending"):
        import json
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ingest_jobs (kind, source_path, target_list_id, recipe_id, "
                "status, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (kind, source_path, target_list_id, recipe_id, status,
                 json.dumps(payload) if payload is not None else None))
            return cur.lastrowid

    def _row_to_job(self, row):
        import json
        d = dict(row)
        d["payload"] = json.loads(d["payload_json"]) if d.get("payload_json") else None
        return d

    def get_job(self, job_id):
        with self.get_connection(write=False) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE job_id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None

    def get_jobs(self, status=None, limit=200):
        with self.get_connection(write=False) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM ingest_jobs WHERE status = ? ORDER BY job_id LIMIT ?",
                    (status, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ingest_jobs ORDER BY job_id LIMIT ?", (limit,)).fetchall()
            return [self._row_to_job(r) for r in rows]

    def update_job_status(self, job_id, status, message=None):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE ingest_jobs SET status = ?, message = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (status, message, job_id))

    def bump_job_attempt(self, job_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE ingest_jobs SET attempts = attempts + 1, status = 'running', "
                "updated_at = CURRENT_TIMESTAMP WHERE job_id = ?", (job_id,))

    def count_jobs_by_status(self):
        with self.get_connection(write=False) as conn:
            return {r[0]: r[1] for r in conn.execute(
                "SELECT status, COUNT(*) FROM ingest_jobs GROUP BY status").fetchall()}

    def clear_finished_jobs(self):
        placeholders = ",".join("?" for _ in self._FINISHED_JOB_STATES)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM ingest_jobs WHERE status IN ({})".format(placeholders),
                list(self._FINISHED_JOB_STATES))

    # ======================
    # NOTIFICATION CENTER (EP6)
    # ======================

    def add_notification(self, title, body=None, level="info"):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO notifications (level, title, body) VALUES (?, ?, ?)",
                (level, title, body))
            return cur.lastrowid

    def get_notifications(self, unread_only=False, limit=100):
        sql = "SELECT * FROM notifications"
        if unread_only:
            sql += " WHERE is_read = 0"
        sql += " ORDER BY notification_id DESC LIMIT ?"
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]

    def unread_notification_count(self):
        with self.get_connection(write=False) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE is_read = 0").fetchone()[0]

    def mark_notifications_read(self):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")

    # ======================
    # WATCH FOLDERS (EP6)
    # ======================

    _WATCH_FIELDS = {"path", "target_list_id", "recipe_id", "interval_sec", "enabled"}

    def create_watch_folder(self, path, target_list_id=None, recipe_id=None,
                             interval_sec=30, enabled=True):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO watch_folders (path, target_list_id, recipe_id, interval_sec, enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                (path, target_list_id, recipe_id, interval_sec, 1 if enabled else 0))
            return cur.lastrowid

    def get_watch_folders(self, enabled_only=False):
        sql = "SELECT * FROM watch_folders"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY watch_id"
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def update_watch_folder(self, watch_id, **fields):
        updates = {k: v for k, v in fields.items() if k in self._WATCH_FIELDS}
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE watch_folders SET {} WHERE watch_id = ?".format(set_clause),
                list(updates.values()) + [watch_id])

    def delete_watch_folder(self, watch_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM watch_folders WHERE watch_id = ?", (watch_id,))

    def set_watch_last_scan(self, watch_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE watch_folders SET last_scan = CURRENT_TIMESTAMP WHERE watch_id = ?",
                (watch_id,))

    # ======================
    # INGEST RECIPES (EP6)
    # ======================

    _RECIPE_FIELDS = {"name", "values_json", "sort_order"}

    def create_ingest_recipe(self, name, values, sort_order=0):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ingest_recipes (name, values_json, sort_order) VALUES (?, ?, ?)",
                (name, json.dumps(values), sort_order))
            return cur.lastrowid

    def get_ingest_recipes(self):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM ingest_recipes ORDER BY sort_order, name").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["values"] = json.loads(d["values_json"])
                out.append(d)
            return out

    def update_ingest_recipe(self, recipe_id, **fields):
        if "values" in fields:
            fields["values_json"] = json.dumps(fields.pop("values"))
        updates = {k: v for k, v in fields.items() if k in self._RECIPE_FIELDS}
        if not updates:
            return
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "UPDATE ingest_recipes SET {} WHERE recipe_id = ?".format(set_clause),
                list(updates.values()) + [recipe_id])

    def delete_ingest_recipe(self, recipe_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM ingest_recipes WHERE recipe_id = ?", (recipe_id,))

    def resolve_recipe_config(self, recipe_values, base_config):
        """Overlay a recipe's values onto base_config, then resolve its
        proxy_profile_id -> PreviewWorker config keys and its
        action_chain_id -> action_chain_steps. Returns a new dict."""
        from ingest_automation import apply_recipe_to_config, profile_to_config_overlay
        recipe_values = recipe_values or {}
        cfg = apply_recipe_to_config(recipe_values, base_config)
        ppid = recipe_values.get('proxy_profile_id')
        if ppid:
            prof = next((p for p in self.get_proxy_profiles()
                         if p.get('profile_id') == ppid), None)
            if prof:
                cfg.update(profile_to_config_overlay(prof))
        acid = recipe_values.get('action_chain_id')
        if acid:
            chain = next((c for c in self.get_action_chains()
                          if c.get('chain_id') == acid), None)
            if chain:
                cfg['action_chain_steps'] = chain.get('steps')
        return cfg

    # ======================
    # PROXY PROFILES (EP6)
    # ======================

    def create_proxy_profile(self, name, kind="mp4", max_size=512, fps=24,
                             duration=None, sort_order=0):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO proxy_profiles (name, kind, max_size, fps, duration, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, kind, max_size, fps, duration, sort_order))
            return cur.lastrowid

    def get_proxy_profiles(self):
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM proxy_profiles ORDER BY sort_order, name").fetchall()]

    def delete_proxy_profile(self, profile_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM proxy_profiles WHERE profile_id = ?", (profile_id,))

    # ======================
    # ACTION CHAINS (EP6)
    # ======================

    def create_action_chain(self, name, steps, sort_order=0):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO action_chains (name, steps_json, sort_order) VALUES (?, ?, ?)",
                (name, json.dumps(steps), sort_order))
            return cur.lastrowid

    def get_action_chains(self):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM action_chains ORDER BY sort_order, name").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["steps"] = json.loads(d["steps_json"])
                out.append(d)
            return out

    def delete_action_chain(self, chain_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM action_chains WHERE chain_id = ?", (chain_id,))

    # ======================
    # ELEMENT EMBEDDINGS (EP7 — AI discovery)
    # ======================

    def store_element_embedding(self, element_id, model_id, vector):
        import numpy as np
        arr = np.asarray(vector, dtype=np.float32).reshape(-1)
        with self.get_connection(write=True) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO element_embeddings (element_fk, model_id, dim, vector) "
                "VALUES (?, ?, ?, ?)",
                (element_id, model_id, int(arr.shape[0]), arr.tobytes()))

    def get_element_embedding(self, element_id):
        import numpy as np
        with self.get_connection(write=False) as conn:
            row = conn.execute(
                "SELECT vector FROM element_embeddings WHERE element_fk = ?",
                (element_id,)).fetchone()
        if not row:
            return None
        return np.frombuffer(row["vector"], dtype=np.float32)

    def get_all_embeddings(self, model_id=None):
        """Return (ids: list[int], matrix: np.ndarray[N, dim]) for cosine search."""
        import numpy as np
        sql = "SELECT element_fk, vector FROM element_embeddings"
        params = []
        if model_id:
            sql += " WHERE model_id = ?"
            params.append(model_id)
        ids, vecs = [], []
        with self.get_connection(write=False) as conn:
            for r in conn.execute(sql, params).fetchall():
                ids.append(r["element_fk"])
                vecs.append(np.frombuffer(r["vector"], dtype=np.float32))
        if not vecs:
            return [], np.zeros((0, 0), dtype=np.float32)
        return ids, np.vstack(vecs)

    def get_elements_missing_embedding(self, model_id):
        """Elements never embedded OR embedded under a different model_id."""
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT e.element_id FROM elements e "
                "LEFT JOIN element_embeddings em ON em.element_fk = e.element_id "
                "WHERE em.element_fk IS NULL OR em.model_id != ? "
                "ORDER BY e.element_id",
                (model_id,)).fetchall()
        return [r[0] for r in rows]

    # ======================
    # ELEMENT COLORS (EP7 — non-AI color search, F004)
    # ======================

    def store_element_color(self, element_id, histogram, dominant=None):
        import json
        import numpy as np
        blob = np.asarray(histogram, dtype=np.float32).reshape(-1).tobytes()
        dom = json.dumps(dominant) if dominant is not None else None
        with self.get_connection(write=True) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO element_colors (element_fk, histogram, dominant) "
                "VALUES (?, ?, ?)", (element_id, blob, dom))

    def get_all_colors(self):
        import numpy as np
        ids, hists = [], []
        with self.get_connection(write=False) as conn:
            for r in conn.execute("SELECT element_fk, histogram FROM element_colors").fetchall():
                ids.append(r["element_fk"])
                hists.append(np.frombuffer(r["histogram"], dtype=np.float32))
        if not hists:
            return [], np.zeros((0, 0), dtype=np.float32)
        return ids, np.vstack(hists)

    # ======================
    # ROLES / PERMISSIONS (EP8 — granular team-collaboration roles)
    # ======================

    def seed_builtin_roles(self):
        """Insert any missing built-in roles + their default permissions. Idempotent.

        Seeding is also guaranteed by the v21 schema migration on fresh/upgraded
        DBs (see db_migrations._seed_builtin_roles); this method exists for
        public-API completeness / re-seeding on demand.
        """
        with self.get_connection() as conn:
            from db_migrations import _seed_builtin_roles
            _seed_builtin_roles(conn)
            conn.commit()

    def create_role(self, name, label=None, permissions=None):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO roles (name, label, is_builtin) VALUES (?, ?, 0)",
                        (name, label or name.capitalize()))
            role_id = cur.lastrowid
            for p in (permissions or set()):
                if is_valid_permission(p):
                    cur.execute("INSERT OR IGNORE INTO role_permissions (role_fk, permission) "
                                "VALUES (?, ?)", (role_id, p))
            conn.commit()
            return role_id

    def get_roles(self):
        with self.get_connection() as conn:
            cur = conn.cursor()
            roles = [dict(r) for r in cur.execute(
                "SELECT * FROM roles ORDER BY is_builtin DESC, name").fetchall()]
            for r in roles:
                r["permissions"] = [row[0] for row in cur.execute(
                    "SELECT permission FROM role_permissions WHERE role_fk = ?",
                    (r["role_id"],)).fetchall()]
            return roles

    def get_role_permissions(self, role_name):
        with self.get_connection() as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT role_id FROM roles WHERE name = ?", (role_name,)).fetchone()
            if not row:
                return set()
            return {r[0] for r in cur.execute(
                "SELECT permission FROM role_permissions WHERE role_fk = ?", (row[0],)).fetchall()}

    def set_role_permissions(self, role_name, permissions):
        with self.get_connection() as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT role_id FROM roles WHERE name = ?", (role_name,)).fetchone()
            if not row:
                return
            role_id = row[0]
            cur.execute("DELETE FROM role_permissions WHERE role_fk = ?", (role_id,))
            for p in permissions:
                if is_valid_permission(p):
                    cur.execute("INSERT INTO role_permissions (role_fk, permission) VALUES (?, ?)",
                                (role_id, p))
            conn.commit()

    def delete_role(self, role_name):
        with self.get_connection() as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT role_id, is_builtin FROM roles WHERE name = ?",
                              (role_name,)).fetchone()
            if not row:
                return
            if row[1]:
                raise ValueError("Cannot delete built-in role: {}".format(role_name))
            cur.execute("DELETE FROM roles WHERE role_id = ?", (row[0],))
            conn.commit()

    def has_permission(self, username, permission):
        user = self.get_user_by_username(username)
        if not user:
            return False
        role = user.get("role")
        if role == "admin":
            return True
        return permission in self.get_role_permissions(role)

    # ======================
    # ACTIVITY LOG (EP8 — team-collaboration audit feed)
    # ======================

    def log_activity(self, actor, action, target_type=None, target_id=None, detail=None):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO activity_log (actor, action, target_type, target_id, detail) "
                "VALUES (?, ?, ?, ?, ?)", (actor, action, target_type, target_id, detail))
            conn.commit()
            return cur.lastrowid

    def get_activity(self, limit=100, action=None, actor=None, target_type=None):
        clauses, params = [], []
        if action is not None:
            clauses.append("action = ?"); params.append(action)
        if actor is not None:
            clauses.append("actor = ?"); params.append(actor)
        if target_type is not None:
            clauses.append("target_type = ?"); params.append(target_type)
        where = " AND ".join(clauses) if clauses else "1=1"
        sql = ("SELECT * FROM activity_log WHERE {} "
               "ORDER BY at DESC, activity_id DESC LIMIT ?".format(where))
        params.append(limit)
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

