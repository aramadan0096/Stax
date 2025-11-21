# -*- coding: utf-8 -*-
"""
Database Manager for StaX
Handles SQLite operations with network-aware file locking
Python 2.7 compatible
"""

import sqlite3
import os
import time
import json
from contextlib import contextmanager
from src.file_lock import FileLockManager


class DatabaseManager(object):
    """
    Manages SQLite database operations for StaX.
    Implements network-aware file locking and connection pooling.
    """
    
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
    
    def _log(self, message):
        """Log message if logging is enabled."""
        if self.enable_logging:
            print("[DB] {}".format(message))
    
    @contextmanager
    def get_connection(self):
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
            # Acquire external file lock if enabled (for network shares)
            if self.use_file_lock:
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
                    conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
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
                except:
                    pass
            
            # Release file lock if acquired
            if file_lock:
                try:
                    file_lock.release()
                    self._log("File lock released")
                except:
                    pass
    
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
                    last_login TIMESTAMP
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
            
            # Create default admin user if no users exist (password: "admin")
            cursor.execute("SELECT COUNT(*) as count FROM users")
            if cursor.fetchone()['count'] == 0:
                import hashlib
                password_hash = hashlib.sha256("admin".encode('utf-8')).hexdigest()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("admin", password_hash, "admin")
                )
                self._log("Default admin user created (username: admin, password: admin)")
            
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
                        last_login TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                
                # Create default admin user
                import hashlib
                password_hash = hashlib.sha256("admin".encode('utf-8')).hexdigest()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("admin", password_hash, "admin")
                )
                self._log("Migration 3: Complete - Default admin user created")
            
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
                    # Try to copy existing data mapping older column names if present
                    try:
                        cursor.execute("PRAGMA table_info(playlist_items)")
                        cols = [r[1] for r in cursor.fetchall()]
                        select_cols = []
                        if 'playlist_fk' in cols:
                            select_cols.append('playlist_fk')
                        else:
                            select_cols.append('playlist')
                        if 'element_fk' in cols:
                            select_cols.append('element_fk')
                        else:
                            select_cols.append('element')
                        if 'order_index' in cols:
                            select_cols.append('order_index')
                        elif 'sort_order' in cols:
                            select_cols.append('sort_order')
                        else:
                            select_cols.append('0')

                        # Build copy statement defensively
                        copy_sql = "INSERT INTO playlist_items_new (playlist_fk, element_fk, order_index, added_at) SELECT {cols}, COALESCE(created_at, CURRENT_TIMESTAMP) FROM playlist_items".format(cols=','.join(select_cols))
                        try:
                            cursor.execute(copy_sql)
                        except Exception:
                            # Fallback: naive copy of playlist_fk, element_fk
                            try:
                                cursor.execute("INSERT INTO playlist_items_new (playlist_fk, element_fk) SELECT playlist_fk, element_fk FROM playlist_items")
                            except Exception:
                                pass

                    except Exception as e:
                        self._log("Migration 6: Data copy failed: {}".format(str(e)))

                    # Replace old table
                    try:
                        cursor.execute("ALTER TABLE playlist_items RENAME TO playlist_items_old")
                        cursor.execute("ALTER TABLE playlist_items_new RENAME TO playlist_items")
                        cursor.execute("DROP TABLE IF EXISTS playlist_items_old")
                    except Exception as e:
                        self._log("Migration 6: Table swap failed: {}".format(str(e)))
                    self._log("Migration 6: Complete")
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

            self._log("All migrations applied successfully")
    
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stacks ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stack_by_id(self, stack_id):
        """Get stack by ID."""
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM lists WHERE parent_list_fk = ? ORDER BY name",
                (parent_list_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_list_by_id(self, list_id):
        """Get list by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lists WHERE list_id = ?", (list_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_list_hierarchy(self, list_id):
        """Return list ancestors from top-level to the specified list."""
        hierarchy = []
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) FROM elements WHERE list_fk = ?"
            params = [list_id]
            
            if not include_deprecated:
                query += " AND is_deprecated = 0"
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]
    
    def get_element_by_id(self, element_id):
        """Get element by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM elements WHERE element_id = ?", (element_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_element(self, element_id, **kwargs):
        """
        Update element fields.
        
        Args:
            element_id (int): Element ID
            **kwargs: Fields to update
            
        Returns:
            bool: True if updated
        """
        if not kwargs:
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join(["{} = ?".format(k) for k in kwargs.keys()])
            values = list(kwargs.values()) + [element_id]
            
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if match_type == 'loose':
                query = "SELECT * FROM elements WHERE {} LIKE ? ORDER BY name".format(property_name)
                cursor.execute(query, ('%' + search_text + '%',))
            else:  # strict
                query = "SELECT * FROM elements WHERE {} = ? ORDER BY name".format(property_name)
                cursor.execute(query, (search_text,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ======================
    # FAVORITES OPERATIONS
    # ======================
    
    def add_favorite(self, element_id, machine_name, user_name=None):
        """Add element to favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO favorites (element_fk, machine_name, user_name) VALUES (?, ?, ?)",
                (element_id, machine_name, user_name)
            )
            return cursor.lastrowid
    
    def remove_favorite(self, element_id, machine_name, user_name=None):
        """Remove element from favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM favorites WHERE element_fk = ? AND machine_name = ? AND user_name IS ?",
                (element_id, machine_name, user_name)
            )
            return cursor.rowcount > 0
    
    def get_favorites(self, machine_name, user_name=None):
        """Get all favorite elements for user/machine."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.* FROM elements e
                JOIN favorites f ON e.element_id = f.element_fk
                WHERE f.machine_name = ? AND f.user_name IS ?
                ORDER BY e.name
            """, (machine_name, user_name))
            return [dict(row) for row in cursor.fetchall()]
    
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        
        with self.get_connection() as conn:
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
        import hashlib
        
        password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        
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
        import hashlib
        
        password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND password_hash = ? AND is_active = 1",
                (username, password_hash)
            )
            row = cursor.fetchone()
            
            if row:
                # Update last login time
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (row['user_id'],)
                )
                conn.commit()
                return dict(row)
            
            return None
    
    def get_user_by_id(self, user_id):
        """
        Get user by ID.
        
        Args:
            user_id (int): User ID
            
        Returns:
            dict: User dict or None
        """
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        import hashlib
        
        password_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            return {row['key']: row['value'] for row in rows}


