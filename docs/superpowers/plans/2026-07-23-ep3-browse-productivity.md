# EP3 — Browse Productivity Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a productivity shell over StaX's existing panes — a Ctrl+K command palette, spacebar quicklook, keyboard help overlay, a persistent editable inspector, skeleton loading + scroll retention, layout presets, accessibility controls, an onboarding checklist, and a minimal start page.

**Architecture:** Each surface is a self-contained widget in its own file, wired into `MainWindow`/`MediaDisplayWidget` via shortcuts, event filters, and existing signals. The command palette harvests live `QAction`s (no duplicate command list). Shared metadata formatting is extracted from `MediaInfoPopup` once and reused by the inspector. All preferences persist in `Config` — no schema changes except one read helper.

**Tech Stack:** Python 3.9, PySide2 (headless offscreen), pytest / pytest-qt, stdlib `difflib`, `Config` (JSON).

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat. **Logging:** `logging`, not `print`. **Commits:** conventional.
- **No new database tables.** Layout preset, accessibility, and onboarding state persist in `Config` keys: `layout_preset`, `a11y_high_contrast`, `a11y_text_scale`, `a11y_focus_assist`, `onboarding_dismissed`. Only one new DB read method (`get_recent_elements`).
- **Command palette harvests live QActions** + a small registry — never a hand-maintained command list.
- **Inspector reuses extracted MediaInfoPopup formatting** (DRY).
- **Skeletons degrade safely:** if SP2's async worker is absent, skeletons never show (no regression) — they hook the existing `on_preview_ready` slot.
- **Dependency — EP1:** `set_element_rating` / `set_element_label` for inspector editing.
- **Dependency — SP1:** `get_connection(write=…)`; `get_top_inserted_elements` for the start page (degrade if absent). Before SP1, drop `write=`.
- **Dependency — SP2/SP6:** async preview signals; UI correctness fixes. Absence → skeletons no-op; other surfaces unaffected.

---

## Key facts (verified against the codebase)

- `MainWindow.setup_toolbar` (`main.py:283`) builds `self.toolbar`; `setup_menus` builds menus with `QAction.setShortcut("Ctrl+I")` etc. (`main.py:335+`).
- 3-pane `self.main_splitter` = `[stacks_panel, media_display, video_player_pane]` (`main.py:211-245`); right pane is `VideoPlayerWidget` (`main.py:237`), hidden until selection.
- Docks: history (bottom), settings (right), analytics (bottom) (`main.py:252-275`).
- `toggle_focus_mode` sets `main_splitter.setSizes([...])` (`main.py:434`).
- `Config.get(key, default)` / `Config.set(key, value)` (`src/config.py:169`).
- `MediaInfoPopup.show_element` renders metadata fields (`src/ui/media_info_popup.py:308`); size/format helpers live there.
- `db.get_favorites(...)`, `db.get_top_inserted_elements(n)` (SP1), `db.get_element_by_id` exist.
- SP0 fixtures: `stax_db`, headless Qt (`qtbot`), `mock_nuke`.

---

# Cluster 3A — Interaction core

## Task 1: Command harvesting + registry

**Files:**
- Create: `src/ui/command_palette.py` (harvest + registry portion)
- Test: `tests/unit/test_ep3_command_harvest.py`

**Interfaces:**
- Produces: `harvest_actions(menu_bar, toolbar) -> list[tuple[str, QAction]]`; `CommandRegistry` with `register(label, callable)` and `entries() -> list[tuple[str, callable]]`; `fuzzy_filter(query, labels) -> list[int]` (indices, best-first).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep3_command_harvest.py`:

```python
import pytest
from PySide2 import QtWidgets

from ui.command_palette import harvest_actions, CommandRegistry, fuzzy_filter


@pytest.mark.gui
def test_harvest_collects_leaf_actions(qtbot):
    bar = QtWidgets.QMenuBar()
    file_menu = bar.addMenu("File")
    a_ingest = file_menu.addAction("Ingest Files")
    file_menu.addSeparator()
    a_exit = file_menu.addAction("Exit")
    toolbar = QtWidgets.QToolBar()
    a_search = toolbar.addAction("Search")

    entries = harvest_actions(bar, toolbar)
    labels = [label for label, _ in entries]
    assert "Ingest Files" in labels and "Exit" in labels and "Search" in labels
    assert "File" not in labels  # submenu parents excluded


@pytest.mark.unit
def test_registry_and_fuzzy():
    reg = CommandRegistry()
    reg.register("Go to stack: Plates", lambda: None)
    assert reg.entries()[0][0] == "Go to stack: Plates"
    order = fuzzy_filter("exit", ["Ingest Files", "Exit", "Advanced Search"])
    assert order[0] == 1  # 'Exit' ranks first
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep3_command_harvest.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement harvest + registry + fuzzy**

Create `src/ui/command_palette.py` (this task adds the top-level helpers; the dialog is Task 2):

```python
# -*- coding: utf-8 -*-
"""Command palette: harvest live actions + a small extra-command registry (EP3)."""

import difflib


def harvest_actions(menu_bar, toolbar):
    """Collect leaf (label, QAction) pairs from a menu bar and toolbar."""
    entries = []
    seen = set()

    def walk(actions):
        for a in actions:
            if a.isSeparator() or not a.text():
                continue
            sub = a.menu()
            if sub is not None:
                walk(sub.actions())
            elif id(a) not in seen:
                seen.add(id(a))
                entries.append((a.text().replace("&", ""), a))

    if menu_bar is not None:
        walk(menu_bar.actions())
    if toolbar is not None:
        walk(toolbar.actions())
    return entries


class CommandRegistry(object):
    """Extra palette commands: (label, callable)."""

    def __init__(self):
        self._items = []

    def register(self, label, callback):
        self._items.append((label, callback))

    def clear(self):
        self._items = []

    def entries(self):
        return list(self._items)


def _subsequence(query, text):
    it = iter(text)
    return all(ch in it for ch in query)


def fuzzy_filter(query, labels):
    """Return indices of labels matching query, best match first."""
    q = (query or "").strip().lower()
    if not q:
        return list(range(len(labels)))
    scored = []
    for i, label in enumerate(labels):
        low = label.lower()
        if q in low:
            score = 100 - low.index(q)
        elif _subsequence(q, low):
            score = 50 * difflib.SequenceMatcher(None, q, low).ratio()
        else:
            continue
        scored.append((score, i))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [i for _, i in scored]
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep3_command_harvest.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/command_palette.py tests/unit/test_ep3_command_harvest.py
git commit -m "feat(ep3): add command harvesting, registry, and fuzzy filter"
```

---

## Task 2: `CommandPalette` dialog + Ctrl+K

**Files:**
- Modify: `src/ui/command_palette.py` (add the dialog), `main.py` (Ctrl+K shortcut)
- Test: `tests/gui/test_ep3_command_palette.py`

**Interfaces:**
- Consumes: `harvest_actions`, `CommandRegistry`, `fuzzy_filter`.
- Produces: `CommandPalette(entries, parent=None)` where `entries` is `list[(label, target)]` (`target` is a `QAction` or callable); `.run_current()` triggers the highlighted entry; `.filter_text(text)`; opened via `MainWindow.open_command_palette()`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep3_command_palette.py`:

```python
import pytest
from PySide2 import QtWidgets

from ui.command_palette import CommandPalette


@pytest.mark.gui
def test_filter_and_run(qtbot):
    fired = {"n": 0}
    entries = [
        ("Ingest Files", lambda: fired.__setitem__("n", fired["n"] + 1)),
        ("Exit", lambda: None),
    ]
    pal = CommandPalette(entries)
    qtbot.addWidget(pal)
    pal.filter_text("ingest")
    assert pal.results_list.count() == 1
    pal.results_list.setCurrentRow(0)
    pal.run_current()
    assert fired["n"] == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep3_command_palette.py -v`
Expected: FAIL — `CommandPalette` class missing.

- [ ] **Step 3: Implement the dialog**

Append to `src/ui/command_palette.py`:

```python
from PySide2 import QtWidgets, QtCore


class CommandPalette(QtWidgets.QDialog):
    def __init__(self, entries, parent=None):
        super(CommandPalette, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup)
        self._entries = list(entries)   # [(label, target)]
        layout = QtWidgets.QVBoxLayout(self)
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Type a command…")
        self.results_list = QtWidgets.QListWidget()
        layout.addWidget(self.search_box)
        layout.addWidget(self.results_list)
        self.search_box.textChanged.connect(self.filter_text)
        self.search_box.returnPressed.connect(self.run_current)
        self.results_list.itemActivated.connect(lambda _i: self.run_current())
        self.filter_text("")
        self.resize(480, 360)

    def filter_text(self, text):
        labels = [lbl for lbl, _ in self._entries]
        order = fuzzy_filter(text, labels)
        self.results_list.clear()
        self._visible = []
        for i in order:
            self.results_list.addItem(self._entries[i][0])
            self._visible.append(i)
        if self.results_list.count():
            self.results_list.setCurrentRow(0)

    def run_current(self):
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self._visible):
            return
        _, target = self._entries[self._visible[row]]
        self.close()
        if hasattr(target, "trigger"):
            target.trigger()
        else:
            target()
```

- [ ] **Step 4: Wire Ctrl+K into MainWindow**

In `main.py`, in `MainWindow.__init__` (after menus/toolbar exist), add:

```python
        from PySide2 import QtWidgets, QtGui
        self._palette_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+K"), self)
        self._palette_shortcut.activated.connect(self.open_command_palette)
```

Add the method:

```python
    def open_command_palette(self):
        from ui.command_palette import CommandPalette, harvest_actions, CommandRegistry
        entries = harvest_actions(self.menuBar(), self.toolbar)
        reg = CommandRegistry()
        for stack in self.db.get_all_stacks():
            reg.register("Go to stack: {}".format(stack["name"]),
                         lambda s=stack: self.stacks_panel.select_stack(s["stack_id"]))
        entries = entries + reg.entries()
        pal = CommandPalette(entries, self)
        pal.move(self.geometry().center() - pal.rect().center())
        pal.show()
        pal.search_box.setFocus()
```

(If `stacks_panel.select_stack` has a different name, use the panel's existing stack-selection method.)

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep3_command_palette.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ui/command_palette.py main.py tests/gui/test_ep3_command_palette.py
git commit -m "feat(ep3): add CommandPalette dialog and Ctrl+K launcher"
```

---

## Task 3: Spacebar quicklook overlay

**Files:**
- Create: `src/ui/quicklook_overlay.py`
- Modify: `src/ui/media_display_widget.py` (Space event filter)
- Test: `tests/gui/test_ep3_quicklook.py`

**Interfaces:**
- Produces: `QuickLookOverlay(parent=None)` with `show_element(element_dict, preview_path)`, signals `next_requested()` / `prev_requested()`; closes on Space/Esc. `MediaDisplayWidget._open_quicklook()` builds it for the current selection.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep3_quicklook.py`:

```python
import pytest
from PySide2 import QtCore, QtGui

from ui.quicklook_overlay import QuickLookOverlay


@pytest.mark.gui
def test_shows_and_navigates(qtbot):
    ov = QuickLookOverlay()
    qtbot.addWidget(ov)
    ov.show_element({"name": "plate_a"}, preview_path=None)
    assert ov.title_label.text() == "plate_a"
    with qtbot.waitSignal(ov.next_requested, timeout=1000):
        ov.keyPressEvent(QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Right, QtCore.Qt.NoModifier))
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep3_quicklook.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the overlay**

Create `src/ui/quicklook_overlay.py`:

```python
# -*- coding: utf-8 -*-
"""Spacebar quicklook overlay (EP3)."""

from PySide2 import QtWidgets, QtCore, QtGui


class QuickLookOverlay(QtWidgets.QWidget):
    next_requested = QtCore.Signal()
    prev_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super(QuickLookOverlay, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        layout = QtWidgets.QVBoxLayout(self)
        self.title_label = QtWidgets.QLabel("")
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label = QtWidgets.QLabel("")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(480, 360)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)

    def show_element(self, element, preview_path):
        self.title_label.setText(element.get("name", ""))
        if preview_path:
            pix = QtGui.QPixmap(preview_path)
            if not pix.isNull():
                self.image_label.setPixmap(pix.scaled(
                    self.image_label.size(), QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation))
        self.show()
        self.setFocus()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Escape):
            self.close()
        elif key == QtCore.Qt.Key_Right:
            self.next_requested.emit()
        elif key == QtCore.Qt.Key_Left:
            self.prev_requested.emit()
        else:
            super(QuickLookOverlay, self).keyPressEvent(event)
```

- [ ] **Step 4: Add the Space trigger in MediaDisplayWidget**

In `MediaDisplayWidget`, install a key handler that opens quicklook on Space for the focused view. Add:

```python
    def _open_quicklook(self):
        from ui.quicklook_overlay import QuickLookOverlay
        el = self.get_selected_element()   # existing helper returning the current element dict
        if not el:
            return
        preview = self._resolve_preview_path(el)   # existing preview-path resolver
        self._quicklook = QuickLookOverlay(self)
        self._quicklook.next_requested.connect(self.select_next_item)
        self._quicklook.prev_requested.connect(self.select_previous_item)
        self._quicklook.show_element(el, preview)
```

In the gallery/table `keyPressEvent` (or an installed event filter — match the existing input handling), route `QtCore.Qt.Key_Space` to `self._open_quicklook()`. If `get_selected_element` / `_resolve_preview_path` / `select_next_item` don't exist under those names, use the existing selection + preview-path helpers (the context menu and thumbnail loader already resolve both).

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep3_quicklook.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ui/quicklook_overlay.py src/ui/media_display_widget.py tests/gui/test_ep3_quicklook.py
git commit -m "feat(ep3): add spacebar quicklook overlay with prev/next"
```

---

## Task 4: Keyboard help overlay

**Files:**
- Create: `src/ui/shortcut_help_overlay.py`
- Modify: `main.py` (`?` shortcut + Help menu action)
- Test: `tests/gui/test_ep3_help_overlay.py`

**Interfaces:**
- Produces: `ShortcutHelpOverlay(shortcuts, parent=None)` where `shortcuts` is `list[(action_label, key_text)]`; `collect_shortcuts(menu_bar) -> list[(str, str)]`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep3_help_overlay.py`:

```python
import pytest
from PySide2 import QtWidgets

from ui.shortcut_help_overlay import ShortcutHelpOverlay, collect_shortcuts


@pytest.mark.gui
def test_collect_and_render(qtbot):
    bar = QtWidgets.QMenuBar()
    m = bar.addMenu("File")
    act = m.addAction("Ingest Files")
    act.setShortcut("Ctrl+I")
    pairs = collect_shortcuts(bar)
    assert ("Ingest Files", "Ctrl+I") in pairs
    ov = ShortcutHelpOverlay(pairs + [("Command palette", "Ctrl+K")])
    qtbot.addWidget(ov)
    assert ov.table.rowCount() == len(pairs) + 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep3_help_overlay.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/shortcut_help_overlay.py`:

```python
# -*- coding: utf-8 -*-
"""Keyboard shortcut help overlay (EP3)."""

from PySide2 import QtWidgets, QtCore


def collect_shortcuts(menu_bar):
    """Return (label, key) for every action with a shortcut."""
    pairs = []

    def walk(actions):
        for a in actions:
            if a.menu():
                walk(a.menu().actions())
            elif a.text() and not a.shortcut().isEmpty():
                pairs.append((a.text().replace("&", ""), a.shortcut().toString()))

    if menu_bar is not None:
        walk(menu_bar.actions())
    return pairs


class ShortcutHelpOverlay(QtWidgets.QDialog):
    def __init__(self, shortcuts, parent=None):
        super(ShortcutHelpOverlay, self).__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(len(shortcuts), 2)
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for row, (label, key) in enumerate(shortcuts):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(label))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(key))
        layout.addWidget(self.table)
        self.resize(420, 480)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super(ShortcutHelpOverlay, self).keyPressEvent(event)
```

- [ ] **Step 4: Wire `?` + Help menu in MainWindow**

In `main.py` `__init__`:

```python
        self._help_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("?"), self)
        self._help_shortcut.activated.connect(self.open_shortcut_help)
```

Add the method and a Help-menu action pointing at it:

```python
    def open_shortcut_help(self):
        from ui.shortcut_help_overlay import ShortcutHelpOverlay, collect_shortcuts
        pairs = collect_shortcuts(self.menuBar())
        pairs += [("Command palette", "Ctrl+K"), ("Quicklook", "Space"),
                  ("Keyboard help", "?")]
        ShortcutHelpOverlay(pairs, self).exec_()
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep3_help_overlay.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ui/shortcut_help_overlay.py main.py tests/gui/test_ep3_help_overlay.py
git commit -m "feat(ep3): add keyboard shortcut help overlay"
```

---

# Cluster 3B — Context & loading

## Task 5: Extract shared metadata formatting

**Files:**
- Create: `src/ui/metadata_format.py`
- Modify: `src/ui/media_info_popup.py` (use the shared helpers)
- Test: `tests/unit/test_ep3_metadata_format.py`

**Interfaces:**
- Produces: `human_size(num_bytes) -> str`, `element_field_rows(element_dict) -> list[(label, value)]` (name/type/format/frames/size — the read-only display rows).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep3_metadata_format.py`:

```python
import pytest
from ui.metadata_format import human_size, element_field_rows


@pytest.mark.unit
def test_human_size_units():
    assert human_size(500) == "500 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


@pytest.mark.unit
def test_field_rows_include_core_fields():
    rows = dict(element_field_rows({"name": "a", "type": "2D", "format": ".exr",
                                    "frame_range": "1-10", "file_size": 1024}))
    assert rows["Name"] == "a"
    assert rows["Format"] == ".exr"
    assert rows["Frames"] == "1-10"
    assert rows["Size"] == "1.0 KB"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep3_metadata_format.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/metadata_format.py`:

```python
# -*- coding: utf-8 -*-
"""Shared element metadata formatting (EP3; reduces audit L10 duplication)."""


def human_size(num_bytes):
    n = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return "{:d} {}".format(int(n), unit)
            return "{:.1f} {}".format(n, unit)
        n /= 1024.0


def element_field_rows(element):
    return [
        ("Name", element.get("name", "")),
        ("Type", element.get("type", "")),
        ("Format", element.get("format", "") or ""),
        ("Frames", element.get("frame_range", "") or ""),
        ("Size", human_size(element.get("file_size", 0))),
    ]
```

Then update `src/ui/media_info_popup.py` to import and use `human_size` / `element_field_rows` in `show_element` instead of its inline size/field formatting (remove the now-duplicated local size code).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep3_metadata_format.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/metadata_format.py src/ui/media_info_popup.py tests/unit/test_ep3_metadata_format.py
git commit -m "feat(ep3): extract shared metadata formatting helpers"
```

---

## Task 6: `InspectorPanel` + right-pane split

**Files:**
- Create: `src/ui/inspector_panel.py`
- Modify: `main.py` (right pane becomes a vertical splitter: preview + inspector)
- Test: `tests/gui/test_ep3_inspector.py`

**Interfaces:**
- Consumes: `element_field_rows`, `db.update_element`, `db.set_element_rating`, `db.set_element_label`, `db.get_labels`.
- Produces: `InspectorPanel(db, parent=None)` with `show_element(element_id)`, `clear()`; editable rating/label/tags/comment commit to the DB.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep3_inspector.py`:

```python
import pytest


def _element(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,file_size) VALUES (1,'e','2D',2048)")
    return 1


@pytest.mark.gui
def test_shows_element_fields(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel
    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)
    assert "e" in ip.name_edit.text()


@pytest.mark.gui
def test_rating_edit_writes_through(qtbot, stax_db):
    from ui.inspector_panel import InspectorPanel
    eid = _element(stax_db)
    ip = InspectorPanel(stax_db)
    qtbot.addWidget(ip)
    ip.show_element(eid)
    ip.set_rating(4)
    assert stax_db.get_element_by_id(eid)["rating"] == 4
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep3_inspector.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the inspector**

Create `src/ui/inspector_panel.py`:

```python
# -*- coding: utf-8 -*-
"""Persistent editable inspector for the selected element (EP3)."""

import logging
from PySide2 import QtWidgets, QtCore

from ui.metadata_format import element_field_rows

logger = logging.getLogger(__name__)


class InspectorPanel(QtWidgets.QWidget):
    def __init__(self, db, parent=None):
        super(InspectorPanel, self).__init__(parent)
        self.db = db
        self._element_id = None
        form = QtWidgets.QFormLayout(self)

        self.readonly_labels = {}
        for label in ("Type", "Format", "Frames", "Size"):
            w = QtWidgets.QLabel("")
            self.readonly_labels[label] = w
            form.addRow(label + ":", w)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.editingFinished.connect(self._commit_name)
        form.addRow("Name:", self.name_edit)

        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.editingFinished.connect(self._commit_tags)
        form.addRow("Tags:", self.tags_edit)

        self.comment_edit = QtWidgets.QLineEdit()
        self.comment_edit.editingFinished.connect(self._commit_comment)
        form.addRow("Comment:", self.comment_edit)

        self.rating_spin = QtWidgets.QSpinBox()
        self.rating_spin.setRange(0, 5)
        self.rating_spin.valueChanged.connect(self.set_rating)
        form.addRow("Rating:", self.rating_spin)

        self.label_combo = QtWidgets.QComboBox()
        self.label_combo.addItem("(none)", None)
        for lbl in self.db.get_labels():
            self.label_combo.addItem(lbl["name"], lbl["label_id"])
        self.label_combo.currentIndexChanged.connect(self._commit_label)
        form.addRow("Label:", self.label_combo)

        self.clear()

    def clear(self):
        self._element_id = None
        self.setEnabled(False)

    def show_element(self, element_id):
        el = self.db.get_element_by_id(element_id)
        if not el:
            self.clear()
            return
        self._element_id = element_id
        self.setEnabled(True)
        for label, value in element_field_rows(el):
            if label in self.readonly_labels:
                self.readonly_labels[label].setText(str(value))
            elif label == "Name":
                self.name_edit.setText(str(value))
        self.tags_edit.setText(el.get("tags", "") or "")
        self.comment_edit.setText(el.get("comment", "") or "")
        self.rating_spin.setValue(el.get("rating", 0) or 0)
        idx = self.label_combo.findData(el.get("label_fk"))
        self.label_combo.setCurrentIndex(max(0, idx))

    def _commit_name(self):
        if self._element_id:
            self.db.update_element(self._element_id, name=self.name_edit.text())

    def _commit_tags(self):
        if self._element_id:
            self.db.update_element(self._element_id, tags=self.tags_edit.text())

    def _commit_comment(self):
        if self._element_id:
            self.db.update_element(self._element_id, comment=self.comment_edit.text())

    def set_rating(self, value):
        if self._element_id:
            self.db.set_element_rating(self._element_id, value)

    def _commit_label(self, _index):
        if self._element_id:
            self.db.set_element_label(self._element_id, self.label_combo.currentData())
```

- [ ] **Step 4: Split the right pane in MainWindow**

In `main.py`, replace the direct add of `video_player_pane` to `main_splitter` with a vertical splitter containing the preview and the inspector:

```python
        from ui.inspector_panel import InspectorPanel
        self.inspector = InspectorPanel(self.db)
        right_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right_split.addWidget(self.video_player_pane)
        right_split.addWidget(self.inspector)
        right_split.setSizes([500, 260])
        self.main_splitter.addWidget(right_split)
```

Connect the media view's selection-changed signal to `self.inspector.show_element(element_id)` (reuse the existing `on_selection_changed` handler; call `self.inspector.show_element(eid)` for a single selection, else `self.inspector.clear()`).

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep3_inspector.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/ui/inspector_panel.py main.py tests/gui/test_ep3_inspector.py
git commit -m "feat(ep3): add editable sticky inspector in the right pane"
```

---

## Task 7: Skeleton loading + scroll retention

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep3_skeleton_scroll.py`

**Interfaces:**
- Produces: `_skeleton_pixmap(size)` (neutral placeholder); items start with the skeleton until `on_preview_ready` swaps in the real thumbnail; `capture_scroll()` / `restore_scroll()` around detail transitions.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep3_skeleton_scroll.py`:

```python
import pytest
from PySide2 import QtGui


@pytest.mark.gui
def test_skeleton_pixmap_is_valid(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    px = w._skeleton_pixmap(128)
    assert isinstance(px, QtGui.QPixmap)
    assert not px.isNull()


@pytest.mark.gui
def test_scroll_capture_restore(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    qtbot.addWidget(w)
    w.capture_scroll()
    w.restore_scroll()   # must not raise even with empty views
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep3_skeleton_scroll.py -v`
Expected: FAIL — helpers missing.

- [ ] **Step 3: Implement**

Add to `MediaDisplayWidget`:

```python
    def _skeleton_pixmap(self, size):
        from PySide2 import QtGui, QtCore
        px = QtGui.QPixmap(size, size)
        px.fill(QtGui.QColor("#26282b"))
        painter = QtGui.QPainter(px)
        painter.setPen(QtGui.QColor("#3a3d41"))
        painter.drawRect(0, 0, size - 1, size - 1)
        painter.end()
        return px

    def capture_scroll(self):
        bar = self.gallery_view.verticalScrollBar()
        self._saved_scroll = bar.value() if bar else 0

    def restore_scroll(self):
        bar = self.gallery_view.verticalScrollBar()
        if bar is not None:
            bar.setValue(getattr(self, "_saved_scroll", 0))
```

In the thumbnail build path (`_update_views_with_elements`), set each new item's icon to `self._skeleton_pixmap(self.current_thumb_size)` before the real preview is available, so items render as skeletons until `on_preview_ready` replaces them. (`on_preview_ready` already swaps the icon in place — no change needed there.) Call `capture_scroll()` at the start of `_open_quicklook` and `restore_scroll()` when it closes. Use the real gallery-view attribute name if it differs from `gallery_view`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep3_skeleton_scroll.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep3_skeleton_scroll.py
git commit -m "feat(ep3): add skeleton placeholders and scroll retention"
```

---

# Cluster 3C — Shell polish (trimmable)

## Task 8: Layout presets

**Files:**
- Create: `src/ui/layout_manager.py`
- Modify: `main.py` (View → Layout menu + apply + persist)
- Test: `tests/unit/test_ep3_layout.py`

**Interfaces:**
- Produces: `LAYOUT_PRESETS` (dict name → `{main_sizes, right_visible, docks}`), `apply_preset(main_window, name)`, and preset persistence via `Config` key `layout_preset`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep3_layout.py`:

```python
import pytest
from ui.layout_manager import LAYOUT_PRESETS, preset_names


@pytest.mark.unit
def test_presets_defined():
    assert set(preset_names()) == {"Browse", "Review", "Ingest", "Curation"}
    for name in preset_names():
        p = LAYOUT_PRESETS[name]
        assert "main_sizes" in p and len(p["main_sizes"]) == 3
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep3_layout.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/layout_manager.py`:

```python
# -*- coding: utf-8 -*-
"""Named layout presets for the main window (EP3)."""

LAYOUT_PRESETS = {
    "Browse":   {"main_sizes": [280, 920, 360], "right_visible": True,
                 "docks": {"history": False, "settings": False, "analytics": False}},
    "Review":   {"main_sizes": [0, 700, 860], "right_visible": True,
                 "docks": {"history": False, "settings": False, "analytics": False}},
    "Ingest":   {"main_sizes": [280, 1000, 0], "right_visible": False,
                 "docks": {"history": True, "settings": False, "analytics": False}},
    "Curation": {"main_sizes": [320, 1040, 200], "right_visible": True,
                 "docks": {"history": False, "settings": False, "analytics": False}},
}


def preset_names():
    return ["Browse", "Review", "Ingest", "Curation"]


def apply_preset(main_window, name):
    preset = LAYOUT_PRESETS.get(name)
    if not preset:
        return
    main_window.main_splitter.setSizes(preset["main_sizes"])
    if hasattr(main_window, "video_player_pane"):
        main_window.video_player_pane.setVisible(preset["right_visible"])
    docks = preset["docks"]
    for key, dock_attr in (("history", "history_dock"), ("settings", "settings_dock"),
                           ("analytics", "analytics_dock")):
        dock = getattr(main_window, dock_attr, None)
        if dock is not None:
            dock.setVisible(docks.get(key, False))
    if getattr(main_window, "config", None):
        main_window.config.set("layout_preset", name)
```

- [ ] **Step 4: Add the View → Layout menu**

In `main.py` `setup_menus`, add a Layout submenu under View:

```python
        from ui.layout_manager import preset_names, apply_preset
        layout_menu = view_menu.addMenu("Layout")
        for name in preset_names():
            act = QtWidgets.QAction(name, self)
            act.triggered.connect(lambda checked=False, n=name: apply_preset(self, n))
            layout_menu.addAction(act)
```

At the end of `__init__`, restore the saved preset: `apply_preset(self, self.config.get("layout_preset", "Browse"))`.

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/unit/test_ep3_layout.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ui/layout_manager.py main.py tests/unit/test_ep3_layout.py
git commit -m "feat(ep3): add layout presets (Browse/Review/Ingest/Curation)"
```

---

## Task 9: Accessibility controls

**Files:**
- Create: `src/ui/accessibility.py`
- Modify: `src/ui/settings_panel.py` (Accessibility section), `main.py` (apply at startup)
- Test: `tests/unit/test_ep3_accessibility.py`

**Interfaces:**
- Produces: `scaled_point_size(base_pt, scale_percent) -> int`, `apply_accessibility(app, config)` (reads the three `a11y_*` config keys and applies font scale / high-contrast / focus QSS).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep3_accessibility.py`:

```python
import pytest
from ui.accessibility import scaled_point_size


@pytest.mark.unit
def test_scaled_point_size():
    assert scaled_point_size(10, 100) == 10
    assert scaled_point_size(10, 150) == 15
    assert scaled_point_size(10, 125) == 12
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep3_accessibility.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/accessibility.py`:

```python
# -*- coding: utf-8 -*-
"""Accessibility application: text scale, high contrast, focus assist (EP3)."""

_HIGH_CONTRAST_QSS = """
QWidget { background: #000000; color: #FFFFFF; }
QLineEdit, QListWidget, QTableWidget { background: #101010; color: #FFFFFF; }
"""

_FOCUS_QSS = """
*:focus { border: 2px solid #4C9AFF; }
"""


def scaled_point_size(base_pt, scale_percent):
    return int(round(base_pt * (scale_percent / 100.0)))


def apply_accessibility(app, config):
    high_contrast = bool(config.get("a11y_high_contrast", False))
    text_scale = int(config.get("a11y_text_scale", 100))
    focus_assist = bool(config.get("a11y_focus_assist", False))

    font = app.font()
    base = getattr(config, "_a11y_base_pt", None)
    if base is None:
        base = font.pointSize() if font.pointSize() > 0 else 9
        config._a11y_base_pt = base
    font.setPointSize(scaled_point_size(base, text_scale))
    app.setFont(font)

    qss = ""
    if high_contrast:
        qss += _HIGH_CONTRAST_QSS
    if focus_assist:
        qss += _FOCUS_QSS
    # append to existing stylesheet without discarding the base theme
    base_qss = getattr(config, "_a11y_base_qss", None)
    if base_qss is None:
        base_qss = app.styleSheet()
        config._a11y_base_qss = base_qss
    app.setStyleSheet(base_qss + qss)
```

- [ ] **Step 4: Add the settings section + startup apply**

In `settings_panel.py`, add an Accessibility group (checkbox high-contrast, a 100–150 spin for text scale, checkbox focus assist) that writes the `a11y_*` config keys and calls `apply_accessibility(QtWidgets.QApplication.instance(), self.config)` on change. In `main.py`, after the app/palette setup, call `apply_accessibility(app, self.config)` once at startup.

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/unit/test_ep3_accessibility.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ui/accessibility.py src/ui/settings_panel.py main.py tests/unit/test_ep3_accessibility.py
git commit -m "feat(ep3): add accessibility controls (contrast/text-scale/focus)"
```

---

## Task 10: Onboarding checklist

**Files:**
- Create: `src/ui/onboarding_checklist.py`
- Modify: `main.py` (first-run show + Help re-open)
- Test: `tests/gui/test_ep3_onboarding.py`

**Interfaces:**
- Consumes: `db.get_all_stacks`, `db.get_elements_count` (or equivalent), `config`.
- Produces: `OnboardingChecklist(db, config, parent=None)` with `step_states() -> dict[str, bool]` and a `dismiss()` that sets `onboarding_dismissed`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep3_onboarding.py`:

```python
import pytest


class _Cfg:
    def __init__(self): self.d = {}
    def get(self, k, default=None): return self.d.get(k, default)
    def set(self, k, v): self.d[k] = v


@pytest.mark.gui
def test_step_states_reflect_db(qtbot, stax_db):
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    states = oc.step_states()
    assert states["Create a stack"] is False
    stax_db.create_stack("S", "/tmp/S")
    assert oc.step_states()["Create a stack"] is True


@pytest.mark.gui
def test_dismiss_persists(qtbot, stax_db):
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    oc.dismiss()
    assert cfg.get("onboarding_dismissed") is True
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep3_onboarding.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/onboarding_checklist.py`:

```python
# -*- coding: utf-8 -*-
"""First-run onboarding checklist (EP3)."""

from PySide2 import QtWidgets, QtCore


class OnboardingChecklist(QtWidgets.QWidget):
    def __init__(self, db, config, parent=None):
        super(OnboardingChecklist, self).__init__(parent)
        self.db = db
        self.config = config
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Getting started</b>"))
        self._checks = {}
        for step in ("Create a stack", "Ingest files", "Insert into Nuke"):
            cb = QtWidgets.QCheckBox(step)
            cb.setEnabled(False)
            self._checks[step] = cb
            layout.addWidget(cb)
        self.dismiss_button = QtWidgets.QPushButton("Dismiss")
        self.dismiss_button.clicked.connect(self.dismiss)
        layout.addWidget(self.dismiss_button)
        self.refresh()

    def step_states(self):
        stacks = self.db.get_all_stacks()
        has_stack = len(stacks) > 0
        has_element = False
        try:
            for s in stacks:
                for lst in self.db.get_lists_by_stack(s["stack_id"]):
                    if self.db.get_elements_count(lst["list_id"]) > 0:
                        has_element = True
                        break
        except Exception:
            has_element = False
        inserted = bool(self.config.get("onboarding_inserted", False))
        return {"Create a stack": has_stack, "Ingest files": has_element,
                "Insert into Nuke": inserted}

    def refresh(self):
        for step, done in self.step_states().items():
            self._checks[step].setChecked(done)

    def dismiss(self):
        self.config.set("onboarding_dismissed", True)
        self.hide()
```

- [ ] **Step 4: Show on first run + Help re-open**

In `main.py`, after the window is built, if `not self.config.get("onboarding_dismissed", False)`, show the checklist (as a small floating widget or a dock). Add a Help → "Getting Started" action that constructs and shows it again. (Use the exact `get_lists_by_stack` / `get_elements_count` names present in the DB; if they differ, use the real list/count methods.)

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/gui/test_ep3_onboarding.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/ui/onboarding_checklist.py main.py tests/gui/test_ep3_onboarding.py
git commit -m "feat(ep3): add first-run onboarding checklist"
```

---

## Task 11: Minimal start page

**Files:**
- Create: `src/ui/start_page.py`
- Modify: `src/db_manager.py` (`get_recent_elements`), `main.py` (show on launch/empty)
- Test: `tests/unit/test_ep3_recent.py`, `tests/gui/test_ep3_start_page.py`

**Interfaces:**
- Produces: `db.get_recent_elements(limit=12) -> list[dict]` (newest by `created_at`); `StartPage(db, user_name, machine_name, parent=None)` with sections Recent / Favorites / Most-used and signal `element_activated(int)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ep3_recent.py`:

```python
import pytest


@pytest.mark.unit
def test_get_recent_elements_newest_first(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("a", "b", "c"):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')", (name,))
    recent = stax_db.get_recent_elements(limit=2)
    assert len(recent) == 2
    assert recent[0]["name"] == "c"   # newest first
```

Create `tests/gui/test_ep3_start_page.py`:

```python
import pytest


@pytest.mark.gui
def test_start_page_renders_recent(qtbot, stax_db):
    from ui.start_page import StartPage
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'a','2D')")
    sp = StartPage(stax_db, user_name="alice", machine_name="ws01")
    qtbot.addWidget(sp)
    assert sp.recent_count() >= 1
```

- [ ] **Step 2: Run them to verify failure**

Run: `pytest tests/unit/test_ep3_recent.py tests/gui/test_ep3_start_page.py -v`
Expected: FAIL — method/module missing.

- [ ] **Step 3: Implement `get_recent_elements`**

Add to `DatabaseManager`:

```python
    def get_recent_elements(self, limit=12):
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM elements ORDER BY created_at DESC, element_id DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
```

- [ ] **Step 4: Implement `StartPage`**

Create `src/ui/start_page.py`:

```python
# -*- coding: utf-8 -*-
"""Minimal personalized start page (EP3): Recent / Favorites / Most-used."""

import logging
from PySide2 import QtWidgets, QtCore

logger = logging.getLogger(__name__)


class StartPage(QtWidgets.QWidget):
    element_activated = QtCore.Signal(int)

    def __init__(self, db, user_name, machine_name, parent=None):
        super(StartPage, self).__init__(parent)
        self.db = db
        self.user_name = user_name
        self.machine_name = machine_name
        self._layout = QtWidgets.QVBoxLayout(self)
        self._recent_list = self._add_section("Recent")
        self._fav_list = self._add_section("Favorites")
        self._top_section, self._top_list = self._add_section("Most-used", return_box=True)
        self.refresh()

    def _add_section(self, title, return_box=False):
        box = QtWidgets.QGroupBox(title)
        v = QtWidgets.QVBoxLayout(box)
        lst = QtWidgets.QListWidget()
        lst.itemActivated.connect(self._on_activated)
        v.addWidget(lst)
        self._layout.addWidget(box)
        return (box, lst) if return_box else lst

    def _fill(self, lst, elements):
        lst.clear()
        for el in elements:
            item = QtWidgets.QListWidgetItem(el.get("name", ""))
            item.setData(QtCore.Qt.UserRole, el.get("element_id"))
            lst.addItem(item)

    def refresh(self):
        self._fill(self._recent_list, self.db.get_recent_elements(12))
        try:
            favs = self.db.get_favorites(self.user_name, self.machine_name)
        except Exception:
            favs = []
        self._fill(self._fav_list, favs)
        try:
            top = self.db.get_top_inserted_elements(10)
        except Exception:
            top = []
        if top:
            self._fill(self._top_list, top)
            self._top_section.setVisible(True)
        else:
            self._top_section.setVisible(False)

    def recent_count(self):
        return self._recent_list.count()

    def _on_activated(self, item):
        eid = item.data(QtCore.Qt.UserRole)
        if eid is not None:
            self.element_activated.emit(eid)
```

- [ ] **Step 5: Show the start page on launch**

In `main.py`, show `StartPage` in the media area (e.g. the stacked widget's index-0 page, coexisting with EP1's empty states) when no list is selected at startup; connect `element_activated` to the existing element-open path. If `get_favorites` uses a different parameter order, match the real signature (`add_favorite(element_id, machine_name, user_name=None)` suggests `get_favorites(user_name, machine_name)` — verify).

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/unit/test_ep3_recent.py tests/gui/test_ep3_start_page.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full EP3 suite**

Run: `pytest -m "not manual" -k ep3 -v`
Expected: all EP3 tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/db_manager.py src/ui/start_page.py main.py tests/unit/test_ep3_recent.py tests/gui/test_ep3_start_page.py
git commit -m "feat(ep3): add get_recent_elements and minimal start page"
```

---

## Self-Review

**1. Spec coverage:**
- Command palette (F049) → Tasks 1–2 ✓
- Spacebar quicklook (F050) → Task 3 ✓
- Keyboard help overlay (F056) → Task 4 ✓
- Shared metadata format (L10 reduction) → Task 5 ✓
- Sticky inspector (F051) → Task 6 ✓
- Skeleton loading + scroll retention (§7.7) → Task 7 ✓
- Layout presets (F055) → Task 8 ✓
- Accessibility (F057) → Task 9 ✓
- Onboarding checklist (F054) → Task 10 ✓
- Minimal start page (F058) + `get_recent_elements` → Task 11 ✓
- Tests unit + headless GUI → every task ✓
- State persistence in Config (§3.10): layout (Task 8), a11y (Task 9), onboarding (Task 10) ✓

**2. Placeholder scan:** New units (palette, overlays, inspector, layout, accessibility, onboarding, start page, metadata_format) have complete code. Integration steps name the exact reuse point (`on_selection_changed`, `on_preview_ready`, `get_lists_by_stack`) and give the concrete fallback where a host method name may differ, rather than leaving it open.

**3. Type consistency:** `harvest_actions`/`CommandRegistry`/`fuzzy_filter` (Task 1) are consumed unchanged in Task 2. `element_field_rows`/`human_size` (Task 5) are used in Task 6. `InspectorPanel.show_element`/`set_rating`/`clear` match Tasks 6 & (main wiring). `apply_preset`/`preset_names`/`LAYOUT_PRESETS` match Tasks 8. `scaled_point_size`/`apply_accessibility` match Task 9. `get_recent_elements` (Task 11) matches its test and StartPage use. Config keys (`layout_preset`, `a11y_high_contrast`, `a11y_text_scale`, `a11y_focus_assist`, `onboarding_dismissed`) are consistent across Tasks 8–11 and the spec.

**Note for the executor:** EP3 assumes EP1 (+ SP1/SP2/SP6). If SP1 isn't landed, drop `write=` and expect `get_top_inserted_elements` to be absent (the start page's Most-used section hides — no failure). Skeletons only appear once SP2's async worker emits `preview_ready`; without it, thumbnails load as today. Read `media_display_widget.py` and `main.py` for the exact local method names before wiring (`gallery_view`, `on_selection_changed`, preview-path resolver) and adapt the reuse calls. Never weaken a test to pass — mark `xfail(strict)` with the dependency id if a seam is genuinely absent.
