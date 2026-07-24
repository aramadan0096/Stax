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

        Args:
            limit (int): Maximum number of results.

        Returns:
            list: List of element dicts.
        """
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM elements ORDER BY created_at DESC, element_id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def update_element(self, element_id, **kwargs):
        """
        Update element fields.
        
        Args:
            element_id (int): Element ID
            **kwargs: Fields to update
            
        Returns:
            bool: True if updated
        """
        updates = {
            k: v for k, v in kwargs.items() if k in self.UPDATABLE_ELEMENT_COLUMNS
        }
        if not updates:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()

            set_clause = ', '.join(["{} = ?".format(k) for k in updates.keys()])
            values = list(updates.values()) + [element_id]
            
            cursor.execute(
                "UPDATE elements SET {} WHERE element_id = ?".format(set_clause),
                values
            )
            return cursor.rowcount > 0
    
    def delete_element(self, element_id):
        """Delete element."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM elements WHERE element_id = ?", (element_id,))
            return cursor.rowcount > 0

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
    
    def log_ingestion(self, action, source_path, target_list, status, message=None, element_id=None):
        """
        Log an ingestion event.
        
        Args:
            action (str): Action performed
            source_path (str): Source file path
            target_list (str): Target list name
            status (str): 'success' or 'error'
            message (str): Optional message
            element_id (int): Optional element ID if created
            
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
            return cursor.lastrowid
    
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


