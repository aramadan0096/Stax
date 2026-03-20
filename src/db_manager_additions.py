# -*- coding: utf-8 -*-
"""
StaX — DatabaseManager additions
==================================
This file contains ALL new methods that need to be added to the existing
DatabaseManager class inside src/db_manager.py.

HOW TO APPLY
------------
Open src/db_manager.py and paste each method below into the DatabaseManager
class body.  Do NOT replace existing methods — these are purely additive.

Also add the following two lines near the top of DatabaseManager.__init__,
AFTER the call to self._create_tables():

    from src.db_migrations import run_migrations
    run_migrations(self.conn)

That one addition activates the entire migration system and creates all new
columns and tables automatically on first run.
"""

# ============================================================
#  Paste the following methods into the DatabaseManager class
# ============================================================

# NOTE: In the actual class these would be indented under `class DatabaseManager:`

def execute(self, sql, params=()):
    """
    Execute an arbitrary SQL statement against the connection.
    Used by the API server and analytics logger for raw writes.

    Parameters
    ----------
    sql    : str
    params : tuple

    Returns
    -------
    sqlite3.Cursor
    """
    with self._lock:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur


# ------------------------------------------------------------------ phash / duplicates

def update_element_phash(self, element_id, phash):
    """Store the perceptual hash for an element (Feature 3)."""
    with self._lock:
        self.conn.execute(
            "UPDATE Elements SET phash = ? WHERE element_id = ?",
            (phash, element_id),
        )
        self.conn.commit()


def get_elements_with_phash(self):
    """
    Return all elements that have a stored phash.
    Used by duplicate_detection.find_duplicates().
    """
    with self._lock:
        cur = self.conn.execute(
            "SELECT element_id, name, list_fk, format, phash, preview_path "
            "FROM Elements WHERE phash IS NOT NULL AND phash != ''"
        )
        return [dict(row) for row in cur.fetchall()]


# ------------------------------------------------------------------ batch edit

def update_element_metadata(self, element_id, **kwargs):
    """
    Update one or more metadata fields on an element.
    Used by BatchEditDialog (Feature 5) and the REST API PATCH endpoint.

    Allowed kwargs: name, tags, comment, type, is_deprecated,
                    list_fk, deprecated_reason
    """
    allowed = {
        "name", "tags", "comment", "type",
        "is_deprecated", "list_fk", "deprecated_reason",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    columns = ", ".join("{} = ?".format(k) for k in updates)
    values  = list(updates.values()) + [element_id]

    with self._lock:
        self.conn.execute(
            "UPDATE Elements SET {} WHERE element_id = ?".format(columns),
            values,
        )
        self.conn.commit()


# ------------------------------------------------------------------ pagination helpers

def get_elements_by_list(self, list_id, limit=None, offset=0):
    """
    Return elements for a list.  *limit* and *offset* enable server-side
    pagination so the UI never loads more rows than it needs (Feature 2).

    If limit is None the original all-rows behaviour is preserved.
    """
    with self._lock:
        if limit is not None:
            cur = self.conn.execute(
                "SELECT * FROM Elements WHERE list_fk = ? AND is_deprecated = 0 "
                "ORDER BY element_id "
                "LIMIT ? OFFSET ?",
                (list_id, limit, offset),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM Elements WHERE list_fk = ? AND is_deprecated = 0 "
                "ORDER BY element_id",
                (list_id,),
            )
        return [dict(row) for row in cur.fetchall()]


def count_elements_by_list(self, list_id):
    """Return the total count of non-deprecated elements in a list."""
    with self._lock:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM Elements "
            "WHERE list_fk = ? AND is_deprecated = 0",
            (list_id,),
        )
        row = cur.fetchone()
        return row[0] if row else 0


# ------------------------------------------------------------------ analytics

def get_top_inserted_elements(self, n=20):
    """
    Return the top N most-inserted elements with their insertion counts.
    Used by AnalyticsPanel and the REST API /analytics/top endpoint.

    Returns
    -------
    list[dict]  keys: element_id, name, list_name, format, type, count
    """
    with self._lock:
        cur = self.conn.execute(
            """
            SELECT
                e.element_id,
                e.name,
                l.name   AS list_name,
                e.format,
                e.type,
                COUNT(i.log_id) AS count
            FROM InsertionLog i
            JOIN Elements e ON e.element_id = i.element_fk
            LEFT JOIN Lists l ON l.list_id = e.list_fk
            GROUP BY i.element_fk
            ORDER BY count DESC
            LIMIT ?
            """,
            (n,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_insertions_by_month(self):
    """
    Return insertion counts aggregated by calendar month.
    Used by AnalyticsPanel "Over Time" chart.

    Returns
    -------
    list[dict]  keys: month (YYYY-MM), count
    """
    with self._lock:
        cur = self.conn.execute(
            """
            SELECT
                strftime('%Y-%m', inserted_at) AS month,
                COUNT(*)                        AS count
            FROM InsertionLog
            GROUP BY month
            ORDER BY month ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def get_insertions_by_user(self):
    """
    Return insertion counts per user.

    Returns
    -------
    list[dict]  keys: username, count, last_active
    """
    with self._lock:
        cur = self.conn.execute(
            """
            SELECT
                COALESCE(u.username, 'Guest')   AS username,
                COUNT(i.log_id)                 AS count,
                MAX(i.inserted_at)              AS last_active
            FROM InsertionLog i
            LEFT JOIN Users u ON u.user_id = i.user_fk
            GROUP BY i.user_fk
            ORDER BY count DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def get_total_insertions(self):
    """Return the total number of rows in InsertionLog."""
    with self._lock:
        cur = self.conn.execute("SELECT COUNT(*) FROM InsertionLog")
        row = cur.fetchone()
        return row[0] if row else 0


def search_elements(self, query, prop="name", match="loose"):
    """
    Search elements by a given property.  Used by the REST API.

    Parameters
    ----------
    query : str
    prop  : str   one of 'name', 'format', 'type', 'comment', 'tags'
    match : str   'loose' (LIKE %q%) or 'strict' (exact)
    """
    allowed_props = {"name", "format", "type", "comment", "tags"}
    if prop not in allowed_props:
        prop = "name"

    with self._lock:
        if match == "strict":
            cur = self.conn.execute(
                "SELECT * FROM Elements WHERE {} = ?".format(prop),
                (query,),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM Elements WHERE {} LIKE ?".format(prop),
                ("%{}%".format(query),),
            )
        return [dict(row) for row in cur.fetchall()]
