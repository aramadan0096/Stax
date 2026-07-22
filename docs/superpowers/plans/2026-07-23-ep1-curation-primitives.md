# EP1 — Curation Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add team-shared ratings (0–5) and an admin-configurable color-label palette to StaX, surfaced in the grid and table with inline quick-edit, plus a visible multi-select action tray and context-aware empty states for the top 4 views.

**Architecture:** Two new nullable/defaulted columns on `elements` plus a `labels` table (migration + seed); a small set of validated `DatabaseManager` methods; two new self-contained widgets (`EmptyStateWidget`, `MultiSelectActionTray`) in their own files; and targeted additions to `media_display_widget.py` (grid badges, two table columns) and `settings_panel.py` (a Labels tab). All new behavior is test-driven with the SP0 `stax_db`/headless-Qt fixtures.

**Tech Stack:** Python 3.9, SQLite (via `DatabaseManager`), PySide2 (headless via `QT_QPA_PLATFORM=offscreen`), pytest / pytest-qt.

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat (`from db_manager import DatabaseManager`). **Logging:** `logging`, not `print`. **Commits:** conventional (`feat:`/`test:`).
- **Ratings/labels are team-shared on the element** (columns on `elements`), never per-user.
- **One label per element**; labels come from an **admin-configurable palette** (the `labels` table).
- **Rating is validated 0–5** at the DB boundary (0 = unrated); out-of-range raises `ValueError`.
- **`color_hex` matches `^#[0-9A-Fa-f]{6}$`**; invalid raises `ValueError`.
- **Dependency — SP1:** this EP assumes SP1 has landed, so `DatabaseManager.get_connection(write=True|False)` exists and the migration runner is in place. Writes use `get_connection(write=True)`, reads `get_connection(write=False)`. If executing before SP1, substitute plain `get_connection()` (the current signature) — behavior is identical.
- **Dependency — SP6:** the multi-select context-menu correctness (admin flag read from `self.main_window`), the wired `BatchEditDialog(element_ids, db, parent)`, and `MainWindow.check_admin_permission()` exist and are reused.
- New widgets live in their own files (single responsibility); do not grow `media_display_widget.py` with widget classes.

---

## Key facts (verified against the codebase)

- `elements` table columns today: `element_id, list_fk, name, type, filepath_soft, filepath_hard, is_hard_copy, frame_range, format, comment, tags, preview_path, gif_preview_path, video_preview_path, geometry_preview_path, is_deprecated, file_size, created_at` (`src/db_manager.py:216`).
- DB write idiom: `with self.get_connection() as conn: cursor = conn.cursor(); cursor.execute(...); return cursor.rowcount > 0` (`src/db_manager.py:837`).
- Schema is created by `DatabaseManager._create_schema()` (`src/db_manager.py:183`) on a fresh DB; migrations by `_apply_migrations()` (`src/db_manager.py:359`). The SP0 `stax_db` fixture builds a real `DatabaseManager` on a temp file, so it exercises `_create_schema`.
- Table view: `self.table_view.setColumnCount(6)` + headers `['Name','Format','Frames','Type','Size','Comment']` (`src/ui/media_display_widget.py:178-179`).
- Grid status badges: `_apply_status_badges(self, pixmap, element_id)` (`src/ui/media_display_widget.py:813`).
- Context menu / bulk actions entry: `show_context_menu` (`src/ui/media_display_widget.py:~1120`).
- Settings tabs added via `self.tab_widget.addTab(tab, "<name>")` (`src/ui/settings_panel.py:210+`); panel emits `settings_changed`.

---

## Task 1: Schema — rating + label columns, labels table, seeded palette

**Files:**
- Modify: `src/db_manager.py` (`_create_schema`, `_apply_migrations`)
- Test: `tests/unit/test_ep1_schema.py`

**Interfaces:**
- Produces: `elements.rating` (INTEGER NOT NULL DEFAULT 0), `elements.label_fk` (INTEGER NULL), and table `labels(label_id, name, color_hex, meaning, sort_order)` seeded with 7 rows.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep1_schema.py`:

```python
import pytest


@pytest.mark.unit
def test_elements_has_rating_and_label_columns(stax_db):
    with stax_db.get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(elements)").fetchall()}
    assert "rating" in cols
    assert "label_fk" in cols


@pytest.mark.unit
def test_labels_table_seeded_with_default_palette(stax_db):
    with stax_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT name, color_hex FROM labels ORDER BY sort_order"
        ).fetchall()
    names = [r[0] for r in rows]
    assert names[:3] == ["Reject", "Review", "Approved"]
    assert len(rows) == 7
    for _, color in rows:
        assert color.startswith("#") and len(color) == 7
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep1_schema.py -v`
Expected: FAIL — `rating`/`label_fk` absent, no `labels` table.

- [ ] **Step 3: Add columns + labels table to `_create_schema`**

In `src/db_manager.py`, inside `_create_schema`, add after the `elements` table `CREATE TABLE` block a labels table and seed, and add the two columns to the `elements` `CREATE TABLE` statement:

In the `elements` CREATE, add these two lines before `created_at`:
```sql
                    rating INTEGER NOT NULL DEFAULT 0,
                    label_fk INTEGER,
```

After the `elements` table is created (still inside `_create_schema`), add:
```python
        # Table: Labels (admin-configurable color palette; EP1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS labels (
                label_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                color_hex  TEXT NOT NULL,
                meaning    TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._seed_default_labels(cursor)
```

Add the seed helper as a new method on `DatabaseManager`:
```python
    DEFAULT_LABELS = [
        ("Reject",   "#E5484D", "Rejected / do not use"),
        ("Review",   "#F5D90A", "Needs review"),
        ("Approved", "#30A46C", "Approved for use"),
        ("Blue",     "#3E63DD", ""),
        ("Purple",   "#8E4EC6", ""),
        ("Orange",   "#F76B15", ""),
        ("Gray",     "#8B8D98", ""),
    ]

    def _seed_default_labels(self, cursor):
        """Insert the default label palette if the labels table is empty."""
        cursor.execute("SELECT COUNT(*) FROM labels")
        if cursor.fetchone()[0] == 0:
            for i, (name, color, meaning) in enumerate(self.DEFAULT_LABELS):
                cursor.execute(
                    "INSERT INTO labels (name, color_hex, meaning, sort_order) "
                    "VALUES (?, ?, ?, ?)",
                    (name, color, meaning, i),
                )
```

- [ ] **Step 4: Add an idempotent migration for existing databases**

In `_apply_migrations`, add a migration block (following the file's existing `PRAGMA table_info` guard pattern) that adds the columns and table to already-created databases:

```python
        # EP1: curation columns + labels table
        cursor.execute("PRAGMA table_info(elements)")
        element_cols = {row[1] for row in cursor.fetchall()}
        if "rating" not in element_cols:
            cursor.execute("ALTER TABLE elements ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
        if "label_fk" not in element_cols:
            cursor.execute("ALTER TABLE elements ADD COLUMN label_fk INTEGER")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS labels (
                label_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                color_hex  TEXT NOT NULL,
                meaning    TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._seed_default_labels(cursor)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/test_ep1_schema.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep1_schema.py
git commit -m "feat(ep1): add rating/label columns and seeded labels palette"
```

---

## Task 2: DB API — rating methods

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep1_rating.py`

**Interfaces:**
- Produces: `set_element_rating(element_id, rating) -> None`, `bulk_set_rating(element_ids, rating) -> int`. Raise `ValueError` on rating outside 0–5.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep1_rating.py`:

```python
import pytest


def _make_element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute(
            "INSERT INTO elements (list_fk, name, type) VALUES (1, 'e', '2D')"
        )
    return 1


@pytest.mark.unit
def test_set_and_read_rating(stax_db):
    eid = _make_element(stax_db)
    stax_db.set_element_rating(eid, 4)
    assert stax_db.get_element_by_id(eid)["rating"] == 4


@pytest.mark.unit
def test_rating_out_of_range_raises(stax_db):
    eid = _make_element(stax_db)
    with pytest.raises(ValueError):
        stax_db.set_element_rating(eid, 6)
    with pytest.raises(ValueError):
        stax_db.set_element_rating(eid, -1)


@pytest.mark.unit
def test_bulk_set_rating_returns_count(stax_db):
    eid = _make_element(stax_db)
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'e2', '2D')")
    n = stax_db.bulk_set_rating([1, 2], 5)
    assert n == 2
    assert stax_db.get_element_by_id(2)["rating"] == 5
```

> Note: if `create_stack` is named differently after SP1, use the consolidated stack-creation method; the elements insert via raw SQL keeps this test independent of that name.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep1_rating.py -v`
Expected: FAIL — `set_element_rating` not defined.

- [ ] **Step 3: Implement the methods**

Add to `DatabaseManager` (near `update_element`):

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_ep1_rating.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep1_rating.py
git commit -m "feat(ep1): add set_element_rating/bulk_set_rating with validation"
```

---

## Task 3: DB API — label methods + labels CRUD

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep1_labels.py`

**Interfaces:**
- Produces: `set_element_label(element_id, label_fk|None)`, `bulk_set_label(element_ids, label_fk|None) -> int`, `get_labels() -> list[dict]`, `create_label(name, color_hex, meaning="", sort_order=0) -> int`, `update_label(label_id, **fields)`, `delete_label(label_id)` (nulls referencing `elements.label_fk`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep1_labels.py`:

```python
import pytest


def _element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1, 'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'e', '2D')")
    return 1


@pytest.mark.unit
def test_get_labels_returns_seeded_palette(stax_db):
    labels = stax_db.get_labels()
    assert len(labels) == 7
    assert labels[0]["name"] == "Reject"
    assert labels[0]["color_hex"] == "#E5484D"


@pytest.mark.unit
def test_create_label_validates_color(stax_db):
    with pytest.raises(ValueError):
        stax_db.create_label("Bad", "red")
    lid = stax_db.create_label("Teal", "#12A594", "custom", sort_order=9)
    assert any(l["label_id"] == lid and l["name"] == "Teal" for l in stax_db.get_labels())


@pytest.mark.unit
def test_set_element_label_and_clear(stax_db):
    eid = _element(stax_db)
    stax_db.set_element_label(eid, 2)
    assert stax_db.get_element_by_id(eid)["label_fk"] == 2
    stax_db.set_element_label(eid, None)
    assert stax_db.get_element_by_id(eid)["label_fk"] is None


@pytest.mark.unit
def test_delete_label_nulls_referencing_elements(stax_db):
    eid = _element(stax_db)
    stax_db.set_element_label(eid, 3)
    stax_db.delete_label(3)
    assert stax_db.get_element_by_id(eid)["label_fk"] is None
    assert all(l["label_id"] != 3 for l in stax_db.get_labels())


@pytest.mark.unit
def test_bulk_set_label_returns_count(stax_db):
    _element(stax_db)
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1, 'e2', '2D')")
    assert stax_db.bulk_set_label([1, 2], 1) == 2
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep1_labels.py -v`
Expected: FAIL — label methods not defined.

- [ ] **Step 3: Implement the methods**

Add to `DatabaseManager`:

```python
    import re as _re  # module-level import preferred; if `re` already imported at top, skip this

    _COLOR_RE = __import__("re").compile(r"^#[0-9A-Fa-f]{6}$")
    _LABEL_FIELDS = {"name", "color_hex", "meaning", "sort_order"}

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
```

> Implementation note: put `import re` at the top of `db_manager.py` (if not already present) and use `re.compile(...)` for `_COLOR_RE` rather than the inline `__import__` shown above; the inline form is only to keep this snippet self-contained.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_ep1_labels.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep1_labels.py
git commit -m "feat(ep1): add label CRUD and element label setters"
```

---

## Task 4: `EmptyStateWidget`

**Files:**
- Create: `src/ui/empty_state_widget.py`
- Test: `tests/gui/test_ep1_empty_state.py`

**Interfaces:**
- Produces: `EmptyStateWidget(headline, message, primary_action=None, secondary_action=None, kind="informational", parent=None)` where each action is `(label_str, callable)`; exposes `.primary_button` / `.secondary_button` (or `None`).

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep1_empty_state.py`:

```python
import pytest

from ui.empty_state_widget import EmptyStateWidget


@pytest.mark.gui
def test_renders_headline_and_fires_primary(qtbot):
    fired = {"n": 0}
    w = EmptyStateWidget(
        "No assets yet",
        "Ingest footage to get started.",
        primary_action=("Ingest files…", lambda: fired.__setitem__("n", fired["n"] + 1)),
        kind="action",
    )
    qtbot.addWidget(w)
    assert "No assets yet" in w.headline_label.text()
    w.primary_button.click()
    assert fired["n"] == 1


@pytest.mark.gui
def test_secondary_optional(qtbot):
    w = EmptyStateWidget("Nothing here", "…", primary_action=("Browse", lambda: None))
    qtbot.addWidget(w)
    assert w.secondary_button is None
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep1_empty_state.py -v`
Expected: FAIL — module `ui.empty_state_widget` missing.

- [ ] **Step 3: Implement the widget**

Create `src/ui/empty_state_widget.py`:

```python
# -*- coding: utf-8 -*-
"""Reusable context-aware empty-state widget (EP1)."""

from PySide2 import QtWidgets, QtCore

_KINDS = ("informational", "action", "celebratory")


class EmptyStateWidget(QtWidgets.QWidget):
    """A centered empty-state: headline, one sentence, and up to two actions.

    Each action is a (label, callable) tuple. `kind` is one of
    informational | action | celebratory (selects tone/icon).
    """

    def __init__(self, headline, message, primary_action=None,
                 secondary_action=None, kind="informational", parent=None):
        super(EmptyStateWidget, self).__init__(parent)
        if kind not in _KINDS:
            kind = "informational"
        self.kind = kind

        outer = QtWidgets.QVBoxLayout(self)
        outer.setAlignment(QtCore.Qt.AlignCenter)

        self.headline_label = QtWidgets.QLabel(headline)
        self.headline_label.setAlignment(QtCore.Qt.AlignCenter)
        f = self.headline_label.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        self.headline_label.setFont(f)

        self.message_label = QtWidgets.QLabel(message)
        self.message_label.setAlignment(QtCore.Qt.AlignCenter)
        self.message_label.setWordWrap(True)

        outer.addStretch(1)
        outer.addWidget(self.headline_label)
        outer.addWidget(self.message_label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setAlignment(QtCore.Qt.AlignCenter)
        self.primary_button = None
        self.secondary_button = None

        if primary_action is not None:
            label, cb = primary_action
            self.primary_button = QtWidgets.QPushButton(label)
            self.primary_button.setDefault(True)
            self.primary_button.clicked.connect(cb)
            buttons.addWidget(self.primary_button)

        if secondary_action is not None:
            label, cb = secondary_action
            self.secondary_button = QtWidgets.QPushButton(label)
            self.secondary_button.clicked.connect(cb)
            buttons.addWidget(self.secondary_button)

        outer.addLayout(buttons)
        outer.addStretch(1)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/gui/test_ep1_empty_state.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/empty_state_widget.py tests/gui/test_ep1_empty_state.py
git commit -m "feat(ep1): add reusable EmptyStateWidget"
```

---

## Task 5: `MultiSelectActionTray`

**Files:**
- Create: `src/ui/multi_select_action_tray.py`
- Test: `tests/gui/test_ep1_action_tray.py`

**Interfaces:**
- Consumes: a `db` with `bulk_set_rating`, `bulk_set_label`, `get_labels` (Tasks 2–3); a `main_window` with `check_admin_permission() -> bool`.
- Produces: `MultiSelectActionTray(db, main_window, parent=None)` with `set_selection(element_ids: list[int])` (shows when ≥2, hides otherwise, updates the count label) and signals `rate_requested(int)`, `label_requested(object)`, `tag_requested()`, `favorite_requested()`, `playlist_requested()`, `deprecate_requested()`, `delete_requested()`, `edit_requested()`. Buttons wired to bulk DB ops for Rate/Label; other actions emit signals the host connects.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep1_action_tray.py`:

```python
import pytest

from ui.multi_select_action_tray import MultiSelectActionTray


class _FakeDB:
    def __init__(self):
        self.rated = None
        self.labeled = None
    def bulk_set_rating(self, ids, rating):
        self.rated = (list(ids), rating); return len(ids)
    def bulk_set_label(self, ids, label_fk):
        self.labeled = (list(ids), label_fk); return len(ids)
    def get_labels(self):
        return [{"label_id": 1, "name": "Reject", "color_hex": "#E5484D", "meaning": ""}]


class _FakeMain:
    def __init__(self, admin=True):
        self._admin = admin
    def check_admin_permission(self):
        return self._admin


@pytest.mark.gui
def test_hidden_below_two_selected(qtbot):
    tray = MultiSelectActionTray(_FakeDB(), _FakeMain())
    qtbot.addWidget(tray)
    tray.set_selection([1])
    assert not tray.isVisibleTo(tray.parent()) or tray.isHidden()
    tray.set_selection([1, 2, 3])
    assert "3" in tray.count_label.text()


@pytest.mark.gui
def test_rate_button_calls_bulk_rating(qtbot):
    db = _FakeDB()
    tray = MultiSelectActionTray(db, _FakeMain())
    qtbot.addWidget(tray)
    tray.set_selection([4, 5])
    tray.apply_rating(3)          # invoked by the star popup
    assert db.rated == ([4, 5], 3)


@pytest.mark.gui
def test_delete_gated_for_non_admin(qtbot):
    tray = MultiSelectActionTray(_FakeDB(), _FakeMain(admin=False))
    qtbot.addWidget(tray)
    tray.set_selection([1, 2])
    assert tray.delete_button.isEnabled() is False
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep1_action_tray.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the widget**

Create `src/ui/multi_select_action_tray.py`:

```python
# -*- coding: utf-8 -*-
"""Visible multi-select action tray for bulk curation (EP1)."""

import logging

from PySide2 import QtWidgets, QtCore

logger = logging.getLogger(__name__)


class MultiSelectActionTray(QtWidgets.QWidget):
    """Bottom bar shown when >=2 items are selected.

    Rate/Label act directly via bulk DB calls; the rest emit signals the
    host (MediaDisplayWidget) connects to its existing bulk handlers.
    """

    rate_requested     = QtCore.Signal(int)
    label_requested    = QtCore.Signal(object)   # label_id or None
    tag_requested      = QtCore.Signal()
    favorite_requested = QtCore.Signal()
    playlist_requested = QtCore.Signal()
    deprecate_requested = QtCore.Signal()
    delete_requested   = QtCore.Signal()
    edit_requested     = QtCore.Signal()

    def __init__(self, db, main_window, parent=None):
        super(MultiSelectActionTray, self).__init__(parent)
        self.db = db
        self.main_window = main_window
        self._selection = []

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)

        self.count_label = QtWidgets.QLabel("0 selected")
        row.addWidget(self.count_label)
        row.addStretch(1)

        self.rate_button     = self._add_button(row, "Rate", self._show_rate_menu)
        self.label_button    = self._add_button(row, "Label", self._show_label_menu)
        self.tag_button      = self._add_button(row, "Add tag", self.tag_requested.emit)
        self.favorite_button = self._add_button(row, "Favorite", self.favorite_requested.emit)
        self.playlist_button = self._add_button(row, "Add to playlist", self.playlist_requested.emit)
        self.deprecate_button = self._add_button(row, "Deprecate", self.deprecate_requested.emit)
        self.delete_button   = self._add_button(row, "Delete", self.delete_requested.emit)
        self.edit_button     = self._add_button(row, "Edit…", self.edit_requested.emit)

        self.hide()

    def _add_button(self, row, text, slot):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(slot)
        row.addWidget(b)
        return b

    def set_selection(self, element_ids):
        self._selection = list(element_ids)
        n = len(self._selection)
        self.count_label.setText("{} selected".format(n))
        is_admin = bool(self.main_window.check_admin_permission())
        self.delete_button.setEnabled(is_admin)
        self.deprecate_button.setEnabled(is_admin)
        self.setVisible(n >= 2)

    # --- Rate ---
    def _show_rate_menu(self):
        menu = QtWidgets.QMenu(self)
        for stars in range(1, 6):
            act = menu.addAction("{} star{}".format(stars, "s" if stars > 1 else ""))
            act.triggered.connect(lambda checked=False, s=stars: self.apply_rating(s))
        clear = menu.addAction("Clear rating")
        clear.triggered.connect(lambda: self.apply_rating(0))
        menu.exec_(self.rate_button.mapToGlobal(self.rate_button.rect().bottomLeft()))

    def apply_rating(self, stars):
        if not self._selection:
            return
        self.db.bulk_set_rating(self._selection, stars)
        self.rate_requested.emit(stars)

    # --- Label ---
    def _show_label_menu(self):
        menu = QtWidgets.QMenu(self)
        for lbl in self.db.get_labels():
            act = menu.addAction(lbl["name"])
            act.triggered.connect(
                lambda checked=False, lid=lbl["label_id"]: self.apply_label(lid))
        clear = menu.addAction("Clear label")
        clear.triggered.connect(lambda: self.apply_label(None))
        menu.exec_(self.label_button.mapToGlobal(self.label_button.rect().bottomLeft()))

    def apply_label(self, label_id):
        if not self._selection:
            return
        self.db.bulk_set_label(self._selection, label_id)
        self.label_requested.emit(label_id)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/gui/test_ep1_action_tray.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/multi_select_action_tray.py tests/gui/test_ep1_action_tray.py
git commit -m "feat(ep1): add MultiSelectActionTray with bulk rate/label + admin gating"
```

---

## Task 6: Grid badges + hover quick-edit

**Files:**
- Modify: `src/ui/media_display_widget.py` (`_apply_status_badges` at line 813; add a hover quick-edit handler)
- Test: `tests/gui/test_ep1_grid_badges.py`

**Interfaces:**
- Consumes: `db.get_element_by_id` (for `rating`/`label_fk`), `db.get_labels`, `db.set_element_rating`, `db.set_element_label`.
- Produces: `_draw_curation_badges(self, pixmap, element_id) -> QPixmap` (stars + label chip) called from `_apply_status_badges`; `quick_set_rating(self, element_id, stars)` / `quick_set_label(self, element_id, label_id)` that write via the DB and repaint that item only.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep1_grid_badges.py`:

```python
import pytest
from PySide2 import QtGui


@pytest.mark.gui
def test_quick_set_rating_writes_through(qtbot, stax_db, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_DB", str(tmp_path / "app.db"))
    from ui.media_display_widget import MediaDisplayWidget
    # seed one element
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk, name, type) VALUES (1,'e','2D')")
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w.quick_set_rating(1, 4)
    assert stax_db.get_element_by_id(1)["rating"] == 4


@pytest.mark.gui
def test_draw_curation_badges_returns_pixmap(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    px = QtGui.QPixmap(128, 128)
    px.fill()
    out = w._draw_curation_badges(px, element_id=None)
    assert isinstance(out, QtGui.QPixmap)
```

> If `MediaDisplayWidget.__init__` needs more than `db` (e.g. a config), match the real constructor signature when writing the test; the two calls above are the only construction points.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep1_grid_badges.py -v`
Expected: FAIL — `_draw_curation_badges` / `quick_set_rating` not defined.

- [ ] **Step 3: Implement badge drawing + quick setters**

Add to `MediaDisplayWidget` (near `_apply_status_badges`, line 813):

```python
    def _draw_curation_badges(self, pixmap, element_id):
        """Overlay a star strip and a label color-chip onto a thumbnail."""
        from PySide2 import QtGui, QtCore
        result = QtGui.QPixmap(pixmap)
        if element_id is None:
            return result
        try:
            el = self.db.get_element_by_id(element_id) or {}
        except Exception:
            logger.exception("failed reading curation state for %s", element_id)
            return result
        rating = el.get("rating", 0) or 0
        label_fk = el.get("label_fk")

        painter = QtGui.QPainter(result)
        try:
            # star strip, bottom-left
            if rating:
                painter.setPen(QtGui.QColor("#F5D90A"))
                painter.drawText(6, result.height() - 6, "★" * int(rating))
            # label chip, top-right
            if label_fk:
                color = self._label_color(label_fk)
                if color:
                    painter.fillRect(result.width() - 16, 6, 10, 10, QtGui.QColor(color))
        finally:
            painter.end()
        return result

    def _label_color(self, label_fk):
        """Resolve a label_fk to its color_hex (cached per refresh)."""
        cache = getattr(self, "_label_color_cache", None)
        if cache is None:
            cache = {l["label_id"]: l["color_hex"] for l in self.db.get_labels()}
            self._label_color_cache = cache
        return cache.get(label_fk)

    def quick_set_rating(self, element_id, stars):
        self.db.set_element_rating(element_id, stars)
        self._refresh_item(element_id)

    def quick_set_label(self, element_id, label_id):
        self.db.set_element_label(element_id, label_id)
        self._label_color_cache = None  # force re-resolve
        self._refresh_item(element_id)
```

Then, in `_apply_status_badges` (line 813), append the curation overlay before returning the pixmap:

```python
        # EP1: overlay rating stars + label chip
        pixmap = self._draw_curation_badges(pixmap, element_id)
        return pixmap
```

If `MediaDisplayWidget` has no `_refresh_item(element_id)` helper yet, add a minimal one that re-runs the existing per-item thumbnail update for that element (reuse the loop body of `_update_views_with_elements`); if a full-view refresh is the only available primitive, call that instead and note it for the SP2 in-place-update work.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/gui/test_ep1_grid_badges.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep1_grid_badges.py
git commit -m "feat(ep1): draw rating/label badges and add grid quick-edit setters"
```

---

## Task 7: Table Rating/Label columns

**Files:**
- Modify: `src/ui/media_display_widget.py` (line 178–179 column setup; the row-population code)
- Test: `tests/gui/test_ep1_table_columns.py`

**Interfaces:**
- Consumes: `db.get_element_by_id`, `db.get_labels`.
- Produces: an 8-column table with headers `[... , 'Rating', 'Label']`; a `_rating_cell_text(rating)` helper returning a star string; label cell colored by the element's label.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep1_table_columns.py`:

```python
import pytest


@pytest.mark.gui
def test_table_has_rating_and_label_columns(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    assert w.table_view.columnCount() == 8
    headers = [w.table_view.horizontalHeaderItem(i).text()
               for i in range(w.table_view.columnCount())]
    assert headers[-2:] == ["Rating", "Label"]


@pytest.mark.gui
def test_rating_cell_text(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    assert w._rating_cell_text(3) == "★★★"
    assert w._rating_cell_text(0) == ""
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep1_table_columns.py -v`
Expected: FAIL — column count is 6.

- [ ] **Step 3: Grow the table + populate the new cells**

At `src/ui/media_display_widget.py:178-179`, change:

```python
        self.table_view.setColumnCount(8)
        self.table_view.setHorizontalHeaderLabels(
            ['Name', 'Format', 'Frames', 'Type', 'Size', 'Comment', 'Rating', 'Label'])
```

Add the helper:

```python
    @staticmethod
    def _rating_cell_text(rating):
        return "★" * int(rating or 0)
```

In the table-row population code (where the existing 6 columns are set per element — search for `setItem(row, 5` / the Comment column), append:

```python
        from PySide2 import QtWidgets, QtGui
        rating_item = QtWidgets.QTableWidgetItem(self._rating_cell_text(element.get('rating', 0)))
        self.table_view.setItem(row, 6, rating_item)

        label_item = QtWidgets.QTableWidgetItem("")
        label_fk = element.get('label_fk')
        if label_fk:
            color = self._label_color(label_fk)
            if color:
                label_item.setBackground(QtGui.QBrush(QtGui.QColor(color)))
        self.table_view.setItem(row, 7, label_item)
```

(`element` is the per-row dict already used to fill columns 0–5; `_label_color` comes from Task 6.)

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/gui/test_ep1_table_columns.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep1_table_columns.py
git commit -m "feat(ep1): add Rating and Label columns to the table view"
```

---

## Task 8: Labels settings tab (admin-gated)

**Files:**
- Modify: `src/ui/settings_panel.py`
- Test: `tests/gui/test_ep1_labels_tab.py`

**Interfaces:**
- Consumes: `db.get_labels`, `db.create_label`, `db.update_label`, `db.delete_label`; `main_window.check_admin_permission`.
- Produces: `_build_labels_tab(self) -> QWidget` added via `self.tab_widget.addTab(tab, "Labels")`; a `labels_table` populated from `get_labels`; Add/Edit/Delete controls disabled for non-admins.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep1_labels_tab.py`:

```python
import pytest


class _FakeMain:
    def __init__(self, admin): self._a = admin
    def check_admin_permission(self): return self._a


@pytest.mark.gui
def test_labels_tab_lists_palette_and_gates_admin(qtbot, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=None, db_manager=stax_db, main_window=_FakeMain(admin=False))
    qtbot.addWidget(panel)
    assert panel.labels_table.rowCount() == 7
    assert panel.add_label_button.isEnabled() is False


@pytest.mark.gui
def test_admin_can_add_label(qtbot, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(config=None, db_manager=stax_db, main_window=_FakeMain(admin=True))
    qtbot.addWidget(panel)
    panel._create_label_row("Teal", "#12A594", "custom")
    assert any(l["name"] == "Teal" for l in stax_db.get_labels())
```

> Match `SettingsPanel.__init__`'s real signature; if it does not currently take `main_window`, thread it through (the panel already needs admin state for the Security Admin tab, so reuse that source instead of adding a param).

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep1_labels_tab.py -v`
Expected: FAIL — `labels_table` / `_build_labels_tab` missing.

- [ ] **Step 3: Implement the tab**

In `SettingsPanel.setup_ui`, after the other `addTab` calls, add:

```python
        self.tab_widget.addTab(self._build_labels_tab(), "Labels")
```

Add the builder and helper:

```python
    def _build_labels_tab(self):
        from PySide2 import QtWidgets
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        self.labels_table = QtWidgets.QTableWidget(0, 3)
        self.labels_table.setHorizontalHeaderLabels(["Color", "Name", "Meaning"])
        layout.addWidget(self.labels_table)

        controls = QtWidgets.QHBoxLayout()
        self.add_label_button = QtWidgets.QPushButton("Add…")
        self.edit_label_button = QtWidgets.QPushButton("Edit…")
        self.delete_label_button = QtWidgets.QPushButton("Delete")
        for b in (self.add_label_button, self.edit_label_button, self.delete_label_button):
            controls.addWidget(b)
        layout.addLayout(controls)

        self.add_label_button.clicked.connect(self._on_add_label)
        self.delete_label_button.clicked.connect(self._on_delete_label)

        is_admin = bool(self.main_window.check_admin_permission()) if self.main_window else False
        for b in (self.add_label_button, self.edit_label_button, self.delete_label_button):
            b.setEnabled(is_admin)

        self._reload_labels()
        return tab

    def _reload_labels(self):
        from PySide2 import QtWidgets, QtGui
        labels = self.db.get_labels()
        self.labels_table.setRowCount(len(labels))
        for row, lbl in enumerate(labels):
            swatch = QtWidgets.QTableWidgetItem("")
            swatch.setBackground(QtGui.QBrush(QtGui.QColor(lbl["color_hex"])))
            self.labels_table.setItem(row, 0, swatch)
            self.labels_table.setItem(row, 1, QtWidgets.QTableWidgetItem(lbl["name"]))
            self.labels_table.setItem(row, 2, QtWidgets.QTableWidgetItem(lbl.get("meaning", "") or ""))

    def _create_label_row(self, name, color_hex, meaning):
        self.db.create_label(name, color_hex, meaning)
        self._reload_labels()
        self.settings_changed.emit()

    def _on_add_label(self):
        from PySide2 import QtWidgets
        name, ok = QtWidgets.QInputDialog.getText(self, "New label", "Name:")
        if not ok or not name:
            return
        color = QtWidgets.QColorDialog.getColor()
        if not color.isValid():
            return
        self._create_label_row(name, color.name(), "")

    def _on_delete_label(self):
        row = self.labels_table.currentRow()
        if row < 0:
            return
        labels = self.db.get_labels()
        if row < len(labels):
            self.db.delete_label(labels[row]["label_id"])
            self._reload_labels()
            self.settings_changed.emit()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/gui/test_ep1_labels_tab.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/settings_panel.py tests/gui/test_ep1_labels_tab.py
git commit -m "feat(ep1): add admin-gated Labels settings tab"
```

---

## Task 9: Wire the action tray + empty states into MediaDisplayWidget

**Files:**
- Modify: `src/ui/media_display_widget.py`, `main.py`
- Test: `tests/gui/test_ep1_integration.py`

**Interfaces:**
- Consumes: `MultiSelectActionTray` (Task 5), `EmptyStateWidget` (Task 4), the bulk DB ops.
- Produces: a tray instance docked below the views, fed by the selection-changed handler; empty-state selection via `_show_empty_state(kind_key)` for `library` / `list` / `search` / `favorites`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep1_integration.py`:

```python
import pytest


@pytest.mark.gui
def test_tray_shows_on_multiselect(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w.action_tray.set_selection([1, 2])
    assert w.action_tray.isVisible() or not w.action_tray.isHidden()


@pytest.mark.gui
def test_empty_state_library_has_ingest_action(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w._show_empty_state("library")
    assert w.current_empty_state.primary_button.text().lower().startswith("ingest")
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep1_integration.py -v`
Expected: FAIL — `action_tray` / `_show_empty_state` missing.

- [ ] **Step 3: Instantiate and wire the tray + empty states**

In `MediaDisplayWidget.__init__` (after the views/stacked widget are built), add:

```python
        from ui.multi_select_action_tray import MultiSelectActionTray
        self.action_tray = MultiSelectActionTray(self.db, getattr(self, "main_window", None) or self._resolve_main_window())
        self.layout().addWidget(self.action_tray)  # dock below the views
        # reuse existing bulk handlers for the non-rate/label actions
        self.action_tray.tag_requested.connect(self._bulk_add_tag_selected)
        self.action_tray.favorite_requested.connect(self.bulk_add_to_favorites)
        self.action_tray.playlist_requested.connect(self._bulk_add_to_playlist_selected)
        self.action_tray.deprecate_requested.connect(self._bulk_deprecate_selected)
        self.action_tray.delete_requested.connect(self._bulk_delete_selected)
        self.action_tray.edit_requested.connect(self._open_batch_edit_selected)
        self.action_tray.rate_requested.connect(lambda _stars: self.refresh_current_view())
        self.action_tray.label_requested.connect(lambda _l: self.refresh_current_view())
```

Connect selection changes on both views to feed the tray:

```python
    def _on_selection_changed_ep1(self):
        ids = self.get_selected_element_ids()   # existing helper returning list[int]
        self.action_tray.set_selection(ids)
```

Wire this to the gallery/table selection signals where other selection handling already happens (search for `selectionChanged` / `itemSelectionChanged`). If a `get_selected_element_ids` helper does not exist, add a small one that maps selected items to their element ids using the same item→id mapping the context menu already uses.

Add the empty-state driver:

```python
    def _show_empty_state(self, kind_key, query=None, list_name=None):
        from ui.empty_state_widget import EmptyStateWidget
        specs = {
            "library": ("No assets yet",
                        "Ingest footage, sequences, or toolsets to get started.",
                        ("Ingest files…", self._request_ingest_files), None, "action"),
            "list":    ("This list is empty",
                        "Add assets to {}.".format(list_name or "this list"),
                        ("Ingest into this list…", self._request_ingest_files), None, "action"),
            "search":  ("No matches for '{}'".format(query or ""),
                        "Try fewer terms or clear filters.",
                        ("Clear filters", self._request_clear_filters), None, "informational"),
            "favorites": ("Nothing here yet",
                        "Star assets or add them to a playlist to collect them.",
                        ("Browse library", self._request_browse_library), None, "informational"),
        }
        headline, message, primary, secondary, kind = specs[kind_key]
        self.current_empty_state = EmptyStateWidget(headline, message, primary, secondary, kind)
        # place on the stacked widget's empty page (index 0)
        self._set_empty_page_widget(self.current_empty_state)
```

Provide the small callback hooks (`_request_ingest_files`, `_request_clear_filters`, `_request_browse_library`) that call the existing MainWindow/toolbar actions; and `_set_empty_page_widget` that swaps the widget shown on the stacked widget's index-0 empty page.

- [ ] **Step 4: Add the MainWindow callbacks used by empty states**

In `main.py`, ensure `MainWindow` exposes the actions the empty-state buttons trigger (reuse existing handlers): ingest (`Ctrl+I`), clear-filters (search reset), and select-library. Expose them so `MediaDisplayWidget._request_*` can call `self.main_window.<handler>()`. If they already exist under other names, wire `_request_ingest_files` etc. to those names directly.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/gui/test_ep1_integration.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full EP1 suite**

Run: `pytest -m "not manual" -k ep1 -v`
Expected: all EP1 unit + gui tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/ui/media_display_widget.py main.py tests/gui/test_ep1_integration.py
git commit -m "feat(ep1): wire action tray and context-aware empty states into media view"
```

---

## Self-Review

**1. Spec coverage:**
- Data model (rating, label_fk, labels table, seed) → Task 1 ✓
- DB API rating methods → Task 2 ✓; label methods + CRUD → Task 3 ✓
- Labels settings tab (admin-gated) → Task 8 ✓
- Grid badges + inline quick-edit → Task 6 ✓
- Table Rating/Label columns → Task 7 ✓
- MultiSelectActionTray (full curation set + admin gating) → Task 5, wired in Task 9 ✓
- EmptyStateWidget + 4 views → Task 4, wired in Task 9 ✓
- Tests unit + headless GUI → every task ✓

**2. Placeholder scan:** New units (labels table, DB methods, `EmptyStateWidget`, `MultiSelectActionTray`) have complete code. Integration tasks (6, 7, 9) give complete code for the new methods plus concrete insertion snippets anchored to verified line numbers/method names; where a host helper (`_refresh_item`, `get_selected_element_ids`, `_set_empty_page_widget`) may or may not pre-exist, the step names the exact fallback rather than leaving it open. No "TBD/handle appropriately".

**3. Type consistency:** `set_element_rating`/`bulk_set_rating`/`set_element_label`/`bulk_set_label`/`get_labels`/`create_label`/`update_label`/`delete_label` are defined in Tasks 2–3 and consumed with identical names in Tasks 5–9. `_label_color` (Task 6) is reused in Task 7. `MultiSelectActionTray(db, main_window)` and its `set_selection`/`apply_rating`/`apply_label` match between Task 5 and Task 9. `EmptyStateWidget(headline, message, primary_action, secondary_action, kind)` matches between Task 4 and Task 9.

**Note for the executor:** EP1 assumes SP1 + SP6 have landed. If running earlier, (a) use `get_connection()` without `write=`, and (b) supply the `BatchEditDialog` / `check_admin_permission` seams the tray and tabs consume, or stub them. Never weaken a test to pass — mark `xfail(strict)` with the dependency id if a seam is genuinely absent.
