# EP2 — Search & Discovery UX — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F007 (saved searches), F008 (smart collections), F009 (synonyms), F010 (negative filters), F011 (fuzzy/typo), F012 (query suggestions/recent), plus the faceted-filter/chips/count UX of §7.1.

---

## 1. Background & Motivation

Today StaX search is a single-property `LIKE` (`search_elements(text, property, loose/strict)`) plus inline `#tag` / `tag:` filters and `search_elements_by_tags`. There are no facets, no way to combine filters, no removable filter chips, no result count, and no way to save or reuse a query. EP2 turns browsing into real discovery: a composable filter model with a faceted drawer and chips, personal saved searches, shared smart collections, and dependency-free text-quality upgrades (synonyms, "did you mean", recent/suggestions).

### Locked design decisions
- **Backend:** a **composable SQL query builder** for structured facets + `LIKE` for text; **stdlib `difflib`** for typo suggestions. No new dependencies. No FTS5/AI.
- **Facet placement:** a **collapsible drawer on the media view** with removable **filter chips** and a live **result count** above the results.
- **Saved searches and smart collections are SEPARATE entities:** saved searches are **personal** re-runnable queries; smart collections are **team-shared** live nav nodes.
- Ratings/labels (EP1) are facetable dimensions.
- Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`.

### Dependencies (must land first)
- **EP1** — `elements.rating` and `elements.label_fk` + the `labels` table (facet dimensions).
- **SP1** — consolidated `DatabaseManager`, `get_connection(write=…)`, column whitelisting for dynamic SQL, migration runner.

### Delivery clusters (incremental, in order)
- **2A — Faceted filtering core:** `FilterSpec` + query builder, facet drawer, chips, result count, negative filters. Independently shippable.
- **2B — Persistence:** saved searches (personal) + smart collections (shared).
- **2C — Text quality:** synonyms, fuzzy suggestions, recent/suggestions. Trimmable if scope pressure arises.

---

## 2. Goals / Non-Goals

### Goals
- One serializable `FilterSpec` describing any combination of text + facets + exclusions.
- Faceted drawer (Type, Format, Tag, Rating, Label, Status) with per-value counts and exclude toggles.
- Removable filter chips + live result count.
- Personal saved searches; shared smart-collection nav nodes.
- Synonym-expanded search, "did you mean" typo help, recent-query suggestions.

### Non-Goals (deferred)
- Semantic / visual / similarity / color / transcript search → **EP7**.
- FTS5 or spellfix1 full-text indexing (revisit only if scale demands).
- Cross-field relevance ranking beyond `LIKE` matching + difflib suggestions.
- Rating/label *editing* (that's EP1); EP2 only reads them as facets.

---

## 3. Detailed Design

### 3.1 FilterSpec (serializable filter model)

A plain JSON-serializable dict with defaulted, optional keys:

```
{
  "text": str,                 # free text (LIKE across name/comment/tags)
  "types": [str],              # subset of 2D/3D/Toolset
  "formats": [str],            # e.g. ['.exr', '.mov']
  "tags_all": [str],           # AND
  "tags_any": [str],           # OR
  "tags_exclude": [str],       # NOT (F010)
  "formats_exclude": [str],    # NOT (F010)
  "rating_min": int,           # 0..5, >= comparison
  "label_fks": [int],          # any-of
  "is_deprecated": bool|None,  # None = don't filter
  "is_hard_copy": bool|None,
  "list_fk": int|None,         # scope to a list
  "stack_fk": int|None         # scope to a stack
}
```

A helper `filter_spec.py` provides `empty_filter()`, validation, and `is_active(spec)`.

### 3.2 Query builder & DB API (`DatabaseManager`)

All dynamic column references are drawn from a fixed whitelist (SP1 pattern); values are parameterized.

```
search_elements_advanced(filter_spec, limit=None, offset=0) -> list[dict]
count_elements_advanced(filter_spec) -> int
get_facet_counts(filter_spec) -> dict     # {'type': {...}, 'format': {...}, 'tag': {...},
                                          #  'rating': {...}, 'label': {...}, 'status': {...}}
```

- Text → `(name LIKE ? OR comment LIKE ? OR tags LIKE ?)`.
- `tags_all` → one `tags LIKE ?` per tag (AND); `tags_any` → OR group; `tags_exclude`/`formats_exclude` → `NOT LIKE` / `format NOT IN (...)`.
- `rating_min` → `rating >= ?`; `label_fks` → `label_fk IN (...)`; flags → equality when not None; scope → `list_fk`/`stack_fk`.
- `get_facet_counts` computes each facet's counts **against the other active filters** (so counts reflect what a click would yield), via one `GROUP BY` query per facet.

### 3.3 Facet drawer, chips, count (2A UI)

- `FacetDrawer(QWidget)` — collapsible drawer docked at the left of the media panel. Groups: **Type, Format, Tag, Rating (≥N), Label, Status** (Deprecated / Hard vs Soft). Each value is a checkable row with a count; each supports an **exclude** state (three-state: off / include / exclude) for negative filters. Any change emits `filter_changed(FilterSpec)`.
- `FilterChipBar(QWidget)` — above the results: one removable chip per active filter clause, a live **"N results"** label, and **Clear all**. Removing a chip emits an updated `FilterSpec`.
- `MediaDisplayWidget.apply_filter(filter_spec)` runs `search_elements_advanced` + `count_elements_advanced`, refreshes the drawer counts via `get_facet_counts`, and repaints. Pagination continues to use `limit/offset`.

### 3.4 Saved searches (2B — personal)

```sql
CREATE TABLE saved_searches (
    saved_search_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name    TEXT NOT NULL,
    machine_name TEXT,
    name         TEXT NOT NULL,
    filter_json  TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

DB API: `create_saved_search(name, filter_spec, user_name, machine_name)`, `get_saved_searches(user_name)`, `delete_saved_search(id)`. A **"Saved Searches"** section in `StacksListsPanel` lists the current user's entries; clicking loads the `FilterSpec` into the drawer and applies it. A **"Save current search…"** control captures the active `FilterSpec`.

### 3.5 Smart collections (2B — shared nav nodes)

```sql
CREATE TABLE smart_collections (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    filter_json TEXT NOT NULL,
    created_by  TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0
);
```

DB API: `create_smart_collection`, `get_smart_collections`, `update_smart_collection`, `delete_smart_collection`. Shown as their own nodes in `StacksListsPanel` (team-shared); selecting one applies its `FilterSpec` live (always-current matches). Create/edit/delete are admin-gated (EP1 `check_admin_permission` pattern), managed from a settings surface or a "New smart collection from current filter" action.

### 3.6 Text quality (2C)

- **Synonyms (F009):** `search_synonyms(synonym_id, term, group_key)` (admin-managed). `expand_terms(text) -> list[str]` groups terms by `group_key`; the query builder ORs the expanded set for text/tag matching.
- **Fuzzy (F011):** `suggest_correction(query) -> str|None` using `difflib.get_close_matches` over the union of tag vocabulary (`get_all_tags`) and element names; surfaced as a non-blocking **"Did you mean *X*?"** line when results are empty/sparse. Never rewrites the query automatically.
- **Suggestions / recent (F012):** `recent_searches(user_name, query_text, ran_at)` capped to N (e.g. 20) per user; `add_recent_search`, `get_recent_searches(user_name)`. The search box shows a dropdown of recent queries + matching tags as the user types.

### 3.7 Data model summary
New tables: `saved_searches`, `smart_collections`, `search_synonyms`, `recent_searches` (all via SP1's migration runner). No changes to `elements` (EP1 already added rating/label).

---

## 4. Architecture & File Impact

| File | Change |
|---|---|
| `src/filter_spec.py` (new) | `FilterSpec` helpers: `empty_filter`, validation, `is_active` |
| `src/db_manager.py` | Query builder (`search_elements_advanced`, `count_elements_advanced`, `get_facet_counts`), saved-search / smart-collection / synonym / recent CRUD, migrations for 4 tables |
| `src/ui/facet_drawer.py` (new) | `FacetDrawer` widget |
| `src/ui/filter_chip_bar.py` (new) | `FilterChipBar` widget |
| `src/ui/media_display_widget.py` | Host drawer + chip bar; `apply_filter`; "did you mean" line; recent dropdown |
| `src/ui/stacks_lists_panel.py` | "Saved Searches" section + smart-collection nodes |
| `src/ui/settings_panel.py` | Synonym management (admin); smart-collection management (admin) |

New widgets and the filter model live in their own files (single responsibility).

---

## 5. Testing Strategy

- **Unit (`tests/unit`):**
  - Query builder: each facet + text + excludes + rating_min produces correct parameterized SQL and rows against the `stax_db` fixture (seed a small element set with varied type/format/tags/rating/label).
  - `get_facet_counts` respects other active filters.
  - Saved-search CRUD scoped by user; smart-collection CRUD (unique name); synonym expansion; `suggest_correction` picks the near match and returns `None` when nothing is close; recent-search cap enforced.
- **GUI (`tests/gui`, headless):**
  - `FacetDrawer` toggles produce the expected `FilterSpec` (include and exclude states).
  - `FilterChipBar` renders one chip per clause, removal updates the spec, count label reflects results.
  - Clicking a saved search / smart collection applies its filter.
  - "Did you mean" line appears for a typo query and is hidden otherwise.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Comma-joined `tags` column makes tag facets/excludes imprecise (substring matches) | Match on delimited boundaries (`',' || tags || ','` LIKE `%,tag,%`); documented; a normalized tag table is a later optimization (report/EP-meta). |
| Facet-count queries add load on large libraries | Counts are simple `GROUP BY`; run them lazily on drawer open and cache per applied filter; pagination unaffected. |
| Left panel + new drawer compete for horizontal space | Drawer is collapsible and remembers its state; default collapsed until the user filters. |
| FilterSpec schema drift between saved JSON and code | Version the spec with a `v` key; `empty_filter()` supplies defaults so older saved filters load forward-compatibly. |
| Scope creep across 3 clusters | 2A ships and is useful alone; 2B and 2C are separately committable; 2C is explicitly trimmable. |

---

## 7. Deliverables Checklist
- [ ] `FilterSpec` helpers + validation.
- [ ] Query builder: `search_elements_advanced`, `count_elements_advanced`, `get_facet_counts`.
- [ ] `FacetDrawer` + `FilterChipBar` + `apply_filter` + result count.
- [ ] Negative filters (exclude tags/formats) in builder + drawer.
- [ ] Saved searches (table + CRUD + nav section).
- [ ] Smart collections (table + CRUD + nav nodes + admin management).
- [ ] Synonyms (table + expansion + admin management).
- [ ] Fuzzy "did you mean" + recent-query suggestions.
- [ ] Unit + headless GUI tests green.

---

## 8. Follow-on
EP3 (Browse productivity) adds the command palette and quicklook that pair with this search UX. EP7 (AI discovery) layers semantic/visual search on top of the same `FilterSpec`/result surface.
