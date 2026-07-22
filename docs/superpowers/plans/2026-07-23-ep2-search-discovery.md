# EP2 — Search & Discovery UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn StaX browsing into real discovery — a composable `FilterSpec` + SQL query builder, a faceted filter drawer with removable chips and a live result count, personal saved searches, shared smart-collection nav nodes, and dependency-free text quality (synonyms, "did you mean", recent queries).

**Architecture:** A serializable `FilterSpec` (JSON) is the single source of truth for every filter surface. `DatabaseManager` gains a parameterized query builder (`search_elements_advanced`, `count_elements_advanced`, `get_facet_counts`) plus CRUD for four new tables. New widgets (`FacetDrawer`, `FilterChipBar`) are self-contained files that emit/consume `FilterSpec`. Text quality uses only stdlib `difflib`. All TDD on the SP0 `stax_db`/headless-Qt fixtures.

**Tech Stack:** Python 3.9, SQLite (via `DatabaseManager`), PySide2 (headless offscreen), pytest / pytest-qt, stdlib `json` + `difflib`.

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat. **Logging:** `logging`, not `print`. **Commits:** conventional.
- **No new dependencies.** Structured facets via a SQL query builder; text typo help via stdlib `difflib`. No FTS5, no AI.
- **All dynamic SQL uses fixed, code-literal column names and parameterized values** (SP1 whitelisting pattern) — never format a user value into SQL.
- **Saved searches are personal** (scoped by `user_name`); **smart collections are team-shared** (admin-managed).
- **Ratings/labels (EP1) are read-only facets here.**
- **Dependency — EP1:** `elements.rating`, `elements.label_fk`, and the `labels` table exist.
- **Dependency — SP1:** `get_connection(write=True|False)` exists and the migration runner is in place. If executing before SP1, use plain `get_connection()`.
- New widgets and the filter model live in their own files (single responsibility).

---

## Key facts (verified against the codebase)

- `search_elements` uses `"... WHERE {} LIKE ?".format(property_name)` (`src/db_manager.py:886`) — SP1 whitelists this; EP2's builder uses only literal column names.
- `get_all_tags() -> sorted list[str]`, parsing the comma-joined `elements.tags` (`src/db_manager.py:1307`).
- `elements.tags` is a comma-joined string, values may have spaces after commas.
- DB write idiom: `with self.get_connection() as conn: cursor = conn.cursor(); ...` (`src/db_manager.py:882`).
- `add_favorite(element_id, machine_name, user_name=None)` — the per-user scoping pattern (`src/db_manager.py:898`).
- Inline search box + handler: `on_search(self, text)` (`src/ui/media_display_widget.py:546`), placeholder at line 71.
- Left nav: `StacksListsPanel` with Playlists list + Stacks/Lists tree (`src/ui/stacks_lists_panel.py:19`).
- SP0 fixture `stax_db` builds a real `DatabaseManager` on a temp DB (has EP1 columns after EP1 lands).

---

# Cluster 2A — Faceted filtering core

## Task 1: `FilterSpec` model

**Files:**
- Create: `src/filter_spec.py`
- Test: `tests/unit/test_ep2_filter_spec.py`

**Interfaces:**
- Produces: `empty_filter() -> dict`, `is_active(spec) -> bool`, `FILTER_VERSION` (int), `normalize(spec) -> dict` (fills defaults, coerces types).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_filter_spec.py`:

```python
import pytest
from filter_spec import empty_filter, is_active, normalize, FILTER_VERSION


@pytest.mark.unit
def test_empty_filter_is_inactive():
    spec = empty_filter()
    assert spec["v"] == FILTER_VERSION
    assert is_active(spec) is False


@pytest.mark.unit
def test_active_when_any_clause_set():
    assert is_active(normalize({"text": "fire"})) is True
    assert is_active(normalize({"types": ["2D"]})) is True
    assert is_active(normalize({"rating_min": 3})) is True


@pytest.mark.unit
def test_normalize_fills_defaults_and_coerces():
    spec = normalize({"rating_min": "4", "types": None})
    assert spec["rating_min"] == 4
    assert spec["types"] == []
    assert spec["text"] == ""
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_filter_spec.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/filter_spec.py`:

```python
# -*- coding: utf-8 -*-
"""Serializable filter model shared by the drawer, chips, saved searches,
and smart collections (EP2)."""

FILTER_VERSION = 1

_LIST_KEYS = ("types", "formats", "tags_all", "tags_any",
              "tags_exclude", "formats_exclude", "label_fks")
_FLAG_KEYS = ("is_deprecated", "is_hard_copy")
_INT_KEYS = ("rating_min", "list_fk", "stack_fk")


def empty_filter():
    spec = {"v": FILTER_VERSION, "text": ""}
    for k in _LIST_KEYS:
        spec[k] = []
    for k in _FLAG_KEYS:
        spec[k] = None
    for k in _INT_KEYS:
        spec[k] = 0 if k == "rating_min" else None
    return spec


def normalize(spec):
    """Return a full spec with defaults filled and types coerced."""
    out = empty_filter()
    if not spec:
        return out
    out["text"] = str(spec.get("text") or "")
    for k in _LIST_KEYS:
        val = spec.get(k) or []
        out[k] = list(val)
    for k in _FLAG_KEYS:
        out[k] = spec.get(k, None)
    for k in _INT_KEYS:
        v = spec.get(k, None)
        if k == "rating_min":
            out[k] = int(v) if v else 0
        else:
            out[k] = int(v) if v else None
    out["v"] = FILTER_VERSION
    return out


def is_active(spec):
    s = normalize(spec)
    if s["text"]:
        return True
    if s["rating_min"]:
        return True
    for k in _LIST_KEYS:
        if s[k]:
            return True
    for k in _FLAG_KEYS:
        if s[k] is not None:
            return True
    if s["list_fk"] or s["stack_fk"]:
        return True
    return False
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_filter_spec.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/filter_spec.py tests/unit/test_ep2_filter_spec.py
git commit -m "feat(ep2): add serializable FilterSpec model"
```

---

## Task 2: Query builder — `search_elements_advanced` + count

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep2_query_builder.py`

**Interfaces:**
- Consumes: `normalize` from `filter_spec`.
- Produces: `search_elements_advanced(filter_spec, limit=None, offset=0) -> list[dict]`, `count_elements_advanced(filter_spec) -> int`, and static `_build_filter_where(spec) -> (str, list)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_query_builder.py`:

```python
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        rows = [
            ("plate_a", "2D", ".exr", "fire,city", 5, 0),
            ("plate_b", "2D", ".mov", "water", 2, 0),
            ("geo_c",   "3D", ".abc", "fire", 0, 1),
        ]
        for name, typ, fmt, tags, rating, deprecated in rows:
            conn.execute(
                "INSERT INTO elements (list_fk, name, type, format, tags, rating, is_deprecated) "
                "VALUES (1,?,?,?,?,?,?)",
                (name, typ, fmt, tags, rating, deprecated),
            )


@pytest.mark.unit
def test_filter_by_type_and_rating(stax_db):
    _seed(stax_db)
    res = stax_db.search_elements_advanced({"types": ["2D"], "rating_min": 3})
    assert [r["name"] for r in res] == ["plate_a"]


@pytest.mark.unit
def test_tag_include_and_exclude(stax_db):
    _seed(stax_db)
    res = stax_db.search_elements_advanced({"tags_any": ["fire"], "tags_exclude": ["city"]})
    assert [r["name"] for r in res] == ["geo_c"]


@pytest.mark.unit
def test_text_matches_name_or_tags(stax_db):
    _seed(stax_db)
    res = stax_db.search_elements_advanced({"text": "plate"})
    assert {r["name"] for r in res} == {"plate_a", "plate_b"}


@pytest.mark.unit
def test_count_matches_result_length(stax_db):
    _seed(stax_db)
    spec = {"types": ["2D"]}
    assert stax_db.count_elements_advanced(spec) == len(stax_db.search_elements_advanced(spec))
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_query_builder.py -v`
Expected: FAIL — `search_elements_advanced` not defined.

- [ ] **Step 3: Implement the builder**

Add to `DatabaseManager` (import `normalize` at top: `from filter_spec import normalize`):

```python
    # Tag boundary match: normalize ", " to "," then wrap and LIKE %,tag,%
    _TAG_MATCH = "(',' || REPLACE(IFNULL(tags,''), ', ', ',') || ',') LIKE '%,' || ? || ',%'"

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
            params.append(tag)
        if s["tags_any"]:
            ors = " OR ".join(DatabaseManager._TAG_MATCH for _ in s["tags_any"])
            clauses.append("(" + ors + ")")
            params += s["tags_any"]
        for tag in s["tags_exclude"]:
            clauses.append("NOT " + DatabaseManager._TAG_MATCH)
            params.append(tag)

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
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_query_builder.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep2_query_builder.py
git commit -m "feat(ep2): add FilterSpec-driven query builder and count"
```

---

## Task 3: `get_facet_counts`

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep2_facet_counts.py`

**Interfaces:**
- Produces: `get_facet_counts(filter_spec) -> dict` with keys `type`, `format`, `rating`, `label`, `status` (each a `{value: count}` dict) and `tag` (a `{tag: count}` dict). Each facet is counted against the other active filters (i.e. excluding its own clause).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_facet_counts.py`:

```python
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for name, typ, fmt in [("a","2D",".exr"), ("b","2D",".mov"), ("c","3D",".abc")]:
            conn.execute("INSERT INTO elements (list_fk,name,type,format) VALUES (1,?,?,?)",
                         (name, typ, fmt))


@pytest.mark.unit
def test_type_facet_counts(stax_db):
    _seed(stax_db)
    counts = stax_db.get_facet_counts({})
    assert counts["type"]["2D"] == 2
    assert counts["type"]["3D"] == 1


@pytest.mark.unit
def test_format_facet_respects_other_filters(stax_db):
    _seed(stax_db)
    counts = stax_db.get_facet_counts({"types": ["2D"]})
    assert counts["format"].get(".exr") == 1
    assert counts["format"].get(".mov") == 1
    assert ".abc" not in counts["format"]
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_facet_counts.py -v`
Expected: FAIL — `get_facet_counts` not defined.

- [ ] **Step 3: Implement**

Add to `DatabaseManager`:

```python
    def _facet_count_query(self, filter_spec, drop_key, group_col):
        """Count rows grouped by group_col, applying the filter minus drop_key."""
        from filter_spec import normalize
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
        # status: deprecated / hard-copy tallies against the full active filter
        where, params = self._build_filter_where(filter_spec)
        with self.get_connection(write=False) as conn:
            dep = conn.execute(
                "SELECT is_deprecated, COUNT(*) FROM elements WHERE {} GROUP BY is_deprecated".format(where),
                params).fetchall()
            counts["status"] = {("deprecated" if k else "active"): v for k, v in dep}
        # tag facet: parse comma-joined tags of the filtered set
        rows = self.search_elements_advanced(filter_spec)
        tag_counts = {}
        for r in rows:
            for t in [x.strip() for x in (r.get("tags") or "").split(",") if x.strip()]:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        counts["tag"] = tag_counts
        return counts
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_facet_counts.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep2_facet_counts.py
git commit -m "feat(ep2): add get_facet_counts with sibling-aware counting"
```

---

## Task 4: `FacetDrawer` widget

**Files:**
- Create: `src/ui/facet_drawer.py`
- Test: `tests/gui/test_ep2_facet_drawer.py`

**Interfaces:**
- Consumes: facet counts dict from `get_facet_counts`.
- Produces: `FacetDrawer(parent=None)` with `set_facets(counts: dict)`, `current_filter() -> dict` (a FilterSpec fragment), and signal `filter_changed(dict)`. Each value row is tri-state: neutral / include / exclude.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep2_facet_drawer.py`:

```python
import pytest
from ui.facet_drawer import FacetDrawer


@pytest.mark.gui
def test_include_type_emits_filter(qtbot):
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {"2D": 2, "3D": 1}, "format": {}, "tag": {},
                       "rating": {}, "label": {}, "status": {}})
    with qtbot.waitSignal(drawer.filter_changed, timeout=1000):
        drawer.set_value_state("type", "2D", "include")
    assert drawer.current_filter()["types"] == ["2D"]


@pytest.mark.gui
def test_exclude_tag_populates_exclude_list(qtbot):
    drawer = FacetDrawer()
    qtbot.addWidget(drawer)
    drawer.set_facets({"type": {}, "format": {}, "tag": {"city": 3},
                       "rating": {}, "label": {}, "status": {}})
    drawer.set_value_state("tag", "city", "exclude")
    assert drawer.current_filter()["tags_exclude"] == ["city"]
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep2_facet_drawer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/facet_drawer.py`:

```python
# -*- coding: utf-8 -*-
"""Collapsible faceted filter drawer (EP2)."""

from PySide2 import QtWidgets, QtCore

# facet key -> (include list-key, exclude list-key or None)
_FACET_KEYS = {
    "type":   ("types", None),
    "format": ("formats", "formats_exclude"),
    "tag":    ("tags_any", "tags_exclude"),
    "rating": ("rating_min", None),
    "label":  ("label_fks", None),
    "status": ("status", None),
}


class FacetDrawer(QtWidgets.QWidget):
    filter_changed = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super(FacetDrawer, self).__init__(parent)
        self._state = {}   # (facet, value) -> 'include' | 'exclude'
        self._layout = QtWidgets.QVBoxLayout(self)
        self._groups = {}

    def set_facets(self, counts):
        # rebuild group boxes from counts
        for i in reversed(range(self._layout.count())):
            w = self._layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._groups = {}
        for facet in ("type", "format", "tag", "rating", "label", "status"):
            values = counts.get(facet, {})
            if not values and facet not in ("type", "format"):
                continue
            box = QtWidgets.QGroupBox(facet.capitalize())
            box.setCheckable(True)
            box.setChecked(False)
            vbox = QtWidgets.QVBoxLayout(box)
            for value, count in sorted(values.items(), key=lambda kv: str(kv[0])):
                vbox.addWidget(self._make_row(facet, value, count))
            self._layout.addWidget(box)
            self._groups[facet] = box

    def _make_row(self, facet, value, count):
        row = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        cb = QtWidgets.QCheckBox("{} ({})".format(value, count))
        cb.setTristate(True)
        cb.stateChanged.connect(
            lambda st, f=facet, v=value: self._on_state(f, v, st))
        h.addWidget(cb)
        return row

    def _on_state(self, facet, value, qt_state):
        mapping = {0: None, 1: "exclude", 2: "include"}  # unchecked/partial/checked
        state = mapping.get(qt_state)
        key = (facet, str(value))
        if state is None:
            self._state.pop(key, None)
        else:
            self._state[key] = state
        self.filter_changed.emit(self.current_filter())

    def set_value_state(self, facet, value, state):
        """Programmatic setter used by tests and chip removal."""
        key = (facet, str(value))
        if state is None:
            self._state.pop(key, None)
        else:
            self._state[key] = state
        self.filter_changed.emit(self.current_filter())

    def current_filter(self):
        from filter_spec import empty_filter
        spec = empty_filter()
        for (facet, value), state in self._state.items():
            inc_key, exc_key = _FACET_KEYS[facet]
            if facet == "rating":
                if state == "include":
                    spec["rating_min"] = int(value)
                continue
            if facet == "status":
                if value == "deprecated":
                    spec["is_deprecated"] = (state == "include")
                continue
            target = inc_key if state == "include" else (exc_key or inc_key)
            if state == "exclude" and exc_key is None:
                continue
            coerced = int(value) if facet == "label" else value
            spec[target].append(coerced)
        return spec
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep2_facet_drawer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/facet_drawer.py tests/gui/test_ep2_facet_drawer.py
git commit -m "feat(ep2): add tri-state FacetDrawer widget"
```

---

## Task 5: `FilterChipBar` widget

**Files:**
- Create: `src/ui/filter_chip_bar.py`
- Test: `tests/gui/test_ep2_chip_bar.py`

**Interfaces:**
- Produces: `FilterChipBar(parent=None)` with `set_filter(spec, result_count)`, signals `chip_removed(str, object)` (facet-key, value) and `cleared()`; renders one chip per active clause + an "N results" label + "Clear all".

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep2_chip_bar.py`:

```python
import pytest
from ui.filter_chip_bar import FilterChipBar


@pytest.mark.gui
def test_renders_chip_per_clause_and_count(qtbot):
    bar = FilterChipBar()
    qtbot.addWidget(bar)
    bar.set_filter({"types": ["2D"], "tags_any": ["fire"]}, result_count=7)
    assert bar.chip_count() == 2
    assert "7" in bar.count_label.text()


@pytest.mark.gui
def test_clear_all_emits(qtbot):
    bar = FilterChipBar()
    qtbot.addWidget(bar)
    bar.set_filter({"types": ["2D"]}, result_count=1)
    with qtbot.waitSignal(bar.cleared, timeout=1000):
        bar.clear_button.click()
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep2_chip_bar.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/filter_chip_bar.py`:

```python
# -*- coding: utf-8 -*-
"""Removable active-filter chips + result count (EP2)."""

from PySide2 import QtWidgets, QtCore

# clause list-keys rendered as chips: (spec_key, label_prefix)
_CHIP_LISTS = [
    ("types", "type"), ("formats", "format"), ("formats_exclude", "not format"),
    ("tags_any", "tag"), ("tags_all", "tag"), ("tags_exclude", "not tag"),
    ("label_fks", "label"),
]


class FilterChipBar(QtWidgets.QWidget):
    chip_removed = QtCore.Signal(str, object)
    cleared = QtCore.Signal()

    def __init__(self, parent=None):
        super(FilterChipBar, self).__init__(parent)
        self._row = QtWidgets.QHBoxLayout(self)
        self._row.setContentsMargins(6, 2, 6, 2)
        self.count_label = QtWidgets.QLabel("0 results")
        self.clear_button = QtWidgets.QPushButton("Clear all")
        self.clear_button.clicked.connect(self.cleared.emit)
        self._chips = []

    def chip_count(self):
        return len(self._chips)

    def set_filter(self, spec, result_count):
        for i in reversed(range(self._row.count())):
            w = self._row.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._chips = []

        for key, prefix in _CHIP_LISTS:
            for value in (spec.get(key) or []):
                self._add_chip(key, value, "{}: {}".format(prefix, value))
        if spec.get("text"):
            self._add_chip("text", spec["text"], "text: {}".format(spec["text"]))
        if spec.get("rating_min"):
            self._add_chip("rating_min", spec["rating_min"], "rating ≥ {}".format(spec["rating_min"]))
        if spec.get("is_deprecated") is not None:
            self._add_chip("is_deprecated", spec["is_deprecated"],
                           "deprecated" if spec["is_deprecated"] else "active")

        self._row.addStretch(1)
        self.count_label.setText("{} results".format(result_count))
        self._row.addWidget(self.count_label)
        self._row.addWidget(self.clear_button)

    def _add_chip(self, key, value, text):
        btn = QtWidgets.QPushButton("{}  ✕".format(text))
        btn.clicked.connect(lambda: self.chip_removed.emit(key, value))
        self._row.addWidget(btn)
        self._chips.append(btn)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep2_chip_bar.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/filter_chip_bar.py tests/gui/test_ep2_chip_bar.py
git commit -m "feat(ep2): add FilterChipBar with removable chips + result count"
```

---

## Task 6: Wire drawer + chips into MediaDisplayWidget

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep2_media_filter.py`

**Interfaces:**
- Consumes: `FacetDrawer`, `FilterChipBar`, `search_elements_advanced`, `count_elements_advanced`, `get_facet_counts`.
- Produces: `apply_filter(self, filter_spec)` (runs the query, updates chips + drawer counts + result count, repaints); `self.facet_drawer`, `self.chip_bar`, `self.current_filter`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep2_media_filter.py`:

```python
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'b','3D')")


@pytest.mark.gui
def test_apply_filter_updates_count(qtbot, stax_db):
    _seed(stax_db)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w.apply_filter({"types": ["2D"]})
    assert "1 results" in w.chip_bar.count_label.text()
    assert w.current_filter["types"] == ["2D"]
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep2_media_filter.py -v`
Expected: FAIL — `apply_filter` / `chip_bar` missing.

- [ ] **Step 3: Implement**

In `MediaDisplayWidget.__init__` (after the views are built) add:

```python
        from ui.facet_drawer import FacetDrawer
        from ui.filter_chip_bar import FilterChipBar
        from filter_spec import empty_filter
        self.current_filter = empty_filter()
        self.facet_drawer = FacetDrawer()
        self.chip_bar = FilterChipBar()
        # place chip bar above the views, drawer to their left (use existing layout)
        self._install_filter_widgets(self.facet_drawer, self.chip_bar)
        self.facet_drawer.filter_changed.connect(self.apply_filter)
        self.chip_bar.chip_removed.connect(self._on_chip_removed)
        self.chip_bar.cleared.connect(lambda: self.apply_filter(empty_filter()))
```

Add the methods:

```python
    def apply_filter(self, filter_spec):
        from filter_spec import normalize
        self.current_filter = normalize(filter_spec)
        rows = self.db.search_elements_advanced(self.current_filter)
        count = len(rows)
        self.chip_bar.set_filter(self.current_filter, count)
        try:
            self.facet_drawer.set_facets(self.db.get_facet_counts(self.current_filter))
        except Exception:
            logger.exception("facet count refresh failed")
        self._render_elements(rows)   # existing per-view render entry point

    def _on_chip_removed(self, key, value):
        spec = dict(self.current_filter)
        if isinstance(spec.get(key), list):
            spec[key] = [v for v in spec[key] if v != value]
        elif key == "rating_min":
            spec[key] = 0
        elif key == "text":
            spec[key] = ""
        else:
            spec[key] = None
        self.apply_filter(spec)
```

Provide `_install_filter_widgets(drawer, chip_bar)` that adds the chip bar above the stacked views and the drawer as a collapsible left column of the media panel; and `_render_elements(rows)` that reuses the existing element-render path (the same one `_update_views_with_elements` uses) — if that method takes a list already, call it directly.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep2_media_filter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep2_media_filter.py
git commit -m "feat(ep2): wire facet drawer + chip bar into media view"
```

---

# Cluster 2B — Persistence

## Task 7: Saved searches (personal)

**Files:**
- Modify: `src/db_manager.py` (schema + migration + CRUD)
- Test: `tests/unit/test_ep2_saved_searches.py`

**Interfaces:**
- Produces table `saved_searches` and: `create_saved_search(name, filter_spec, user_name, machine_name=None) -> int`, `get_saved_searches(user_name) -> list[dict]` (each has parsed `filter` dict), `delete_saved_search(saved_search_id)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_saved_searches.py`:

```python
import pytest


@pytest.mark.unit
def test_create_and_scope_by_user(stax_db):
    sid = stax_db.create_saved_search("Fire 2D", {"types": ["2D"], "tags_any": ["fire"]}, "alice")
    stax_db.create_saved_search("Bob only", {"types": ["3D"]}, "bob")
    alice = stax_db.get_saved_searches("alice")
    assert [s["name"] for s in alice] == ["Fire 2D"]
    assert alice[0]["filter"]["types"] == ["2D"]
    assert alice[0]["saved_search_id"] == sid


@pytest.mark.unit
def test_delete(stax_db):
    sid = stax_db.create_saved_search("X", {"text": "a"}, "alice")
    stax_db.delete_saved_search(sid)
    assert stax_db.get_saved_searches("alice") == []
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_saved_searches.py -v`
Expected: FAIL — methods/table missing.

- [ ] **Step 3: Implement schema + migration + CRUD**

Add the table to `_create_schema` and the idempotent `_apply_migrations` block (following EP1 Task 1's pattern):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_searches (
                saved_search_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name    TEXT NOT NULL,
                machine_name TEXT,
                name         TEXT NOT NULL,
                filter_json  TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

Add methods (import `json` at top of the module if not present):

```python
    def create_saved_search(self, name, filter_spec, user_name, machine_name=None):
        import json
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO saved_searches (user_name, machine_name, name, filter_json) "
                "VALUES (?, ?, ?, ?)",
                (user_name, machine_name, name, json.dumps(filter_spec)),
            )
            return cur.lastrowid

    def get_saved_searches(self, user_name):
        import json
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
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM saved_searches WHERE saved_search_id = ?", (saved_search_id,))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_saved_searches.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep2_saved_searches.py
git commit -m "feat(ep2): add personal saved-searches table and CRUD"
```

---

## Task 8: Smart collections (shared)

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep2_smart_collections.py`

**Interfaces:**
- Produces table `smart_collections` and: `create_smart_collection(name, filter_spec, created_by=None, sort_order=0) -> int`, `get_smart_collections() -> list[dict]` (parsed `filter`), `update_smart_collection(collection_id, **fields)`, `delete_smart_collection(collection_id)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_smart_collections.py`:

```python
import pytest


@pytest.mark.unit
def test_create_list_shared(stax_db):
    cid = stax_db.create_smart_collection("Un-reviewed plates",
                                          {"types": ["2D"], "rating_min": 0}, created_by="alice")
    cols = stax_db.get_smart_collections()
    assert cols[0]["name"] == "Un-reviewed plates"
    assert cols[0]["filter"]["types"] == ["2D"]
    assert cols[0]["collection_id"] == cid


@pytest.mark.unit
def test_update_and_delete(stax_db):
    cid = stax_db.create_smart_collection("A", {"text": "x"})
    stax_db.update_smart_collection(cid, name="B")
    assert stax_db.get_smart_collections()[0]["name"] == "B"
    stax_db.delete_smart_collection(cid)
    assert stax_db.get_smart_collections() == []
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_smart_collections.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement schema + CRUD**

Add table (to `_create_schema` + migration block):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS smart_collections (
                collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                filter_json TEXT NOT NULL,
                created_by  TEXT,
                sort_order  INTEGER NOT NULL DEFAULT 0
            )
        """)
```

Methods:

```python
    _COLLECTION_FIELDS = {"name", "filter_json", "created_by", "sort_order"}

    def create_smart_collection(self, name, filter_spec, created_by=None, sort_order=0):
        import json
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO smart_collections (name, filter_json, created_by, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (name, json.dumps(filter_spec), created_by, sort_order))
            return cur.lastrowid

    def get_smart_collections(self):
        import json
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
        import json
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
        with self.get_connection(write=True) as conn:
            conn.cursor().execute(
                "DELETE FROM smart_collections WHERE collection_id = ?", (collection_id,))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_smart_collections.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep2_smart_collections.py
git commit -m "feat(ep2): add shared smart-collections table and CRUD"
```

---

## Task 9: Nav integration — saved searches + smart collections

**Files:**
- Modify: `src/ui/stacks_lists_panel.py`
- Test: `tests/gui/test_ep2_nav.py`

**Interfaces:**
- Consumes: `get_saved_searches(user_name)`, `get_smart_collections()`.
- Produces: a "Saved Searches" list and a "Smart Collections" list in `StacksListsPanel`; signal `filter_selected(dict)` emitted with the chosen `FilterSpec`; `refresh_saved_searches()` / `refresh_smart_collections()`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep2_nav.py`:

```python
import pytest


class _FakeMain:
    def check_admin_permission(self): return True


@pytest.mark.gui
def test_selecting_saved_search_emits_filter(qtbot, stax_db):
    stax_db.create_saved_search("Fire", {"tags_any": ["fire"]}, "alice")
    from ui.stacks_lists_panel import StacksListsPanel
    panel = StacksListsPanel(stax_db, main_window=_FakeMain(), user_name="alice")
    qtbot.addWidget(panel)
    panel.refresh_saved_searches()
    with qtbot.waitSignal(panel.filter_selected, timeout=1000):
        panel.saved_searches_list.setCurrentRow(0)
        panel._on_saved_search_activated(panel.saved_searches_list.item(0))
```

> Match `StacksListsPanel.__init__`'s real signature; thread `user_name` from the current session if the panel does not already have it.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep2_nav.py -v`
Expected: FAIL — `saved_searches_list` / `filter_selected` missing.

- [ ] **Step 3: Implement**

Add to `StacksListsPanel` a `filter_selected = QtCore.Signal(dict)` and, in `setup_ui`, two labelled `QListWidget`s below the existing Tags section:

```python
        # Saved Searches (personal)
        self.saved_searches_list = QtWidgets.QListWidget()
        self.saved_searches_list.itemActivated.connect(self._on_saved_search_activated)
        layout.addWidget(QtWidgets.QLabel("Saved Searches"))
        layout.addWidget(self.saved_searches_list)

        # Smart Collections (shared)
        self.smart_collections_list = QtWidgets.QListWidget()
        self.smart_collections_list.itemActivated.connect(self._on_smart_collection_activated)
        layout.addWidget(QtWidgets.QLabel("Smart Collections"))
        layout.addWidget(self.smart_collections_list)

        self.refresh_saved_searches()
        self.refresh_smart_collections()
```

Add methods:

```python
    from PySide2 import QtCore  # ensure imported at module top

    def refresh_saved_searches(self):
        from PySide2 import QtWidgets, QtCore
        self.saved_searches_list.clear()
        for s in self.db.get_saved_searches(self.user_name):
            item = QtWidgets.QListWidgetItem(s["name"])
            item.setData(QtCore.Qt.UserRole, s["filter"])
            self.saved_searches_list.addItem(item)

    def refresh_smart_collections(self):
        from PySide2 import QtWidgets, QtCore
        self.smart_collections_list.clear()
        for c in self.db.get_smart_collections():
            item = QtWidgets.QListWidgetItem(c["name"])
            item.setData(QtCore.Qt.UserRole, c["filter"])
            self.smart_collections_list.addItem(item)

    def _on_saved_search_activated(self, item):
        from PySide2 import QtCore
        self.filter_selected.emit(item.data(QtCore.Qt.UserRole))

    def _on_smart_collection_activated(self, item):
        from PySide2 import QtCore
        self.filter_selected.emit(item.data(QtCore.Qt.UserRole))
```

Wire `panel.filter_selected` to `media_display.apply_filter` in `main.py` where the panel's other signals are connected. Add a "Save current search…" control (a small button near the search box in `MediaDisplayWidget`) that calls `db.create_saved_search(name, self.current_filter, user_name)` then `panel.refresh_saved_searches()`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep2_nav.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/stacks_lists_panel.py main.py tests/gui/test_ep2_nav.py
git commit -m "feat(ep2): add saved-search + smart-collection nav sections"
```

---

# Cluster 2C — Text quality (trimmable)

## Task 10: Synonyms

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep2_synonyms.py`

**Interfaces:**
- Produces table `search_synonyms(synonym_id, term, group_key)` and: `add_synonym(term, group_key)`, `get_synonyms() -> list[dict]`, `delete_synonym(synonym_id)`, `expand_terms(text) -> list[str]` (the input words plus any group siblings).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_synonyms.py`:

```python
import pytest


@pytest.mark.unit
def test_expand_terms_includes_group_siblings(stax_db):
    stax_db.add_synonym("fire", "g1")
    stax_db.add_synonym("flame", "g1")
    stax_db.add_synonym("blaze", "g1")
    expanded = set(stax_db.expand_terms("fire"))
    assert {"fire", "flame", "blaze"}.issubset(expanded)


@pytest.mark.unit
def test_expand_terms_passthrough_when_no_group(stax_db):
    assert stax_db.expand_terms("waterfall") == ["waterfall"]
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_synonyms.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add table (to `_create_schema` + migration):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_synonyms (
                synonym_id INTEGER PRIMARY KEY AUTOINCREMENT,
                term       TEXT NOT NULL,
                group_key  TEXT NOT NULL
            )
        """)
```

Methods:

```python
    def add_synonym(self, term, group_key):
        with self.get_connection(write=True) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO search_synonyms (term, group_key) VALUES (?, ?)",
                        (term.strip().lower(), group_key))
            return cur.lastrowid

    def get_synonyms(self):
        with self.get_connection(write=False) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM search_synonyms ORDER BY group_key, term").fetchall()]

    def delete_synonym(self, synonym_id):
        with self.get_connection(write=True) as conn:
            conn.cursor().execute("DELETE FROM search_synonyms WHERE synonym_id = ?", (synonym_id,))

    def expand_terms(self, text):
        """Expand each whitespace token to its synonym group's members."""
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
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_synonyms.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep2_synonyms.py
git commit -m "feat(ep2): add synonym table and expand_terms"
```

---

## Task 11: Fuzzy suggestion + recent searches

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep2_fuzzy_recent.py`

**Interfaces:**
- Produces: `suggest_correction(query) -> str|None` (difflib over tag + name vocabulary), table `recent_searches(recent_id, user_name, query_text, ran_at)` capped per user, `add_recent_search(user_name, query_text, cap=20)`, `get_recent_searches(user_name) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep2_fuzzy_recent.py`:

```python
import pytest


def _seed_tags(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'x','2D','fire,explosion')")


@pytest.mark.unit
def test_suggest_correction_finds_near_tag(stax_db):
    _seed_tags(stax_db)
    assert stax_db.suggest_correction("frie") == "fire"
    assert stax_db.suggest_correction("zzzzzz") is None


@pytest.mark.unit
def test_recent_searches_capped_and_ordered(stax_db):
    for i in range(25):
        stax_db.add_recent_search("alice", "q{}".format(i), cap=20)
    recent = stax_db.get_recent_searches("alice")
    assert len(recent) == 20
    assert recent[0] == "q24"   # most recent first
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep2_fuzzy_recent.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add table (to `_create_schema` + migration):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_searches (
                recent_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name  TEXT NOT NULL,
                query_text TEXT NOT NULL,
                ran_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

Methods:

```python
    def suggest_correction(self, query):
        """Return the closest tag/name term to `query`, or None."""
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
        with self.get_connection(write=False) as conn:
            return [r[0] for r in conn.execute(
                "SELECT query_text FROM recent_searches WHERE user_name = ? "
                "ORDER BY recent_id DESC", (user_name,)).fetchall()]
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep2_fuzzy_recent.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep2_fuzzy_recent.py
git commit -m "feat(ep2): add difflib suggestion + capped recent searches"
```

---

## Task 12: Wire "did you mean" + recent into the search box

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep2_search_help.py`

**Interfaces:**
- Consumes: `suggest_correction`, `add_recent_search`, `get_recent_searches`, `expand_terms`.
- Produces: on search, text is expanded via `expand_terms` into `tags_any`; a `did_you_mean_label` shows `suggest_correction` output when results are 0; recent queries feed a `QCompleter` on the search box.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep2_search_help.py`:

```python
import pytest


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'x','2D','fire')")


@pytest.mark.gui
def test_did_you_mean_appears_on_typo(qtbot, stax_db):
    _seed(stax_db)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w.run_text_search("frie")   # no exact hits -> suggestion
    assert "fire" in w.did_you_mean_label.text().lower()
    assert w.did_you_mean_label.isVisible()


@pytest.mark.gui
def test_no_suggestion_when_results_found(qtbot, stax_db):
    _seed(stax_db)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w.run_text_search("fire")
    assert not w.did_you_mean_label.isVisible()
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep2_search_help.py -v`
Expected: FAIL — `run_text_search` / `did_you_mean_label` missing.

- [ ] **Step 3: Implement**

Add a `did_you_mean_label` (a hidden `QLabel`) beneath the search box in `MediaDisplayWidget.__init__`, and:

```python
    def run_text_search(self, text):
        from filter_spec import empty_filter
        spec = empty_filter()
        spec["text"] = text
        # synonym-expand into tags_any as an OR assist
        try:
            spec["tags_any"] = self.db.expand_terms(text)
        except Exception:
            logger.exception("term expansion failed")
        self.apply_filter(spec)
        count = self.db.count_elements_advanced(spec)
        if count == 0:
            suggestion = self.db.suggest_correction(text)
            if suggestion:
                self.did_you_mean_label.setText("Did you mean <b>{}</b>?".format(suggestion))
                self.did_you_mean_label.setVisible(True)
                return
        self.did_you_mean_label.setVisible(False)

    def _install_recent_completer(self, user_name):
        from PySide2 import QtWidgets
        recents = self.db.get_recent_searches(user_name)
        completer = QtWidgets.QCompleter(recents, self.search_box)
        completer.setCaseSensitivity(0)
        self.search_box.setCompleter(completer)
```

Change the existing `on_search` (line 546) so that, for a plain-text query (no `#tag`/`tag:` prefix), it calls `self.run_text_search(text)` and records `self.db.add_recent_search(user_name, text)`; keep the existing `#tag`/`tag:` fast paths.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep2_search_help.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full EP2 suite**

Run: `pytest -m "not manual" -k ep2 -v`
Expected: all EP2 unit + gui tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep2_search_help.py
git commit -m "feat(ep2): wire did-you-mean + synonym expansion + recent completer"
```

---

## Task 13: Settings — Search management tab (admin)

**Files:**
- Modify: `src/ui/settings_panel.py`
- Test: `tests/gui/test_ep2_search_settings.py`

**Interfaces:**
- Consumes: `get_synonyms`, `add_synonym`, `delete_synonym`, `get_smart_collections`, `delete_smart_collection`; `main_window.check_admin_permission`.
- Produces: `_build_search_tab(self) -> QWidget` added via `self.tab_widget.addTab(tab, "Search")`; a `synonyms_table` and `collections_table`; add/delete controls disabled for non-admins.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep2_search_settings.py`:

```python
import pytest


class _Main:
    def __init__(self, admin): self._a = admin
    def check_admin_permission(self): return self._a


@pytest.mark.gui
def test_search_tab_lists_synonyms_and_gates_admin(qtbot, stax_db):
    stax_db.add_synonym("fire", "g1")
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config=None, main_window=_Main(admin=False))
    qtbot.addWidget(panel)
    assert panel.synonyms_table.rowCount() == 1
    assert panel.add_synonym_button.isEnabled() is False


@pytest.mark.gui
def test_admin_add_synonym(qtbot, stax_db):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config=None, main_window=_Main(admin=True))
    qtbot.addWidget(panel)
    panel._add_synonym_row("flame", "g1")
    assert any(s["term"] == "flame" for s in stax_db.get_synonyms())
```

> Match `SettingsPanel.__init__`'s real signature (same `main_window` source EP1's Labels tab uses).

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep2_search_settings.py -v`
Expected: FAIL — `synonyms_table` / `_build_search_tab` missing.

- [ ] **Step 3: Implement the tab**

In `SettingsPanel.setup_ui`, after the other `addTab` calls, add:

```python
        self.tab_widget.addTab(self._build_search_tab(), "Search")
```

Add the builder + helpers:

```python
    def _build_search_tab(self):
        from PySide2 import QtWidgets
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        is_admin = bool(self.main_window.check_admin_permission()) if self.main_window else False

        layout.addWidget(QtWidgets.QLabel("Synonyms (term → group)"))
        self.synonyms_table = QtWidgets.QTableWidget(0, 2)
        self.synonyms_table.setHorizontalHeaderLabels(["Term", "Group"])
        layout.addWidget(self.synonyms_table)
        syn_row = QtWidgets.QHBoxLayout()
        self.add_synonym_button = QtWidgets.QPushButton("Add…")
        self.delete_synonym_button = QtWidgets.QPushButton("Delete")
        syn_row.addWidget(self.add_synonym_button)
        syn_row.addWidget(self.delete_synonym_button)
        layout.addLayout(syn_row)

        layout.addWidget(QtWidgets.QLabel("Smart Collections"))
        self.collections_table = QtWidgets.QTableWidget(0, 1)
        self.collections_table.setHorizontalHeaderLabels(["Name"])
        layout.addWidget(self.collections_table)
        self.delete_collection_button = QtWidgets.QPushButton("Delete collection")
        layout.addWidget(self.delete_collection_button)

        self.add_synonym_button.clicked.connect(self._on_add_synonym)
        self.delete_synonym_button.clicked.connect(self._on_delete_synonym)
        self.delete_collection_button.clicked.connect(self._on_delete_collection)
        for b in (self.add_synonym_button, self.delete_synonym_button, self.delete_collection_button):
            b.setEnabled(is_admin)

        self._reload_synonyms()
        self._reload_collections()
        return tab

    def _reload_synonyms(self):
        from PySide2 import QtWidgets
        syns = self.db.get_synonyms()
        self.synonyms_table.setRowCount(len(syns))
        for row, s in enumerate(syns):
            self.synonyms_table.setItem(row, 0, QtWidgets.QTableWidgetItem(s["term"]))
            self.synonyms_table.setItem(row, 1, QtWidgets.QTableWidgetItem(s["group_key"]))

    def _reload_collections(self):
        from PySide2 import QtWidgets
        cols = self.db.get_smart_collections()
        self.collections_table.setRowCount(len(cols))
        for row, c in enumerate(cols):
            self.collections_table.setItem(row, 0, QtWidgets.QTableWidgetItem(c["name"]))

    def _add_synonym_row(self, term, group_key):
        self.db.add_synonym(term, group_key)
        self._reload_synonyms()
        self.settings_changed.emit()

    def _on_add_synonym(self):
        from PySide2 import QtWidgets
        term, ok = QtWidgets.QInputDialog.getText(self, "New synonym", "Term:")
        if not ok or not term:
            return
        group, ok2 = QtWidgets.QInputDialog.getText(self, "New synonym", "Group key:")
        if not ok2 or not group:
            return
        self._add_synonym_row(term, group)

    def _on_delete_synonym(self):
        row = self.synonyms_table.currentRow()
        if row < 0:
            return
        syns = self.db.get_synonyms()
        if row < len(syns):
            self.db.delete_synonym(syns[row]["synonym_id"])
            self._reload_synonyms()

    def _on_delete_collection(self):
        row = self.collections_table.currentRow()
        if row < 0:
            return
        cols = self.db.get_smart_collections()
        if row < len(cols):
            self.db.delete_smart_collection(cols[row]["collection_id"])
            self._reload_collections()
            self.settings_changed.emit()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep2_search_settings.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/settings_panel.py tests/gui/test_ep2_search_settings.py
git commit -m "feat(ep2): add admin Search settings tab (synonyms + smart collections)"
```

---

## Self-Review

**1. Spec coverage:**
- FilterSpec model → Task 1 ✓
- Query builder + count → Task 2 ✓; facet counts → Task 3 ✓
- FacetDrawer (incl. negative-filter exclude states, F010) → Task 4 ✓
- FilterChipBar + result count → Task 5 ✓; wired + apply_filter → Task 6 ✓
- Saved searches (F007, personal) → Task 7 + nav Task 9 ✓
- Smart collections (F008, shared) → Task 8 + nav Task 9 ✓
- Synonyms (F009) → Task 10, applied in Task 12 ✓
- Fuzzy/typo (F011) → Task 11, surfaced Task 12 ✓
- Query suggestions/recent (F012) → Task 11 + completer Task 12 ✓
- Tests unit + headless GUI → every task ✓
- Admin management of synonyms/smart-collections (spec §3.5/§3.6, §4) → Task 13 (admin-gated Search settings tab) ✓

**2. Placeholder scan:** New units (FilterSpec, builder, facet counts, both widgets, all DB CRUD) have complete code. Integration tasks (6, 9, 12) give complete new-method code plus concrete wiring snippets anchored to verified methods (`on_search:546`, panel `setup_ui`), naming the exact reuse point (`_render_elements`, `apply_filter`) rather than leaving it open.

**3. Type consistency:** `search_elements_advanced`/`count_elements_advanced`/`get_facet_counts` (Tasks 2–3) are consumed with identical names in Task 6. `FacetDrawer.set_facets`/`current_filter`/`set_value_state`/`filter_changed` match Tasks 4 & 6. `FilterChipBar.set_filter`/`chip_removed`/`cleared` match Tasks 5 & 6. `FilterSpec` keys (`types`, `formats`, `tags_any`, `tags_exclude`, `rating_min`, `label_fks`, `is_deprecated`, `is_hard_copy`, `list_fk`, `stack_fk`) are identical across Tasks 1, 2, 4, 5, 6. `get_saved_searches`/`get_smart_collections` return dicts with a parsed `filter` key, consumed as such in Task 9. `expand_terms`/`suggest_correction`/`add_recent_search`/`get_recent_searches` match Tasks 10–12.

**Note for the executor:** EP2 assumes EP1 + SP1 have landed. If running before SP1, drop the `write=` kwarg. The Task 6/9/12 wiring reuses existing render/selection/search entry points — read `media_display_widget.py` and `stacks_lists_panel.py` for the exact local names before editing, and adjust the reuse calls (`_render_elements`, `on_search`) to the real method names. Never weaken a test to pass; mark `xfail(strict)` with the dependency id if a seam is genuinely absent.
