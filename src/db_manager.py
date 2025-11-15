# -*- coding: utf-8 -*-
"""
Database Manager for VFX_Asset_Hub
Handles SQLite operations with network-aware file locking
Python 2.7 compatible
"""

import sqlite3
import os
import time
import json
from contextlib import contextmanager


class DatabaseManager(object):
    """
    Manages SQLite database operations for VFX_Asset_Hub.
    Implements network-aware file locking and connection pooling.
    """
    
    def __init__(self, db_path):
        """
        Initialize database manager.
        
        Args:
            db_path (str): Path to SQLite database file
        """
        self.db_path = db_path
        self.max_retries = 5
        self.retry_delay = 0.5  # seconds
        
        # Ensure database directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        # Initialize schema if database doesn't exist
        if not os.path.exists(db_path):
            self._create_schema()
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections with retry logic.
        Implements file locking for network-shared databases.
        
        Yields:
            sqlite3.Connection: Database connection
        """
        conn = None
        for attempt in range(self.max_retries):
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=30.0,  # 30 second timeout for locks
                    isolation_level='DEFERRED'
                )
                conn.row_factory = sqlite3.Row  # Enable dict-like access
                # Enable foreign keys
                conn.execute("PRAGMA foreign_keys = ON")
                yield conn
                conn.commit()
                break
            except sqlite3.OperationalError as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
            finally:
                if conn:
                    conn.close()
    
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
            
            # Table 2: Lists (Sub-Categories)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lists (
                    list_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stack_fk INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stack_fk) REFERENCES stacks(stack_id) ON DELETE CASCADE
                )
            """)
            
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    playlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table 6: Playlist Items (Many-to-many)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlist_items (
                    playlist_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_fk INTEGER NOT NULL,
                    element_fk INTEGER NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lists_stack ON lists(stack_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_list ON elements(list_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_type ON elements(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_name ON elements(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_element ON favorites(element_fk)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_element ON ingestion_history(element_fk)")
    
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
    
    def create_list(self, stack_id, name):
        """
        Create a new list within a stack.
        
        Args:
            stack_id (int): Parent stack ID
            name (str): List name
            
        Returns:
            int: list_id of created list
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO lists (stack_fk, name) VALUES (?, ?)",
                (stack_id, name)
            )
            return cursor.lastrowid
    
    def get_lists_by_stack(self, stack_id):
        """
        Get all lists for a stack.
        
        Args:
            stack_id (int): Stack ID
            
        Returns:
            list: List of list dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM lists WHERE stack_fk = ? ORDER BY name",
                (stack_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_list_by_id(self, list_id):
        """Get list by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lists WHERE list_id = ?", (list_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
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
                          'preview_path', 'is_deprecated', 'file_size']:
                    fields.append(key)
                    values.append(value)
            
            placeholders = ','.join(['?'] * len(values))
            field_names = ','.join(fields)
            
            cursor.execute(
                "INSERT INTO elements ({}) VALUES ({})".format(field_names, placeholders),
                values
            )
            return cursor.lastrowid
    
    def get_elements_by_list(self, list_id, include_deprecated=False):
        """
        Get all elements for a list.
        
        Args:
            list_id (int): List ID
            include_deprecated (bool): Include deprecated elements
            
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
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
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
