# EP8 — Team Collaboration (metadata sync first) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real team-collaboration value on top of the already-shared `STOCK_DB`: a **granular role→permission matrix** (F042), an append-only **activity/audit log + Activity dock** (F043), and a portable **metadata + preview bundle** export/import with timestamp conflict handling (F041) — plus a named `CollaborationConnector` seam so the deferred Kitsu/Ftrack/Flow/DCC bridges (F044–F048) can be added later without rework. Everything is **stdlib-only** (`json`, `zipfile`, `shutil`) and **network-free in tests**.

**Architecture:** A Qt-free `permissions.py` holds the permission contract shared with SP4. `DatabaseManager` gains three tables (`roles`, `role_permissions`, `activity_log`), an `elements.updated_at` migration, roles/permissions CRUD, `has_permission`, `log_activity`/`get_activity`, and optional-actor audit hooks in `delete_element`/`log_ingestion`/`update_element`. A Qt-free `src/sync/metadata_bundle.py` serialises a list to a `.staxbundle` zip and merges it back newest-timestamp-wins. `src/sync/connector.py` defines the `CollaborationConnector` ABC + registry and one concrete `LocalBundleConnector`. New widgets (`ActivityPanel`, Roles/Sync settings tabs) are self-contained. All TDD on the SP0 `stax_db`/headless-Qt fixtures.

**Tech Stack:** Python 3.9, SQLite (via `DatabaseManager`), PySide2 (headless offscreen), pytest / pytest-qt, stdlib `json` + `zipfile` + `shutil`.

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat (`from db_manager import …`, `from permissions import …`, `from sync.metadata_bundle import …`). **Logging:** `logging`, not `print`. **Commits:** conventional.
- **No new dependencies.** Bundles use stdlib `zipfile`/`json`/`shutil` only. **No live external SDK** (Kitsu/Ftrack/Flow) is imported anywhere in EP8.
- **All dynamic SQL uses fixed, code-literal column names and parameterized values** (SP1 whitelisting pattern) — never format a user value into SQL.
- **`admin` implies every permission.** `has_permission` short-circuits to `True` for the `admin` role, keeping the existing `check_admin_permission` gate valid.
- **Audit hooks are opt-in and backward-compatible:** the new `actor`/`_actor` params default to `None`; omitting them preserves current behavior and current tests.
- **Sync is explicit export→import** of a `.staxbundle`; **no real-time/cloud sync**. Conflict resolution is whole-element, newest-`updated_at`-wins, with a `{added,updated,skipped}` report.
- **Dependency — SP1:** `get_connection(...)` + migration runner. The code below uses plain `get_connection()` (verified current signature) and the `CREATE TABLE IF NOT EXISTS` idempotent pattern already used by `_apply_migrations`. If SP1 has landed a `write=` kwarg, add it.
- **Dependency — SP4:** granular roles build on SP4's user/session model; `permissions.PERMISSIONS` is the shared contract.
- **Dependency — EP4:** metadata edits are audited via the same `log_activity`; EP4's `set_element_metadata` calls it where present.
- Pure modules (`permissions.py`, `metadata_bundle.py`, `connector.py`) stay Qt-free and network-free (single responsibility, isolated tests).

---

## Key facts (verified against the codebase)

- `get_connection()` is a `@contextmanager` with file locking; current signature takes **no** `write=` kwarg (`src/db_manager.py:81`). DB write idiom: `with self.get_connection() as conn: cursor = conn.cursor(); …`.
- Schema is built in `_create_schema` (`src/db_manager.py:183`) and existing DBs are patched idempotently in `_apply_migrations` (`src/db_manager.py:359`), which uses `try: SELECT col … except sqlite3.OperationalError: ALTER TABLE …` for columns.
- `users` table: `role TEXT NOT NULL CHECK(role IN ('admin','user')) DEFAULT 'user'` (`src/db_manager.py:301`); default `admin/admin` user seeded when empty (`:347`).
- `create_user(username, password, role='user', email=None)` (`:1490`), `authenticate_user` (`:1520`), `get_user_by_username` (`:1570`), `get_all_users` (`:1586`), `update_user(**kwargs)` whitelist `['username','email','role','is_active']` (`:1598`).
- `main.py`: `self.current_user` (dict with `username`/`role`/`user_id`), `self.is_admin` (`:110`), `check_admin_permission(action_name="this action")` (`:527`) — prompts login then shows a styled "Permission Denied" dialog.
- `delete_element(element_id)` (`:863`), `update_element(element_id, **kwargs)` (`:837`), `get_element_by_id(element_id)` (`:829`), `log_ingestion(action, source_path, target_list, status, message=None, element_id=None)` (`:934`).
- `elements` columns include `name,type,format,frame_range,comment,tags,preview_path,gif_preview_path,is_deprecated,created_at` (`:214`) — **no `updated_at` yet** (added in Task 9).
- `get_elements_by_list(list_id, include_deprecated=False, limit=None, offset=0)` (`:777`), `create_stack(name, path)` (`:559`), `get_list_by_id` (`:675`).
- `SettingsPanel.setup_ui` adds tabs via `self.tab_widget.addTab(...)`; Security Admin tab is admin-gated and rebuilt in `refresh_security_tab` (`src/ui/settings_panel.py:56,102,685`); `self.main_window.check_admin_permission()` / `self.main_window.current_user` are the admin signals.
- SP0 fixture `stax_db` builds a real `DatabaseManager` on a temp DB.

---

# Cluster 8A — Granular roles (F042)

## Task 1: `permissions` contract module

**Files:**
- Create: `src/permissions.py`
- Test: `tests/unit/test_ep8_permissions.py`

**Interfaces:**
- Produces: `PERMISSIONS` (tuple), `BUILTIN_ROLES` (dict[str, set]), `is_valid_permission(p) -> bool`, `default_permissions_for(role_name) -> set`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_permissions.py`:

```python
import pytest
from permissions import (PERMISSIONS, BUILTIN_ROLES,
                         is_valid_permission, default_permissions_for)


@pytest.mark.unit
def test_admin_has_every_permission():
    assert BUILTIN_ROLES["admin"] == set(PERMISSIONS)


@pytest.mark.unit
def test_builtin_roles_only_use_valid_permissions():
    for role, perms in BUILTIN_ROLES.items():
        for p in perms:
            assert is_valid_permission(p), "{} -> bad perm {}".format(role, p)


@pytest.mark.unit
def test_default_permissions_for_known_and_unknown():
    assert default_permissions_for("ingestor") == {"can_ingest"}
    assert default_permissions_for("nope") == set()
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_permissions.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/permissions.py`:

```python
# -*- coding: utf-8 -*-
"""Permission contract shared by EP8 granular roles and SP4 auth hardening.
Qt-free and DB-free so it is unit-testable in isolation."""

PERMISSIONS = (
    "can_ingest",
    "can_delete",
    "can_edit_metadata",
    "can_manage_users",
    "can_manage_schema",
)

# built-in role name -> granted permission set
BUILTIN_ROLES = {
    "admin":    set(PERMISSIONS),                     # admin implies all
    "user":     {"can_ingest", "can_edit_metadata"},
    "reviewer": {"can_edit_metadata"},
    "ingestor": {"can_ingest"},
    "viewer":   set(),
}


def is_valid_permission(permission):
    return permission in PERMISSIONS


def default_permissions_for(role_name):
    """Built-in default permission set for a role name (empty for unknown)."""
    return set(BUILTIN_ROLES.get(role_name, set()))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_permissions.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/permissions.py tests/unit/test_ep8_permissions.py
git commit -m "feat(ep8): add permission contract module"
```

---

## Task 2: Roles + permissions tables, CRUD, `has_permission`

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep8_roles.py`

**Interfaces:**
- Produces tables `roles`, `role_permissions`, and: `seed_builtin_roles()`, `create_role(name, label=None, permissions=None) -> int`, `get_roles() -> list[dict]` (each with a `permissions` list), `get_role_permissions(role_name) -> set`, `set_role_permissions(role_name, permissions)`, `delete_role(role_name)` (refuses built-ins), `has_permission(username, permission) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_roles.py`:

```python
import pytest


@pytest.mark.unit
def test_builtin_roles_seeded(stax_db):
    names = {r["name"] for r in stax_db.get_roles()}
    assert {"admin", "user", "reviewer", "ingestor", "viewer"}.issubset(names)


@pytest.mark.unit
def test_admin_user_has_all_permissions(stax_db):
    # the default admin/admin user is seeded by _create_schema
    assert stax_db.has_permission("admin", "can_delete") is True
    assert stax_db.has_permission("admin", "can_manage_schema") is True


@pytest.mark.unit
def test_role_permission_membership(stax_db):
    stax_db.create_user("rev", "pw", role="reviewer")
    assert stax_db.has_permission("rev", "can_edit_metadata") is True
    assert stax_db.has_permission("rev", "can_delete") is False


@pytest.mark.unit
def test_set_role_permissions_and_custom_role(stax_db):
    rid = stax_db.create_role("editor", permissions={"can_edit_metadata"})
    assert rid > 0
    stax_db.set_role_permissions("editor", {"can_edit_metadata", "can_delete"})
    assert stax_db.get_role_permissions("editor") == {"can_edit_metadata", "can_delete"}


@pytest.mark.unit
def test_delete_role_refuses_builtin(stax_db):
    with pytest.raises(ValueError):
        stax_db.delete_role("admin")


@pytest.mark.unit
def test_unknown_user_or_role_has_no_permission(stax_db):
    assert stax_db.has_permission("ghost", "can_ingest") is False
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_roles.py -v`
Expected: FAIL — tables/methods missing.

- [ ] **Step 3: Implement schema + seed + CRUD**

In `_create_schema` (after the users/settings tables) **and** in `_apply_migrations`, add the tables and seed (idempotent):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                role_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                label      TEXT,
                is_builtin INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_fk    INTEGER NOT NULL,
                permission TEXT NOT NULL,
                PRIMARY KEY (role_fk, permission),
                FOREIGN KEY (role_fk) REFERENCES roles(role_id) ON DELETE CASCADE
            )
        """)
```

In `_apply_migrations`, wrap the two `CREATE TABLE IF NOT EXISTS` above in the same block, then call seeding. Because `_create_schema`/`_apply_migrations` each already open a connection, expose the seed as a method that opens its own connection and call `self.seed_builtin_roles()` at the end of both (after the `with` block returns). Add the methods to `DatabaseManager` (import `permissions` at module top: `from permissions import PERMISSIONS, BUILTIN_ROLES, is_valid_permission`):

```python
    def seed_builtin_roles(self):
        """Insert any missing built-in roles + their default permissions. Idempotent."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            for name, perms in BUILTIN_ROLES.items():
                cur.execute("SELECT role_id FROM roles WHERE name = ?", (name,))
                row = cur.fetchone()
                if row:
                    role_id = row[0]
                else:
                    cur.execute(
                        "INSERT INTO roles (name, label, is_builtin) VALUES (?, ?, 1)",
                        (name, name.capitalize()))
                    role_id = cur.lastrowid
                    for p in perms:
                        cur.execute(
                            "INSERT OR IGNORE INTO role_permissions (role_fk, permission) "
                            "VALUES (?, ?)", (role_id, p))
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
```

Call `self.seed_builtin_roles()` at the end of both `_create_schema` and `_apply_migrations` (outside their `with` blocks).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_roles.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep8_roles.py
git commit -m "feat(ep8): add roles/permissions tables, CRUD and has_permission"
```

---

## Task 3: `check_permission` enforcement in MainWindow

**Files:**
- Modify: `main.py`
- Test: `tests/gui/test_ep8_check_permission.py`

**Interfaces:**
- Consumes: `db.has_permission`.
- Produces: `MainWindow.check_permission(permission, action_name="this action") -> bool` (admin always passes; no `current_user` → prompt login; failure → styled dialog + `False`).

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep8_check_permission.py`:

```python
import pytest


@pytest.mark.gui
def test_check_permission_uses_role_matrix(qtbot, stax_db, monkeypatch):
    stax_db.create_user("rev", "pw", role="reviewer")
    from main import StaXMainWindow  # adjust to the real MainWindow class name
    win = StaXMainWindow(db=stax_db)
    qtbot.addWidget(win)
    win.current_user = {"username": "rev", "role": "reviewer", "user_id": 2}
    win.is_admin = False
    # silence any dialog on denial
    monkeypatch.setattr("PySide2.QtWidgets.QMessageBox.warning", lambda *a, **k: None)
    assert win.check_permission("can_edit_metadata") is True
    assert win.check_permission("can_delete") is False
```

> Match the real `MainWindow` class name and constructor in `main.py` (it may build its own `DatabaseManager`; if so, set `win.db = stax_db` after construction and re-run the check). If a full window is too heavy to instantiate headless, extract `check_permission` onto a small mixin and test that instead — keep the method body identical.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep8_check_permission.py -v`
Expected: FAIL — `check_permission` missing.

- [ ] **Step 3: Implement**

Add to the `MainWindow` class in `main.py`, right after `check_admin_permission` (line 547):

```python
    def check_permission(self, permission, action_name="this action"):
        """Granular-permission gate (EP8). Admin always passes."""
        if not self.current_user:
            if not self.show_login(required=True):
                QtWidgets.QMessageBox.information(
                    self, "Login Required",
                    "You must login to perform {}.".format(action_name))
                return False
        username = self.current_user.get("username") if self.current_user else None
        if self.is_admin or self.db.has_permission(username, permission):
            return True
        QtWidgets.QMessageBox.warning(
            self, "Permission Denied",
            "You need the '{}' permission to perform {}.\n\n"
            "Current user: {} ({})".format(
                permission, action_name,
                username or "guest",
                self.current_user.get("role", "guest") if self.current_user else "guest"))
        return False
```

Switch the relevant call sites: the ingest action gates on `check_permission("can_ingest", "ingestion")`; the delete-element action on `check_permission("can_delete", "deleting assets")`; metadata edit on `check_permission("can_edit_metadata", "editing metadata")`. Keep `check_admin_permission` for user management and schema surfaces.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep8_check_permission.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/gui/test_ep8_check_permission.py
git commit -m "feat(ep8): add granular check_permission gate to MainWindow"
```

---

## Task 4: Admin Roles matrix tab

**Files:**
- Modify: `src/ui/settings_panel.py`
- Test: `tests/gui/test_ep8_roles_tab.py`

**Interfaces:**
- Consumes: `get_roles`, `set_role_permissions`, `create_role`; `main_window.check_admin_permission`.
- Produces: `_build_roles_tab(self) -> QWidget` added via `self.tab_widget.addTab(tab, "Roles")`; `self.roles_table` (roles × permission checkboxes); `_toggle_role_permission(role_name, permission, on)`; add/edit controls disabled for non-admins.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep8_roles_tab.py`:

```python
import pytest


class _Main:
    def __init__(self, admin, user="admin"):
        self._a = admin
        self.current_user = {"username": user, "role": "admin" if admin else "user"}
        self.is_admin = admin
    def check_admin_permission(self, *a, **k):
        return self._a


@pytest.mark.gui
def test_roles_tab_lists_roles_and_gates_admin(qtbot, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config=None, main_window=_Main(admin=False))
    qtbot.addWidget(panel)
    assert panel.roles_table.rowCount() >= 5      # built-in roles
    assert panel.add_role_button.isEnabled() is False


@pytest.mark.gui
def test_admin_toggles_permission_persists(qtbot, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config=None, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    panel._toggle_role_permission("reviewer", "can_delete", True)
    assert "can_delete" in stax_db.get_role_permissions("reviewer")
```

> Match `SettingsPanel.__init__`'s real signature (the same `main_window` source the Security Admin tab uses).

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep8_roles_tab.py -v`
Expected: FAIL — `roles_table` / `_build_roles_tab` missing.

- [ ] **Step 3: Implement the tab**

In `SettingsPanel.setup_ui`, after the Security Admin tab, add:

```python
        self.tab_widget.addTab(self._build_roles_tab(), "Roles")
```

Add the builder + helpers (import `from permissions import PERMISSIONS` at module top):

```python
    def _build_roles_tab(self):
        from PySide2 import QtWidgets, QtCore
        from permissions import PERMISSIONS
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        is_admin = bool(self.main_window.check_admin_permission()) if self.main_window else False

        layout.addWidget(QtWidgets.QLabel("Roles → Permissions"))
        self.roles_table = QtWidgets.QTableWidget(0, 1 + len(PERMISSIONS))
        self.roles_table.setHorizontalHeaderLabels(["Role"] + list(PERMISSIONS))
        layout.addWidget(self.roles_table)

        self.add_role_button = QtWidgets.QPushButton("Add role…")
        self.add_role_button.clicked.connect(self._on_add_role)
        self.add_role_button.setEnabled(is_admin)
        layout.addWidget(self.add_role_button)

        self._roles_admin = is_admin
        self._reload_roles()
        return tab

    def _reload_roles(self):
        from PySide2 import QtWidgets, QtCore
        from permissions import PERMISSIONS
        roles = self.db.get_roles()
        self.roles_table.setRowCount(len(roles))
        for row, role in enumerate(roles):
            name_item = QtWidgets.QTableWidgetItem(role["name"])
            name_item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.roles_table.setItem(row, 0, name_item)
            for col, perm in enumerate(PERMISSIONS, start=1):
                cb = QtWidgets.QCheckBox()
                cb.setChecked(perm in role["permissions"])
                cb.setEnabled(getattr(self, "_roles_admin", False))
                cb.toggled.connect(
                    lambda on, r=role["name"], p=perm: self._toggle_role_permission(r, p, on))
                holder = QtWidgets.QWidget()
                h = QtWidgets.QHBoxLayout(holder)
                h.setContentsMargins(0, 0, 0, 0)
                h.setAlignment(QtCore.Qt.AlignCenter)
                h.addWidget(cb)
                self.roles_table.setCellWidget(row, col, holder)

    def _toggle_role_permission(self, role_name, permission, on):
        perms = self.db.get_role_permissions(role_name)
        if on:
            perms.add(permission)
        else:
            perms.discard(permission)
        self.db.set_role_permissions(role_name, perms)
        rid = next((r["role_id"] for r in self.db.get_roles() if r["name"] == role_name), None)
        actor = (self.main_window.current_user or {}).get("username") if self.main_window else None
        if actor:
            self.db.log_activity(actor, "role_change", "role", rid,
                                 "{} {} {}".format("granted" if on else "revoked", permission, role_name))

    def _on_add_role(self):
        from PySide2 import QtWidgets
        name, ok = QtWidgets.QInputDialog.getText(self, "New role", "Role name:")
        if not ok or not name:
            return
        self.db.create_role(name.strip())
        self._reload_roles()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep8_roles_tab.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/settings_panel.py tests/gui/test_ep8_roles_tab.py
git commit -m "feat(ep8): add admin Roles matrix settings tab"
```

---

# Cluster 8B — Activity feed / audit (F043)

## Task 5: `activity_log` table + `log_activity` / `get_activity`

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep8_activity_log.py`

**Interfaces:**
- Produces table `activity_log` and: `log_activity(actor, action, target_type=None, target_id=None, detail=None) -> int`, `get_activity(limit=100, action=None, actor=None, target_type=None) -> list[dict]` (newest first).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_activity_log.py`:

```python
import pytest


@pytest.mark.unit
def test_log_and_read_newest_first(stax_db):
    stax_db.log_activity("alice", "ingest", "element", 1, "plate_a")
    stax_db.log_activity("bob", "delete", "element", 1, "plate_a")
    rows = stax_db.get_activity()
    assert rows[0]["action"] == "delete"
    assert rows[0]["actor"] == "bob"
    assert rows[1]["action"] == "ingest"


@pytest.mark.unit
def test_filter_by_action_and_actor(stax_db):
    stax_db.log_activity("alice", "ingest", "element", 1)
    stax_db.log_activity("bob", "ingest", "element", 2)
    stax_db.log_activity("alice", "delete", "element", 1)
    assert len(stax_db.get_activity(action="ingest")) == 2
    assert len(stax_db.get_activity(actor="alice")) == 2
    assert len(stax_db.get_activity(action="delete", actor="alice")) == 1


@pytest.mark.unit
def test_limit(stax_db):
    for i in range(5):
        stax_db.log_activity("alice", "ingest", "element", i)
    assert len(stax_db.get_activity(limit=2)) == 2
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_activity_log.py -v`
Expected: FAIL — table/methods missing.

- [ ] **Step 3: Implement**

Add the table (to `_create_schema` + `_apply_migrations`):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor       TEXT,
                action      TEXT NOT NULL,
                target_type TEXT,
                target_id   INTEGER,
                detail      TEXT,
                at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_at ON activity_log(at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log(action)")
```

Add methods:

```python
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
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_activity_log.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep8_activity_log.py
git commit -m "feat(ep8): add activity_log table with log/get and filters"
```

---

## Task 6: Audit hooks in delete / ingest / metadata edit

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep8_audit_hooks.py`

**Interfaces:**
- Produces: `delete_element(element_id, actor=None)`, `log_ingestion(..., actor=None)`, `update_element(element_id, _actor=None, **kwargs)` — each appends the matching `activity_log` row **only when the actor is supplied**; omitting it preserves current behavior.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_audit_hooks.py`:

```python
import pytest


def _seed_element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'plate_a', '2D')")
        conn.commit()
    return 1


@pytest.mark.unit
def test_delete_with_actor_audits(stax_db):
    eid = _seed_element(stax_db)
    stax_db.delete_element(eid, actor="alice")
    rows = stax_db.get_activity(action="delete")
    assert rows and rows[0]["actor"] == "alice" and rows[0]["target_id"] == eid


@pytest.mark.unit
def test_delete_without_actor_writes_no_activity(stax_db):
    eid = _seed_element(stax_db)
    stax_db.delete_element(eid)
    assert stax_db.get_activity(action="delete") == []


@pytest.mark.unit
def test_update_with_actor_audits_metadata_edit(stax_db):
    eid = _seed_element(stax_db)
    stax_db.update_element(eid, _actor="bob", comment="new note")
    rows = stax_db.get_activity(action="metadata_edit")
    assert rows and rows[0]["actor"] == "bob"


@pytest.mark.unit
def test_ingest_success_with_actor_audits(stax_db):
    stax_db.log_ingestion("ingest", "/src/a.exr", "L", "success", actor="carol", element_id=7)
    rows = stax_db.get_activity(action="ingest")
    assert rows and rows[0]["actor"] == "carol" and rows[0]["target_id"] == 7
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_audit_hooks.py -v`
Expected: FAIL — actor params not accepted / no rows written.

- [ ] **Step 3: Implement**

Update the three methods (keep their existing bodies; add the optional actor + audit write):

```python
    def delete_element(self, element_id, actor=None):
        """Delete element. When `actor` is given, record a delete activity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM elements WHERE element_id = ?", (element_id,))
            deleted = cursor.rowcount > 0
        if deleted and actor:
            self.log_activity(actor, "delete", "element", element_id)
        return deleted
```

For `update_element`, pull `_actor` out of the call **before** building the SET clause so it never becomes a column:

```python
    def update_element(self, element_id, _actor=None, **kwargs):
        if not kwargs:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ', '.join(["{} = ?".format(k) for k in kwargs.keys()])
            values = list(kwargs.values()) + [element_id]
            cursor.execute(
                "UPDATE elements SET {} WHERE element_id = ?".format(set_clause), values)
            updated = cursor.rowcount > 0
        if updated and _actor:
            self.log_activity(_actor, "metadata_edit", "element", element_id,
                              ",".join(sorted(kwargs.keys())))
        return updated
```

For `log_ingestion`, add `actor=None` to the signature and, after the existing history insert, when `status == "success" and actor`:

```python
        if status == "success" and actor:
            self.log_activity(actor, "ingest", "element", element_id, source_path)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_audit_hooks.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep8_audit_hooks.py
git commit -m "feat(ep8): audit delete/ingest/metadata-edit via optional actor"
```

---

## Task 7: `ActivityPanel` dock

**Files:**
- Create: `src/ui/activity_panel.py`
- Test: `tests/gui/test_ep8_activity_panel.py`

**Interfaces:**
- Consumes: `get_activity`.
- Produces: `ActivityPanel(db, parent=None)` (a `QDockWidget`) with `activity_table`, `action_filter`/`actor_filter` combos, and `refresh()`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep8_activity_panel.py`:

```python
import pytest


@pytest.mark.gui
def test_activity_panel_lists_and_filters(qtbot, stax_db):
    stax_db.log_activity("alice", "ingest", "element", 1, "plate_a")
    stax_db.log_activity("bob", "delete", "element", 1, "plate_a")
    from ui.activity_panel import ActivityPanel
    panel = ActivityPanel(stax_db)
    qtbot.addWidget(panel)
    panel.refresh()
    assert panel.activity_table.rowCount() == 2
    panel.set_action_filter("delete")
    panel.refresh()
    assert panel.activity_table.rowCount() == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep8_activity_panel.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/activity_panel.py`:

```python
# -*- coding: utf-8 -*-
"""Activity / audit feed dock (EP8, F043)."""

from PySide2 import QtWidgets, QtCore

_COLUMNS = ["When", "Actor", "Action", "Target", "Detail"]


class ActivityPanel(QtWidgets.QDockWidget):
    def __init__(self, db, parent=None):
        super(ActivityPanel, self).__init__("Activity", parent)
        self.db = db
        self._action = None
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)

        bar = QtWidgets.QHBoxLayout()
        self.action_filter = QtWidgets.QComboBox()
        self.action_filter.addItems(["(all)", "ingest", "delete", "metadata_edit",
                                     "role_change", "export", "import"])
        self.action_filter.currentTextChanged.connect(self._on_action_changed)
        self.actor_filter = QtWidgets.QComboBox()
        self.actor_filter.setEditable(True)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(QtWidgets.QLabel("Action:"))
        bar.addWidget(self.action_filter)
        bar.addWidget(QtWidgets.QLabel("Actor:"))
        bar.addWidget(self.actor_filter)
        bar.addWidget(refresh_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.activity_table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self.activity_table.setHorizontalHeaderLabels(_COLUMNS)
        self.activity_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.activity_table)

        self.setWidget(container)
        self.refresh()

    def set_action_filter(self, action):
        self._action = action

    def _on_action_changed(self, text):
        self._action = None if text == "(all)" else text

    def refresh(self):
        actor = self.actor_filter.currentText().strip() or None
        rows = self.db.get_activity(action=self._action, actor=actor)
        self.activity_table.setRowCount(len(rows))
        for row, ev in enumerate(rows):
            target = "{}#{}".format(ev.get("target_type") or "", ev.get("target_id") or "")
            values = [str(ev.get("at") or ""), ev.get("actor") or "",
                      ev.get("action") or "", target, ev.get("detail") or ""]
            for col, val in enumerate(values):
                self.activity_table.setItem(row, col, QtWidgets.QTableWidgetItem(val))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep8_activity_panel.py -v`
Expected: PASS.

- [ ] **Step 5: Wire the dock into `main.py` + commit**

In `MainWindow.__init__` (where other docks are created), add:

```python
        from ui.activity_panel import ActivityPanel
        self.activity_dock = ActivityPanel(self.db, self)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.activity_dock)
        self.activity_dock.hide()   # toggled from the View menu like History
```

Add a View-menu toggle next to the History panel toggle, and call `self.activity_dock.refresh()` when it is shown.

```bash
git add src/ui/activity_panel.py main.py tests/gui/test_ep8_activity_panel.py
git commit -m "feat(ep8): add Activity dock with action/actor filters"
```

---

# Cluster 8C — Team metadata sync (F041)

## Task 8: `elements.updated_at` migration + bump on update

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep8_updated_at.py`

**Interfaces:**
- Produces: `elements.updated_at` column (defaults to `created_at`); `update_element` sets `updated_at = CURRENT_TIMESTAMP` on every write.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_updated_at.py`:

```python
import time
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'a', '2D')")
        conn.commit()
    return 1


@pytest.mark.unit
def test_updated_at_column_exists(stax_db):
    eid = _seed(stax_db)
    row = stax_db.get_element_by_id(eid)
    assert "updated_at" in row


@pytest.mark.unit
def test_update_bumps_updated_at(stax_db):
    eid = _seed(stax_db)
    before = stax_db.get_element_by_id(eid)["updated_at"]
    time.sleep(1.1)
    stax_db.update_element(eid, comment="x")
    after = stax_db.get_element_by_id(eid)["updated_at"]
    assert after >= before
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_updated_at.py -v`
Expected: FAIL — no `updated_at` column.

- [ ] **Step 3: Implement**

Add `updated_at TIMESTAMP` to the `elements` `CREATE TABLE` in `_create_schema`. In `_apply_migrations`, add an idempotent column migration (mirroring the existing pattern) that also backfills from `created_at`:

```python
            # EP8 Migration: elements.updated_at for sync conflict resolution
            try:
                cursor.execute("SELECT updated_at FROM elements LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute("ALTER TABLE elements ADD COLUMN updated_at TIMESTAMP")
                cursor.execute("UPDATE elements SET updated_at = created_at "
                               "WHERE updated_at IS NULL")
```

In `update_element`, always stamp `updated_at` (add it to the write, without requiring the caller to pass it):

```python
    def update_element(self, element_id, _actor=None, **kwargs):
        if not kwargs:
            return False
        kwargs = dict(kwargs)
        kwargs["updated_at"] = self._now_iso()   # stamp on every update
        ...
```

Add a small helper:

```python
    @staticmethod
    def _now_iso():
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

(Use an explicit timestamp string rather than `CURRENT_TIMESTAMP` so the value is present in the same connection without a re-read.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_updated_at.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep8_updated_at.py
git commit -m "feat(ep8): add elements.updated_at and bump on update_element"
```

---

## Task 9: `metadata_bundle.export_list_bundle`

**Files:**
- Create: `src/sync/__init__.py`, `src/sync/metadata_bundle.py`
- Test: `tests/unit/test_ep8_bundle_export.py`

**Interfaces:**
- Produces: `export_list_bundle(db, list_id, out_path, source_site="", include_previews=True) -> str`; `read_manifest(bundle_path) -> dict`. Bundle is a zip with `manifest.json`, `elements.json`, and `previews/`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_bundle_export.py`:

```python
import json
import zipfile
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type, comment, tags) "
                     "VALUES (1, 'plate_a', '2D', 'hi', 'fire,city')")
        conn.commit()
    return 1


@pytest.mark.unit
def test_export_writes_zip_with_manifest_and_elements(stax_db, tmp_path):
    lid = _seed(stax_db)
    from sync.metadata_bundle import export_list_bundle, read_manifest
    out = str(tmp_path / "list.staxbundle")
    path = export_list_bundle(stax_db, lid, out, source_site="siteA")
    assert path == out
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "elements.json" in names
        elements = json.loads(zf.read("elements.json").decode("utf-8"))
    assert elements[0]["name"] == "plate_a"
    assert elements[0]["tags"] == "fire,city"
    manifest = read_manifest(out)
    assert manifest["source_site"] == "siteA"
    assert manifest["element_count"] == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_bundle_export.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/sync/__init__.py` (empty package marker), then `src/sync/metadata_bundle.py`:

```python
# -*- coding: utf-8 -*-
"""Portable metadata + preview bundle export/import (EP8, F041).
Stdlib only: json, zipfile, shutil, os, datetime. Network-free."""

import os
import json
import zipfile
import datetime
import logging

logger = logging.getLogger(__name__)

BUNDLE_VERSION = 1

# element columns that travel in the bundle
_FIELDS = ("name", "type", "format", "frame_range", "comment", "tags",
           "is_deprecated", "created_at", "updated_at")


def _iso_now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def export_list_bundle(db, list_id, out_path, source_site="", include_previews=True):
    """Serialize a list's elements + metadata + previews into a .staxbundle zip."""
    lst = db.get_list_by_id(list_id)
    elements = db.get_elements_by_list(list_id, include_deprecated=True)

    records, preview_map = [], {}
    for el in elements:
        rec = {k: el.get(k) for k in _FIELDS}
        rec["preview_file"] = None
        preview = el.get("preview_path")
        if include_previews and preview and os.path.exists(preview):
            arc = "previews/{}_{}".format(el["element_id"], os.path.basename(preview))
            rec["preview_file"] = arc
            preview_map[arc] = preview
        records.append(rec)

    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "source_site": source_site,
        "exported_at": _iso_now(),
        "scope": {"type": "list", "id": list_id,
                  "name": lst["name"] if lst else str(list_id)},
        "element_count": len(records),
    }

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("elements.json", json.dumps(records, indent=2))
        for arc, src in preview_map.items():
            try:
                zf.write(src, arc)
            except OSError:
                logger.exception("failed to add preview %s", src)
    if hasattr(db, "log_activity"):
        db.log_activity(source_site or "system", "export", "bundle", list_id,
                        "{} elements".format(len(records)))
    return out_path


def read_manifest(bundle_path):
    with zipfile.ZipFile(bundle_path) as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_bundle_export.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sync/__init__.py src/sync/metadata_bundle.py tests/unit/test_ep8_bundle_export.py
git commit -m "feat(ep8): add metadata bundle export + manifest reader"
```

---

## Task 10: `import_bundle` with timestamp conflict handling

**Files:**
- Modify: `src/sync/metadata_bundle.py`
- Test: `tests/unit/test_ep8_bundle_import.py`

**Interfaces:**
- Produces: `import_bundle(db, bundle_path, target_list_id, conflict="timestamp", previews_dir=None) -> {"added": n, "updated": n, "skipped": n}`. Match by element name within the target list; add when absent, update when the bundle `updated_at` is newer, skip otherwise.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_bundle_import.py`:

```python
import pytest


def _seed_source(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'SRC')")
        conn.execute("INSERT INTO elements (list_fk, name, type, comment) "
                     "VALUES (1, 'plate_a', '2D', 'v1')")
        conn.commit()
    return 1


def _make_target_list(stax_db):
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'DST')")
        conn.commit()
    return 2


@pytest.mark.unit
def test_roundtrip_add_then_skip(stax_db, tmp_path):
    src = _seed_source(stax_db)
    dst = _make_target_list(stax_db)
    from sync.metadata_bundle import export_list_bundle, import_bundle
    bundle = str(tmp_path / "b.staxbundle")
    export_list_bundle(stax_db, src, bundle)

    first = import_bundle(stax_db, bundle, dst)
    assert first == {"added": 1, "updated": 0, "skipped": 0}
    # re-import same bundle -> identical timestamps -> skip
    second = import_bundle(stax_db, bundle, dst)
    assert second == {"added": 0, "updated": 0, "skipped": 1}


@pytest.mark.unit
def test_newer_bundle_updates(stax_db, tmp_path):
    src = _seed_source(stax_db)
    dst = _make_target_list(stax_db)
    from sync.metadata_bundle import export_list_bundle, import_bundle
    # bring plate_a into DST first
    export_list_bundle(stax_db, src, str(tmp_path / "b1.staxbundle"))
    import_bundle(stax_db, str(tmp_path / "b1.staxbundle"), dst)
    # edit the source (bumps updated_at) and re-export a newer bundle
    import time; time.sleep(1.1)
    src_el = [e for e in stax_db.get_elements_by_list(src) if e["name"] == "plate_a"][0]
    stax_db.update_element(src_el["element_id"], comment="v2")
    export_list_bundle(stax_db, src, str(tmp_path / "b2.staxbundle"))
    res = import_bundle(stax_db, str(tmp_path / "b2.staxbundle"), dst)
    assert res == {"added": 0, "updated": 1, "skipped": 0}
    dst_el = [e for e in stax_db.get_elements_by_list(dst) if e["name"] == "plate_a"][0]
    assert dst_el["comment"] == "v2"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_bundle_import.py -v`
Expected: FAIL — `import_bundle` not defined.

- [ ] **Step 3: Implement**

Append to `src/sync/metadata_bundle.py`:

```python
def _load_records(bundle_path):
    with zipfile.ZipFile(bundle_path) as zf:
        return json.loads(zf.read("elements.json").decode("utf-8"))


def _extract_preview(bundle_path, arc, previews_dir):
    if not arc or not previews_dir:
        return None
    try:
        with zipfile.ZipFile(bundle_path) as zf:
            data = zf.read(arc)
        dest = os.path.join(previews_dir, os.path.basename(arc))
        if not os.path.isdir(previews_dir):
            os.makedirs(previews_dir)
        with open(dest, "wb") as fh:
            fh.write(data)
        return dest
    except (OSError, KeyError):
        logger.exception("failed to extract preview %s", arc)
        return None


def import_bundle(db, bundle_path, target_list_id, conflict="timestamp", previews_dir=None):
    """Merge a bundle into target_list_id. Match by name; newest updated_at wins."""
    records = _load_records(bundle_path)
    existing = {e["name"]: e for e in db.get_elements_by_list(target_list_id,
                                                              include_deprecated=True)}
    summary = {"added": 0, "updated": 0, "skipped": 0}

    for rec in records:
        name = rec.get("name")
        preview_dest = _extract_preview(bundle_path, rec.get("preview_file"), previews_dir)
        payload = {k: rec.get(k) for k in
                   ("type", "format", "frame_range", "comment", "tags", "is_deprecated")}
        if preview_dest:
            payload["preview_path"] = preview_dest

        current = existing.get(name)
        if current is None:
            with db.get_connection() as conn:
                cols = ["list_fk", "name"] + list(payload.keys()) + ["updated_at"]
                vals = [target_list_id, name] + list(payload.values()) + [rec.get("updated_at")]
                placeholders = ", ".join("?" for _ in cols)
                conn.execute("INSERT INTO elements ({}) VALUES ({})".format(
                    ", ".join(cols), placeholders), vals)
                conn.commit()
            summary["added"] += 1
            continue

        incoming = rec.get("updated_at") or ""
        local = current.get("updated_at") or ""
        if conflict == "timestamp" and incoming > local:
            # update in place; preserve updated_at from the bundle
            payload_with_ts = dict(payload)
            payload_with_ts["updated_at"] = incoming
            with db.get_connection() as conn:
                set_clause = ", ".join("{} = ?".format(k) for k in payload_with_ts)
                conn.execute("UPDATE elements SET {} WHERE element_id = ?".format(set_clause),
                             list(payload_with_ts.values()) + [current["element_id"]])
                conn.commit()
            summary["updated"] += 1
        else:
            summary["skipped"] += 1

    if hasattr(db, "log_activity"):
        db.log_activity("system", "import", "bundle", target_list_id,
                        "added={added} updated={updated} skipped={skipped}".format(**summary))
    return summary
```

> Note: the update path writes `updated_at` directly (not via `update_element`) so the bundle's timestamp is preserved for future comparisons rather than being re-stamped to "now".

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_bundle_import.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sync/metadata_bundle.py tests/unit/test_ep8_bundle_import.py
git commit -m "feat(ep8): add bundle import with newest-timestamp merge"
```

---

## Task 11: `CollaborationConnector` ABC + registry + local connector

**Files:**
- Create: `src/sync/connector.py`
- Test: `tests/unit/test_ep8_connector.py`

**Interfaces:**
- Produces: `CollaborationConnector` (base), `LocalBundleConnector`, `register_connector(cls)`, `get_connectors() -> list` (instances). `LocalBundleConnector.capabilities() == {"push", "pull"}`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep8_connector.py`:

```python
import pytest


@pytest.mark.unit
def test_base_connector_is_unavailable_by_default():
    from sync.connector import CollaborationConnector
    c = CollaborationConnector()
    assert c.is_available() is False
    assert c.capabilities() == set()


@pytest.mark.unit
def test_local_bundle_connector_registered_with_capabilities():
    from sync.connector import get_connectors, LocalBundleConnector
    instances = get_connectors()
    assert any(isinstance(c, LocalBundleConnector) for c in instances)
    local = [c for c in instances if isinstance(c, LocalBundleConnector)][0]
    assert local.capabilities() == {"push", "pull"}
    assert local.is_available() is True
    assert local.key == "local_bundle"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep8_connector.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/sync/connector.py`:

```python
# -*- coding: utf-8 -*-
"""Collaboration connector seam (EP8). EP8 ships only the local-bundle path;
Kitsu/Ftrack/Flow/DCC bridges are follow-on subclasses (see the EP8 design §10).
No third-party SDK is imported here."""

import logging

logger = logging.getLogger(__name__)


class CollaborationConnector(object):
    """Base class for external collaboration bridges."""
    key = "base"
    label = "Base Connector"

    def is_available(self):
        """True when this connector is configured/usable in the environment."""
        return False

    def capabilities(self):
        """Subset of {'push', 'pull', 'status', 'notes'}."""
        return set()

    def push(self, payload):
        raise NotImplementedError

    def pull(self):
        raise NotImplementedError


class LocalBundleConnector(CollaborationConnector):
    """The only concrete connector EP8 ships: wraps metadata_bundle export/import."""
    key = "local_bundle"
    label = "Local Bundle (.staxbundle)"

    def is_available(self):
        return True

    def capabilities(self):
        return {"push", "pull"}

    def push(self, payload):
        from sync.metadata_bundle import export_list_bundle
        return export_list_bundle(payload["db"], payload["list_id"], payload["out_path"],
                                  source_site=payload.get("source_site", ""))

    def pull(self, payload=None):
        from sync.metadata_bundle import import_bundle
        payload = payload or {}
        return import_bundle(payload["db"], payload["bundle_path"], payload["target_list_id"],
                             previews_dir=payload.get("previews_dir"))


_REGISTRY = []


def register_connector(cls):
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
    return cls


def get_connectors():
    return [cls() for cls in _REGISTRY]


register_connector(LocalBundleConnector)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep8_connector.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sync/connector.py tests/unit/test_ep8_connector.py
git commit -m "feat(ep8): add CollaborationConnector seam + LocalBundleConnector"
```

---

## Task 12: Admin Sync tab (export/import + connectors list)

**Files:**
- Modify: `src/ui/settings_panel.py`
- Test: `tests/gui/test_ep8_sync_tab.py`

**Interfaces:**
- Consumes: `export_list_bundle`, `import_bundle`, `get_connectors`, `get_all_stacks`/`get_lists_by_stack`; `main_window.check_admin_permission`.
- Produces: `_build_sync_tab(self) -> QWidget` added via `self.tab_widget.addTab(tab, "Sync")`; `self.connectors_table`; `_do_export(list_id, out_path)` / `_do_import(bundle_path, target_list_id)` helpers; controls admin-gated.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep8_sync_tab.py`:

```python
import pytest


class _Main:
    def __init__(self, admin):
        self._a = admin
        self.current_user = {"username": "admin", "role": "admin"}
        self.is_admin = admin
    def check_admin_permission(self, *a, **k):
        return self._a


def _seed_list(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'a', '2D')")
        conn.commit()
    return 1


@pytest.mark.gui
def test_sync_tab_lists_connectors(qtbot, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config=None, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    labels = [panel.connectors_table.item(r, 0).text()
              for r in range(panel.connectors_table.rowCount())]
    assert any("Local Bundle" in t for t in labels)


@pytest.mark.gui
def test_export_helper_writes_bundle_and_audits(qtbot, stax_db, tmp_path):
    lid = _seed_list(stax_db)
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config=None, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    out = str(tmp_path / "x.staxbundle")
    panel._do_export(lid, out)
    import os
    assert os.path.exists(out)
    assert stax_db.get_activity(action="export")
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep8_sync_tab.py -v`
Expected: FAIL — `connectors_table` / `_build_sync_tab` missing.

- [ ] **Step 3: Implement the tab**

In `SettingsPanel.setup_ui`, after the Roles tab, add:

```python
        self.tab_widget.addTab(self._build_sync_tab(), "Sync")
```

Add the builder + helpers:

```python
    def _build_sync_tab(self):
        from PySide2 import QtWidgets
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        is_admin = bool(self.main_window.check_admin_permission()) if self.main_window else False

        layout.addWidget(QtWidgets.QLabel("Metadata bundle export / import"))
        btn_row = QtWidgets.QHBoxLayout()
        self.export_bundle_button = QtWidgets.QPushButton("Export list to bundle…")
        self.import_bundle_button = QtWidgets.QPushButton("Import bundle…")
        self.export_bundle_button.clicked.connect(self._on_export_clicked)
        self.import_bundle_button.clicked.connect(self._on_import_clicked)
        for b in (self.export_bundle_button, self.import_bundle_button):
            b.setEnabled(is_admin)
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addWidget(QtWidgets.QLabel("Connectors"))
        self.connectors_table = QtWidgets.QTableWidget(0, 3)
        self.connectors_table.setHorizontalHeaderLabels(["Connector", "Available", "Capabilities"])
        layout.addWidget(self.connectors_table)
        self._reload_connectors()
        layout.addStretch()
        return tab

    def _reload_connectors(self):
        from PySide2 import QtWidgets
        from sync.connector import get_connectors
        conns = get_connectors()
        self.connectors_table.setRowCount(len(conns))
        for row, c in enumerate(conns):
            self.connectors_table.setItem(row, 0, QtWidgets.QTableWidgetItem(c.label))
            self.connectors_table.setItem(row, 1, QtWidgets.QTableWidgetItem(
                "yes" if c.is_available() else "no"))
            self.connectors_table.setItem(row, 2, QtWidgets.QTableWidgetItem(
                ", ".join(sorted(c.capabilities())) or "-"))

    def _do_export(self, list_id, out_path):
        from sync.metadata_bundle import export_list_bundle
        site = (self.main_window.current_user or {}).get("username", "") if self.main_window else ""
        return export_list_bundle(self.db, list_id, out_path, source_site=site)

    def _do_import(self, bundle_path, target_list_id):
        from sync.metadata_bundle import import_bundle
        return import_bundle(self.db, bundle_path, target_list_id)

    def _on_export_clicked(self):
        from PySide2 import QtWidgets
        list_id, ok = QtWidgets.QInputDialog.getInt(self, "Export", "List ID:")
        if not ok:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export bundle", "list.staxbundle", "StaX bundle (*.staxbundle)")
        if path:
            self._do_export(list_id, path)

    def _on_import_clicked(self):
        from PySide2 import QtWidgets
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import bundle", "", "StaX bundle (*.staxbundle)")
        if not path:
            return
        target, ok = QtWidgets.QInputDialog.getInt(self, "Import", "Target list ID:")
        if not ok:
            return
        summary = self._do_import(path, target)
        QtWidgets.QMessageBox.information(
            self, "Import complete",
            "Added {added}, updated {updated}, skipped {skipped}.".format(**summary))
```

> The export/import dialogs use plain list-ID inputs to stay self-contained; a later polish can swap in a stack/list tree picker built from `get_all_stacks`/`get_lists_by_stack`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep8_sync_tab.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full EP8 suite**

Run: `pytest -m "not manual" -k ep8 -v`
Expected: all EP8 unit + gui tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ui/settings_panel.py tests/gui/test_ep8_sync_tab.py
git commit -m "feat(ep8): add admin Sync tab (export/import + connectors list)"
```

---

## Self-Review

**1. Spec coverage:**
- Permission contract module → Task 1 ✓
- Roles/permissions tables + `has_permission` (F042) → Task 2 ✓; enforcement gate → Task 3 ✓; admin matrix UI → Task 4 ✓
- `activity_log` + `log_activity`/`get_activity` (F043) → Task 5 ✓; mutation audit hooks → Task 6 ✓; Activity dock → Task 7 ✓
- `elements.updated_at` for conflict resolution → Task 8 ✓
- Bundle export (metadata + previews, F041) → Task 9 ✓; import + timestamp merge → Task 10 ✓
- `CollaborationConnector` seam + `LocalBundleConnector` (seam for deferred F044–F048) → Task 11 ✓
- Sync UI (export/import + connectors list) → Task 12 ✓
- Deferred F044–F048 → documented as follow-on in the design §10; the connector ABC is their only touchpoint here ✓
- Tests unit + headless GUI on `stax_db`/`tmp_path`, no network → every task ✓

**2. Placeholder scan:** New units (`permissions`, roles/permissions CRUD, `activity_log`, `metadata_bundle` export/import, `connector` registry, both settings tabs, `ActivityPanel`) ship complete code. Integration tasks (3, 6, 7, 12) give complete new-method code plus concrete wiring anchored to verified locations (`check_admin_permission:527`, `_apply_migrations:359`, `setup_ui` `addTab`, dock creation in `__init__`), naming the exact reuse points rather than leaving them open.

**3. Type consistency:** `has_permission(username, permission) -> bool` (Task 2) is consumed identically in `check_permission` (Task 3). `get_roles()` returns dicts with a `permissions` list, consumed as such in the Roles tab (Task 4). `log_activity(actor, action, target_type, target_id, detail)` / `get_activity(limit, action, actor, target_type)` (Task 5) are consumed with identical names/kwargs in Tasks 6, 7, 9, 10, 12 and the Roles tab. `export_list_bundle(db, list_id, out_path, source_site, include_previews)` and `import_bundle(db, bundle_path, target_list_id, conflict, previews_dir) -> {"added","updated","skipped"}` (Tasks 9–10) match the connector `push`/`pull` payloads (Task 11) and the Sync-tab `_do_export`/`_do_import` (Task 12). `elements.updated_at` (Task 8) is the exact field the merge compares (Task 10). Connector interface (`key`, `is_available`, `capabilities`, `push`, `pull`) is stable across Tasks 11–12.

**Note for the executor:** EP8 assumes SP1 (migrations) and SP4 (auth) have landed and that EP4's edit path calls `log_activity`. The code uses plain `get_connection()` (verified current signature); if SP1 has added a `write=` kwarg, add it. Task 3/6/7/12 wiring reuses existing seams — read `main.py` (real `MainWindow` class name, dock-creation block, ingest/delete/edit call sites) and `settings_panel.py` (`setup_ui` tab order, `main_window` source) for the exact local names before editing, and adjust. Never weaken a test to pass; mark `xfail(strict)` with the dependency id if a seam is genuinely absent. No third-party SDK (gazu/ftrack/shotgun) may be imported anywhere in EP8 — the deferred bridges are follow-on EPs behind the `CollaborationConnector` seam.
