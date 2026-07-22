# EP1 — Curation Primitives — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX **feature-enhancement program** (Enhancement Projects EP1–EP9), derived from `STAX_FEATURE_ENHANCEMENT_REPORT.md`. EP1 is the first enhancement sub-project and delivers the highest visible-value-per-effort curation upgrades.
**Covers report features:** F013 (ratings), F014 (color labels), F052 (multi-select action tray), F053 (context-aware empty states), plus the "quick metadata fields" of §7.4.

---

## 1. Background & Motivation

The enhancement report identifies fast, visible curation upgrades as the highest near-term value. Today StaX lets users tag, comment, favorite, and deprecate elements, but has **no rating, no color-label status marker, no visible bulk-action surface** (bulk actions are hidden in a context menu — report §7.4), and **generic empty screens**. EP1 adds team-shared ratings and an admin-configurable color-label palette, surfaces them in the grid and table with inline quick-edit, replaces the hidden bulk actions with a visible multi-select action tray, and adds action-driving empty states to the four highest-traffic zero-data screens.

### Program context / locked decisions
- **Build on the remediation program (SP0–SP8); do not duplicate it.** EP1 assumes SP-level fixes have landed.
- **Ratings and labels are team-shared on the element** (like tags/comments), not per-user.
- **Color labels use an admin-configurable palette** (color + name + meaning), seeded with a default set.
- **Action tray = full curation set**; the context menu remains as a secondary path.
- **Empty states cover the top 4 views.**
- Target platforms Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`.

### Dependencies (must land before EP1 executes)
- **SP1** — versioned migration runner, consolidated `DatabaseManager`, `get_connection(write=…)` read/write scoping, `bulk`/`update_element_metadata` patterns.
- **SP6** — multi-select correctness (M3 admin flag via `main_window`, M5 cache handling), the wired `BatchEditDialog` (L2), and `MainWindow.check_admin_permission`.

---

## 2. Goals / Non-Goals

### Goals
- Team-shared 0–5 star rating per element.
- Admin-configurable color-label palette; one label per element.
- Grid badges + table columns for rating and label, with **inline quick-edit** (no dialog).
- A persistent multi-select **action tray** with the full curation set.
- A reusable **empty-state** component wired into 4 views.

### Non-Goals (deferred)
- Filtering / sorting / smart-collections *by* rating or label → **EP2**.
- Rating as an input to AI ranking / similarity → **EP7**.
- Per-user (personal) ratings; free-form multi-labels overlapping tags.
- Review/approval *statuses* (WIP/Review/Approved as a versioned workflow) → **EP5** (distinct from the color-label marker here).

---

## 3. Detailed Design

### 3.1 Data model (via SP1 migration runner — new schema version)

```sql
ALTER TABLE elements ADD COLUMN rating INTEGER NOT NULL DEFAULT 0;   -- 0 = unrated, 1..5 stars
ALTER TABLE elements ADD COLUMN label_fk INTEGER;                    -- nullable

CREATE TABLE IF NOT EXISTS labels (
    label_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    color_hex  TEXT NOT NULL,          -- e.g. '#E5484D'
    meaning    TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);
```

- `elements.label_fk` references `labels.label_id` with `ON DELETE SET NULL`. Because SQLite cannot add an FK via `ALTER`, the constraint is enforced in application code (`delete_label` nulls referencing rows in the same transaction) and documented; the column is a plain nullable INTEGER.
- **Default palette seeded on migration** (admins may edit/reorder/delete): Red `#E5484D` (Reject), Yellow `#F5D90A` (Review), Green `#30A46C` (Approved), Blue `#3E63DD`, Purple `#8E4EC6`, Orange `#F76B15`, Gray `#8B8D98`.
- Rating is validated to the range 0–5 at the DB API boundary (out-of-range raises `ValueError`).

### 3.2 `DatabaseManager` API (new methods)

All writes acquire `get_connection(write=True)`; reads use `get_connection(write=False)`.

```
set_element_rating(element_id: int, rating: int) -> None          # clamps/validates 0..5
set_element_label(element_id: int, label_fk: int | None) -> None
bulk_set_rating(element_ids: list[int], rating: int) -> int       # returns rows affected
bulk_set_label(element_ids: list[int], label_fk: int | None) -> int
get_labels() -> list[dict]                                        # ordered by sort_order
create_label(name: str, color_hex: str, meaning: str = "", sort_order: int = 0) -> int
update_label(label_id: int, **fields) -> None                    # whitelist: name/color_hex/meaning/sort_order
delete_label(label_id: int) -> None                              # nulls elements.label_fk, then deletes
```

`color_hex` is validated against `^#[0-9A-Fa-f]{6}$`. `update_label` uses the same column-whitelist approach SP1 introduced for `update_element` (no string-formatted column injection).

### 3.3 Settings: label palette management

A new **"Labels"** tab in `src/ui/settings_panel.py` (added via the existing `addTab` pattern), admin-gated:
- Non-admin: read-only list of swatch • name • meaning.
- Admin: a `QTableWidget` of labels with Add / Edit / Delete and a `QColorDialog` swatch picker; drag or up/down to reorder (`sort_order`). Edits call the labels CRUD methods and emit the panel's existing `settings_changed` signal so open galleries refresh chips.

### 3.4 Grid & table surfacing + inline quick-edit

- **Grid** (`media_display_widget.py`): extend `_apply_status_badges` (line 813) to overlay (a) a compact star strip reflecting `rating` and (b) a label color-chip in a thumbnail corner. On item hover, show an inline 5-star setter and a label swatch dropdown that call `set_element_rating` / `set_element_label` and repaint that item only (no page rebuild — consistent with the SP2 in-place update model).
- **Table** (`media_display_widget.py:178-179`): grow `setColumnCount(6)` → `8` and append headers `'Rating'`, `'Label'`. Two `QStyledItemDelegate`s render/edit the star widget and the colored chip; committing an edit calls the corresponding DB method and updates the model in place.

### 3.5 Multi-select action tray

A new `MultiSelectActionTray(QWidget)` docked at the bottom of `MediaDisplayWidget`:
- Hidden when `< 2` items selected; shown with a live "N selected" count otherwise.
- Buttons: **Rate** (star popup), **Label** (palette popup), **Add tag**, **Favorite**, **Add to playlist**, **Deprecate**, **Delete**, **Edit…** (opens SP6's `BatchEditDialog`).
- Each button calls the bulk DB method for the current selection; **Delete/Deprecate** are gated by `self.main_window.check_admin_permission()` (SP6 pattern). After an action, the tray refreshes affected items in place.
- The existing context menu is retained as a secondary path (no regression).

### 3.6 Empty states

A reusable widget:

```
EmptyStateWidget(headline: str, message: str, primary_action: (label, callable),
                 secondary_action: (label, callable) | None = None,
                 kind: str = "informational")   # informational | action | celebratory
```

Rendered through the existing index-0 empty page of the `QStackedWidget`. `kind` selects an icon/tone. Wired into 4 views:
1. **Empty library (first-run):** "No assets yet" / "Ingest footage, sequences, or toolsets to get started." → primary **Ingest files…** (`kind=action`).
2. **Empty list/stack:** "This list is empty" / "Add assets to <list>." → primary **Ingest into this list…** (`kind=action`).
3. **No search results:** "No matches for '<query>'" / "Try fewer terms or clear filters." → primary **Clear filters**, secondary suggestion (`kind=informational`).
4. **Empty favorites/playlist:** "Nothing here yet" / "Star assets or add them to a playlist to collect them." → primary **Browse library** (`kind=informational`).

---

## 4. Architecture & File Impact

| File | Change |
|---|---|
| `src/db_manager.py` | New rating/label columns (migration), labels table + seed, 9 new methods |
| `src/db_migrations.py` (SP1's runner) | New migration step adding columns/table/seed |
| `src/ui/settings_panel.py` | New admin-gated "Labels" tab |
| `src/ui/media_display_widget.py` | Grid badges + hover quick-edit; 2 table columns + delegates; host the tray + empty-state page wiring |
| `src/ui/multi_select_action_tray.py` (new) | The action-tray widget |
| `src/ui/empty_state_widget.py` (new) | The reusable empty-state widget |
| `main.py` | Provide `Ingest files…` / `Browse library` callbacks to empty states |

New widgets live in their own files (single responsibility) rather than swelling the already-large `media_display_widget.py`.

---

## 5. Testing Strategy

- **Unit (`tests/unit`):** rating clamp/validation (0..5, reject 6/-1); `color_hex` regex; labels CRUD; `delete_label` nulls `elements.label_fk`; `bulk_set_rating`/`bulk_set_label` row counts; migration adds columns + seeds 7 labels. Use the `stax_db` fixture.
- **GUI (`tests/gui`, headless):** table shows Rating/Label columns and a delegate edit calls the DB; `MultiSelectActionTray` is hidden at <2 and visible with correct count at ≥2; Rate/Label/Delete invoke the bulk methods (Delete gated by a stubbed `check_admin_permission`); `EmptyStateWidget` renders headline + primary action and fires the callback; each of the 4 views selects the correct empty state; the Labels settings tab is read-only for a non-admin.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| SQLite can't `ALTER`-add the FK | Enforce `ON DELETE SET NULL` in `delete_label` app-code within one transaction; cover with a test. |
| Bottom tray crowds small windows | Tray is a single scrollable row; collapses to icons under a width threshold. |
| Inline star editing conflicts with drag-to-Nuke / selection | Quick-edit controls only appear on hover in a dedicated badge zone; dragging the item body still initiates the Nuke drag. |
| Label palette edits leave stale chips in open views | `settings_changed` triggers a chip refresh; deleted labels resolve to "no label" via `ON DELETE SET NULL`. |

---

## 7. Deliverables Checklist
- [ ] Migration: `rating` + `label_fk` columns, `labels` table, seeded palette.
- [ ] 9 `DatabaseManager` methods with validation + tests.
- [ ] Labels settings tab (admin-gated).
- [ ] Grid badges + hover quick-edit for rating/label.
- [ ] Table Rating/Label columns + delegates.
- [ ] `MultiSelectActionTray` with the full curation set + admin gating.
- [ ] `EmptyStateWidget` wired into the 4 views.
- [ ] Unit + headless GUI tests green.

---

## 8. Follow-on
EP2 (Search & discovery UX) consumes EP1's rating/label columns for faceted filtering and smart collections. EP5 (Review & approval) introduces versioned *statuses* distinct from EP1's color-label marker.
