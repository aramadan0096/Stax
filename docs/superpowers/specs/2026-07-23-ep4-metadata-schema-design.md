# EP4 — Metadata Schema & Automation — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F015 (custom metadata schema by stack), F016 (metadata templates), F018 (metadata inheritance), F019 (auto-tag rules by folder/path), F020 (metadata quality checker), F021 (asset relationship links), F022 (naming convention assistant).

---

## 1. Background & Motivation

StaX metadata today is a fixed set — name, type, format, frame range, comment, tags (+ EP1 rating/label). Studios need **custom, typed fields per asset kind** (a plate stack wants Shot/Sequence/Colorspace; a 3D stack wants Poly-count/Rig-status), **templates** to fill them fast, **inheritance** so defaults flow down, **auto-tagging** from ingest paths, a **quality checker** to catch missing/mis-named data, **relationships** between assets, and a **naming assistant**. EP4 delivers all seven on an EAV model so custom fields stay SQL-queryable (and can later become EP2 facets).

### Locked design decisions
- **Storage:** EAV — a `metadata_fields` definition table + an `element_metadata(element_fk, field_key, value)` value table. Not a JSON blob.
- **Schema scope:** per-stack, typed fields (`text/number/choice/date/bool`), inherited down to lists/elements.
- **Full EP4:** all seven features, in three independently-shippable clusters.
- Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`.

### Dependencies
- **SP1** — DB, `get_connection(write=…)`, migration runner, column whitelisting.
- **SP2 / `ingestion_core.ingest_file`** — the ingest hook point for auto-tag and template application.
- **EP1** — `InspectorPanel` (EP3) / `EditElementDialog` surfaces where custom fields render (EP4 adds the custom-field section).

### Delivery clusters
- **4A — Schema core:** fields, EAV values, inheritance, editing UI.
- **4B — Templates & auto-tag:** templates + path-based rules applied at ingest.
- **4C — Rules & links:** quality checker + Health panel, naming assistant, relationships.

---

## 2. Goals / Non-Goals

### Goals
- Admin-defined typed custom fields per stack; per-element values via EAV.
- Inheritance: element override → list default → stack default → field default.
- Reusable metadata templates applied at ingest.
- Path-pattern auto-tag/auto-field rules at ingest.
- A quality checker (required fields, naming regex) surfaced in a Health panel.
- A naming assistant that validates/suggests names.
- Asset-to-asset relationship links shown in the inspector.

### Non-Goals (deferred)
- Exposing custom fields as EP2 facets/search → a later EP2 extension (schema here makes it possible).
- Cross-project/global schema sharing or import/export of schemas.
- Automated metadata *derivation* from pixel/AI analysis → EP7.
- Approval-workflow statuses (that's EP5, distinct from quality rules).

---

## 3. Detailed Design — Cluster 4A (Schema core)

### 3.1 Tables

```sql
CREATE TABLE metadata_fields (
    field_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    stack_fk    INTEGER NOT NULL,
    key         TEXT NOT NULL,               -- machine key, unique per stack
    label       TEXT NOT NULL,
    field_type  TEXT NOT NULL,               -- text|number|choice|date|bool
    choices_json TEXT,                        -- JSON array for 'choice'
    required    INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(stack_fk, key)
);

CREATE TABLE element_metadata (
    element_fk INTEGER NOT NULL,
    field_key  TEXT NOT NULL,
    value      TEXT,
    PRIMARY KEY (element_fk, field_key)
);

CREATE TABLE metadata_defaults (
    default_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type TEXT NOT NULL,                 -- 'stack' | 'list'
    scope_id   INTEGER NOT NULL,
    field_key  TEXT NOT NULL,
    value      TEXT,
    UNIQUE(scope_type, scope_id, field_key)
);
```

`element_metadata` values are stored as text and coerced by `field_type` on read/write. `field_type` and `choices_json` are validated at definition time (`ValueError` on unknown type / invalid choices).

### 3.2 DB API

```
create_metadata_field(stack_fk, key, label, field_type, choices=None, required=False, sort_order=0) -> int
get_metadata_fields(stack_fk) -> list[dict]
update_metadata_field(field_id, **fields)          # whitelisted
delete_metadata_field(field_id)                    # also clears element_metadata for that key
set_element_metadata(element_id, field_key, value) # validates against the field's type
get_element_metadata(element_id) -> dict           # only stored overrides
set_metadata_default(scope_type, scope_id, field_key, value)
get_effective_metadata(element_id) -> dict         # inheritance-resolved values for all stack fields
```

**Inheritance resolution** (`get_effective_metadata`): for each field of the element's stack, value = element override → nearest ancestor list default (walking `parent_list_fk` up) → stack default → `None`.

### 3.3 Editing UI

- A **Custom Fields** group added to `EditElementDialog` (dialogs.py:572) and the EP3 `InspectorPanel`: one widget per field (`text`→line edit, `number`→spin, `choice`→combo, `date`→date edit, `bool`→checkbox), pre-filled from `get_effective_metadata`, writing overrides via `set_element_metadata`. Fields not overridden show the inherited value as a placeholder/hint.
- A **Fields** admin manager (settings, admin-gated) to define/edit/reorder a stack's fields.

---

## 4. Detailed Design — Cluster 4B (Templates & auto-tag)

### 4.1 Tables

```sql
CREATE TABLE metadata_templates (
    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stack_fk    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    values_json TEXT NOT NULL                 -- {field_key: value, ..., "tags": "a,b"}
);

CREATE TABLE autotag_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    stack_fk    INTEGER,                       -- NULL = all stacks
    pattern     TEXT NOT NULL,
    match_type  TEXT NOT NULL,                 -- contains|glob|regex
    tags        TEXT,                          -- comma-joined tags to add
    field_values_json TEXT,                    -- {field_key: value}
    sort_order  INTEGER NOT NULL DEFAULT 0
);
```

### 4.2 API + ingest integration

```
create_metadata_template(stack_fk, name, values) -> int
get_metadata_templates(stack_fk) -> list[dict]
apply_template(element_id, template_id)            # writes field overrides + merges tags
create_autotag_rule(...) / get_autotag_rules(stack_fk) / delete_autotag_rule(id)
evaluate_autotag(source_path, stack_fk) -> {"tags": [...], "fields": {key: value}}
```

- `evaluate_autotag` matches each rule's `pattern` against `source_path` by `match_type` (`contains` = substring, `glob` = `fnmatch`, `regex` = `re.search`) and unions the resulting tags/fields (rule `sort_order` decides precedence on field conflicts).
- **Ingest hook:** `ingestion_core.ingest_file` calls `evaluate_autotag(source_path, stack_fk)` after path resolution and merges the derived tags into the element's tags and the derived fields into `element_metadata` before/after the DB insert. Caller-supplied tags win over rule tags on exact duplicates (union, deduped).
- **Ingest dialog template picker:** choosing a template pre-fills the ingest form and applies its values on creation.

---

## 5. Detailed Design — Cluster 4C (Rules & links)

### 5.1 Quality checker (F020)

```sql
CREATE TABLE quality_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    stack_fk    INTEGER,                       -- NULL = all
    kind        TEXT NOT NULL,                 -- required_field | naming_regex
    config_json TEXT NOT NULL                  -- {"field_key": "..."} | {"pattern": "..."}
);
```

`check_element_quality(element_id) -> list[dict]` evaluates the applicable rules and returns issues `{rule_id, kind, message}`:
- `required_field`: the field has no effective value → "Missing required field: <label>".
- `naming_regex`: `element.name` doesn't match `pattern` → "Name doesn't match convention".

A **Health panel** (`QDockWidget`, bottom, like History) lists per-list issue counts and a drill-down table; double-clicking an issue selects the offending element. `get_quality_summary(list_id) -> {"issues": N, ...}` powers the counts.

### 5.2 Naming assistant (F022)

`suggest_name(proposed, stack_fk) -> (ok: bool, suggestion: str|None)`: validates `proposed` against the stack's `naming_regex` rule (if any). When it fails, returns a best-effort corrected suggestion (e.g. lowercasing, replacing spaces with underscores, stripping invalid chars to satisfy the pattern where derivable). Surfaced as a non-blocking inline warning + one-click "Apply suggestion" in the ingest and rename dialogs.

### 5.3 Relationships (F021)

```sql
CREATE TABLE element_relationships (
    rel_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_element_fk   INTEGER NOT NULL,
    to_element_fk     INTEGER NOT NULL,
    rel_type          TEXT NOT NULL,           -- variant_of | derived_from | related
    UNIQUE(from_element_fk, to_element_fk, rel_type)
);
```

API: `add_relationship(from_id, to_id, rel_type)`, `get_relationships(element_id) -> list[dict]` (both directions), `remove_relationship(rel_id)`. An inspector **Related** section lists linked assets (click to navigate); a "Link selected…" action creates a relationship from the current selection.

---

## 6. Architecture & File Impact

| File | Change |
|---|---|
| `src/db_manager.py` | 7 tables + migrations; all field/EAV/default/template/autotag/quality/relationship API |
| `src/metadata_rules.py` (new) | Pure helpers: `evaluate_autotag`, `check_element_quality`, `suggest_name`, inheritance resolution (kept testable without Qt/DB where possible) |
| `src/ingestion_core.py` | `ingest_file` calls `evaluate_autotag` + template application |
| `src/ui/custom_fields_widget.py` (new) | Dynamic per-type field editor reused by dialog + inspector |
| `src/ui/dialogs.py` | Custom-fields section in `EditElementDialog`; naming-assistant warning in rename/ingest |
| `src/ui/inspector_panel.py` (EP3) | Custom Fields + Related sections |
| `src/ui/health_panel.py` (new) | Quality Health dock |
| `src/ui/settings_panel.py` | Admin managers: Fields, Templates, Auto-tag rules, Quality rules |
| `main.py` | Health dock + wiring |

Pure logic (`metadata_rules.py`) is separated from Qt/DB so rule evaluation is unit-testable in isolation.

---

## 7. Testing Strategy

- **Unit:**
  - Field CRUD + type/choices validation; delete clears EAV values.
  - `set/get_element_metadata` with type coercion; `get_effective_metadata` inheritance chain (element > list > stack).
  - Template create/apply merges fields + tags.
  - `evaluate_autotag` for contains/glob/regex; precedence on conflicts.
  - `check_element_quality` (required-missing, naming-fail) and `get_quality_summary`.
  - `suggest_name` returns ok for valid, a correction for invalid.
  - Relationship add/get(both directions)/remove; unique constraint.
  - Migrations create all 7 tables.
- **GUI (headless):** `CustomFieldsWidget` renders the correct widget per type and writes an override; Fields/Templates/Rules managers gate on admin; ingest dialog template picker applies values; Health panel lists issues and navigates; inspector Related section shows links.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| EAV values are untyped text | Coerce/validate on write against `field_type`; store canonical text; tests cover each type. |
| Inheritance chain cost per element | Resolve lazily (only when editing/inspecting one element); batch reads for the Health panel; walk is O(list depth), shallow in practice. |
| Auto-tag regex from user input could be slow/broken | Compile with a guard; on bad pattern, log and skip that rule (never fail ingest). |
| 7 tables + ingest hook is large | Clusters ship independently: 4A alone is useful; 4B/4C are separate; Health dock can be deferred within 4C. |
| Custom fields not yet searchable | Out of scope by design; EAV keeps a clean path to add EP2 facets later. |
| Deleting a field/stack orphans EAV rows | `delete_metadata_field` clears its `element_metadata`; stack delete cascades lists/elements already; add cleanup for defaults/fields in the same transaction. |

---

## 9. Deliverables Checklist
- [ ] `metadata_fields` + `element_metadata` + CRUD + type validation.
- [ ] `metadata_defaults` + `get_effective_metadata` inheritance.
- [ ] `CustomFieldsWidget` + editing in dialog & inspector; Fields admin manager.
- [ ] `metadata_templates` + apply + ingest picker; Templates admin manager.
- [ ] `autotag_rules` + `evaluate_autotag` + ingest hook; Auto-tag admin manager.
- [ ] `quality_rules` + `check_element_quality` + Health panel; Quality admin manager.
- [ ] `suggest_name` naming assistant in ingest/rename.
- [ ] `element_relationships` + inspector Related section.
- [ ] Unit + headless GUI tests green.

---

## 10. Follow-on
EP2 gains custom-field facets on top of the EAV model. EP5 review statuses complement (not replace) quality rules. EP7 can auto-populate custom fields from AI analysis.
