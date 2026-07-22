# EP8 — Team Collaboration (metadata sync first) — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F041 (team metadata sync over local media), F042 (granular role permissions), F043 (activity feed & audit events). **Defers with a documented follow-on:** F044 (Kitsu), F045 (Ftrack), F046 (Flow/ShotGrid), F047 (additional DCC connectors), F048 (integration-manager UI).

---

## 1. Background & Motivation

StaX teams on a LAN **already share metadata today**: `STOCK_DB` points every instance at one network-shared SQLite file, and `src/file_lock.py` serialises writes with an advisory lock. So "collaboration" for the on-site case is a solved problem — the value EP8 must add is for the cases the shared file does **not** cover:

- **(a) Multi-site / offline members** — a freelancer or a second studio with no route to the network share cannot see the team's metadata. They need a way to receive a stack/list's elements + metadata + previews as a **portable bundle**, import it, and later send changes back, with **conflict handling by timestamp**.
- **(b) Auditability** — the shared DB records *state* but not *history*: who deprecated an element, who changed a role, who deleted an asset. Teams need an **activity/audit log** and a panel to read it.
- **(c) Access control granularity** — the current model is binary (`users.role` is `admin` or `user`; `main.check_admin_permission` is the only gate). Studios want a **role → permission matrix** (a "reviewer" who can edit metadata but not delete; an "ingestor" who can ingest but not manage users).

EP8 delivers all three on **stdlib only** (`json`, `zipfile`, `shutil`, `difflib`-free) — no real-time cloud sync, no new dependency. It also ships a small, named **connector interface** so the deferred PM/DCC bridges (Kitsu/Ftrack/Flow) can be added later as subclasses without reworking EP8.

### Locked design decisions
- **Scope:** build **F041/F042/F043 now**; **defer** F044–F048 (see §10) but ship a `CollaborationConnector` ABC + registry as the extension seam.
- **No real-time cloud sync.** Sync is an explicit **export → transport → import** of a portable `.staxbundle` (a zip of JSON + copied preview files).
- **Conflict handling by timestamp.** Import merges element-by-element (matched by name within the target list); the newer `updated_at` wins. A new `elements.updated_at` column (migration) is bumped on every `update_element`.
- **Roles are data, not code.** A `roles` + `role_permissions` matrix layered *on top of* the existing `users.role` string; `admin` implies every permission (keeps SP4 hardening and the existing `check_admin_permission` gate valid).
- **Audit is append-only.** `activity_log` rows are written on ingest, delete, metadata edit, role change, export and import.
- **Dependency-light tests:** export/import round-trip on `tmp_path`, role/permission checks, activity-log writes — **no network, no Qt for the pure layers**.
- Windows + Linux; flat imports; `logging` not `print`.

### Dependencies
- **SP1** — DB consolidation: `get_connection(...)`, the idempotent migration runner, and column whitelisting. If executing before SP1, use plain `get_connection()` (the verified current signature) — the plan's code does exactly this.
- **SP4** — auth/roles hardening: EP8's granular roles **build directly on** SP4's user/session model. SP4 owns password hashing and session lifetime; EP8 owns the role→permission matrix and enforcement layer. Coordinate: the permission constants (§3.1) are the shared contract.
- **EP4** — metadata edits (`set_element_metadata`, custom-field writes) are **audited events**: EP8's `log_activity` is called from EP4's edit path (and from the core `update_element`).
- **SP0** — fixtures: all tests use the `stax_db` temp-DB fixture and headless-Qt (`offscreen`).

### Delivery clusters
- **8A — Granular roles (F042):** `permissions.py` + `roles`/`role_permissions` tables + `has_permission` + `check_permission` gate + admin role-matrix UI.
- **8B — Activity feed / audit (F043):** `activity_log` table + `log_activity`/`get_activity` + mutation hooks + Activity dock with filters.
- **8C — Team metadata sync (F041):** `updated_at` column + `metadata_bundle` export/import (stdlib zip) with timestamp conflict handling + `CollaborationConnector` stub + Sync UI.

---

## 2. Goals / Non-Goals

### Goals
- A named, typed permission set (`can_ingest`, `can_delete`, `can_edit_metadata`, `can_manage_users`, `can_manage_schema`) stored in tables, seeded with built-in roles.
- `has_permission(username, permission) -> bool` at the DB layer and `MainWindow.check_permission(permission, action_name)` at the UI layer, with `admin` implying all.
- An append-only `activity_log(actor, action, target_type, target_id, detail, at)` written on key mutations, and an Activity dock that lists recent events with actor/action filters.
- Export a stack/list's elements + metadata + previews to a portable `.staxbundle`, and import/merge it on another instance with conflict resolution by newer `updated_at`.
- A `CollaborationConnector` ABC + registry so future bridges plug in without touching EP8 core.

### Non-Goals (deferred)
- **Live PM/DCC bridges** — Kitsu (F044), Ftrack (F045), Flow/ShotGrid (F046), extra DCC connectors (F047), integration-manager UI (F048). Documented as follow-on in §10; the connector ABC is their seam.
- **Real-time / cloud sync**, presence, live cursors, or a sync server. Sync is explicit bundle export/import only.
- **Field-level three-way merge.** Conflict resolution is whole-element, newest-timestamp-wins (with a `skipped`/`updated` report), not per-field CRDT.
- **New auth mechanics** (SSO, password policy) — SP4 owns those; EP8 consumes them.
- **Binary media re-transcode** on import — previews are copied verbatim; source media is *not* shipped in the bundle (paths + metadata only, plus preview thumbnails).

---

## 3. Detailed Design — Cluster 8A (Granular roles, F042)

### 3.1 Permission contract (pure module)

`src/permissions.py` is Qt-free and DB-free so it is unit-testable in isolation and is the **shared contract with SP4**:

```python
PERMISSIONS = (
    "can_ingest",
    "can_delete",
    "can_edit_metadata",
    "can_manage_users",
    "can_manage_schema",
)

# built-in role -> granted permissions
BUILTIN_ROLES = {
    "admin":    set(PERMISSIONS),                                  # implies all
    "user":     {"can_ingest", "can_edit_metadata"},
    "reviewer": {"can_edit_metadata"},
    "ingestor": {"can_ingest"},
    "viewer":   set(),
}
```

Helpers: `is_valid_permission(p) -> bool`, `default_permissions_for(role_name) -> set`.

### 3.2 Tables

```sql
CREATE TABLE roles (
    role_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,          -- matches users.role string
    label      TEXT,
    is_builtin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE role_permissions (
    role_fk    INTEGER NOT NULL,
    permission TEXT NOT NULL,                  -- one of PERMISSIONS
    PRIMARY KEY (role_fk, permission),
    FOREIGN KEY (role_fk) REFERENCES roles(role_id) ON DELETE CASCADE
);
```

The existing `users.role` **text** column stays the join key (by name). We do **not** ALTER its `CHECK(role IN ('admin','user'))` constraint (SQLite can't cheaply drop a CHECK); instead new roles are additive rows in `roles`, and `update_user(role=…)` continues to write the string. Built-in roles are seeded idempotently from `BUILTIN_ROLES` on migration.

### 3.3 DB API

```
seed_builtin_roles()                                  # idempotent; called from schema + migration
create_role(name, label=None, permissions=None) -> int
get_roles() -> list[dict]                              # each: {role_id,name,label,is_builtin,permissions:[...]}
set_role_permissions(role_name, permissions)          # replace the set for a role
get_role_permissions(role_name) -> set
has_permission(username, permission) -> bool          # admin role -> always True
delete_role(role_name)                                # built-in roles refuse deletion
```

`has_permission` resolves: look up the user's `role` string → if `admin`, return `True` → else test membership in `get_role_permissions(role)`. Unknown user / unknown role → `False`.

### 3.4 Enforcement layer

`MainWindow.check_permission(permission, action_name="this action") -> bool` mirrors the existing `check_admin_permission` (main.py:527): if no `current_user`, prompt login; else `db.has_permission(current_user["username"], permission)`; on failure show the same styled "Permission Denied" dialog. Call sites (ingest button, delete action, metadata edit, user management) switch from `check_admin_permission()` to the specific `check_permission("can_…")`. `check_admin_permission` is retained (admin-only surfaces like schema/user management still use it, and `admin` passes every `check_permission` anyway).

### 3.5 Admin role-matrix UI

A **Roles** admin tab in `SettingsPanel` (admin-gated exactly like the Security Admin tab): a `QTableWidget` with roles as rows and the five permissions as checkbox columns; editing a cell calls `set_role_permissions`; an "Add role…" control calls `create_role`. Built-in roles' rows are read-only for structure (name/deletion) but their permission cells remain editable so a studio can retune `reviewer`. Every save writes an `activity_log` `role_change` event (§4).

---

## 4. Detailed Design — Cluster 8B (Activity feed / audit, F043)

### 4.1 Table

```sql
CREATE TABLE activity_log (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor       TEXT,                          -- username, or 'system'
    action      TEXT NOT NULL,                 -- ingest|delete|metadata_edit|role_change|export|import
    target_type TEXT,                          -- element|stack|list|user|role|bundle
    target_id   INTEGER,
    detail      TEXT,                          -- short human string or JSON
    at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_activity_at     ON activity_log(at);
CREATE INDEX idx_activity_action ON activity_log(action);
```

### 4.2 API

```
log_activity(actor, action, target_type=None, target_id=None, detail=None) -> int
get_activity(limit=100, action=None, actor=None, target_type=None) -> list[dict]   # newest first
```

`get_activity` builds a parameterized `WHERE` from whichever of `action/actor/target_type` are non-None (code-literal column names, SP1 whitelisting pattern), ordered `at DESC, activity_id DESC`, `LIMIT ?`.

### 4.3 Mutation hooks

Audit is written at the mutation source so it is captured regardless of caller:
- **delete** — `delete_element(element_id, actor=None)` gains an optional `actor`; when set, writes a `delete`/`element` row before removing the row.
- **ingest** — `log_ingestion(...)` gains an optional `actor`; on `status == "success"` it also writes an `ingest`/`element` activity row (the existing `ingestion_history` write is unchanged — activity_log is the *cross-cutting* feed, ingestion_history stays ingest-specific).
- **metadata edit** — a helper `record_metadata_edit(actor, element_id, detail)` is called from `update_element`'s callers and from EP4's `set_element_metadata` (EP4 dependency). To keep it caller-agnostic, `update_element(element_id, _actor=None, **kwargs)` writes a `metadata_edit` row when `_actor` is supplied.
- **role change** — the Roles UI (§3.5) calls `log_activity(actor, "role_change", "role", role_id, detail)`.
- **export/import** — the sync layer (§5) writes `export`/`import` `bundle` rows with counts.

`actor` is threaded from `MainWindow.current_user["username"]` at the call sites; pure/headless code passes `actor="system"` or omits it (no row written), keeping unit tests deterministic.

### 4.4 Activity dock

`src/ui/activity_panel.py` — `ActivityPanel(QDockWidget)` (bottom dock, like the History panel): a `QTableWidget` (When / Actor / Action / Target / Detail) plus two `QComboBox` filters (Action, Actor) and a Refresh button; `refresh()` calls `get_activity(...)` with the selected filters. Wired in `main.py` as a dockable panel next to History.

---

## 5. Detailed Design — Cluster 8C (Team metadata sync, F041)

### 5.1 `updated_at` for conflict resolution

Migration adds `elements.updated_at TIMESTAMP` (defaulting to `created_at` for existing rows). `update_element` sets `updated_at = CURRENT_TIMESTAMP` on every write. This is the timestamp the merge compares.

### 5.2 Bundle format (`.staxbundle` = a zip)

A portable bundle is a zip written with stdlib `zipfile`:

```
manifest.json     {"bundle_version":1,"source_site":<str>,"exported_at":<iso>,
                   "scope":{"type":"list","id":<n>,"name":<str>},"element_count":<n>}
elements.json     [ {name,type,format,frame_range,comment,tags,is_deprecated,
                     updated_at,created_at,preview_file:<rel path|null>, ...}, ... ]
previews/…        preview image/gif files referenced by elements.json
```

Only metadata + preview thumbnails travel — **not** the source media. Import rewrites nothing on disk except copying previews into the local previews dir.

### 5.3 Pure sync module

`src/sync/metadata_bundle.py` (stdlib `json`, `zipfile`, `os`, `shutil`, `datetime`):

```
export_list_bundle(db, list_id, out_path, source_site="", include_previews=True) -> str
    # returns out_path; serializes the list's elements + metadata + previews into the zip

read_manifest(bundle_path) -> dict

import_bundle(db, bundle_path, target_list_id, conflict="timestamp",
              previews_dir=None) -> dict
    # returns {"added": n, "updated": n, "skipped": n}
```

**Merge rule** (`conflict="timestamp"`): for each element in the bundle, match an existing element in `target_list_id` by `name`.
- No match → **add** (create element with bundle metadata; copy its preview).
- Match, bundle `updated_at` **newer** → **update** the local element's metadata (and preview).
- Match, bundle `updated_at` **older or equal** → **skip**.

The function is pure Python over the `db` object — fully round-trippable under `tmp_path` with no network and no Qt.

### 5.4 Connector interface stub (seam for F044–F047)

`src/sync/connector.py` — the named extension point; **ships no live bridge**:

```python
class CollaborationConnector(object):
    """Base class for external collaboration bridges (Kitsu/Ftrack/Flow/DCC).
    EP8 ships only the local-bundle path; subclasses are follow-on work."""
    key = "base"
    label = "Base Connector"

    def is_available(self):        # env/config present?
        return False
    def capabilities(self):        # subset of {"push","pull","status","notes"}
        return set()
    def push(self, payload):       raise NotImplementedError
    def pull(self):                raise NotImplementedError

# registry
def register_connector(cls): ...
def get_connectors() -> list          # instances
```

EP8 registers exactly one concrete connector — `LocalBundleConnector` — wrapping §5.3 (`capabilities() == {"push","pull"}` via export/import). Kitsu/Ftrack/Flow/DCC connectors are documented stubs (§10), each a future `CollaborationConnector` subclass; nothing in EP8 imports a third-party SDK.

### 5.5 Sync UI

A **Sync** admin tab in `SettingsPanel`: an "Export list to bundle…" action (list picker + file save dialog → `export_list_bundle`, writes an `export` activity row) and an "Import bundle…" action (file open + target-list picker → `import_bundle`, shows the `{added,updated,skipped}` summary, writes an `import` activity row). A read-only **Connectors** list shows `get_connectors()` with availability — the deferred bridges appear here disabled once their stubs are registered.

---

## 6. Architecture & File Impact

| File | Change |
|---|---|
| `src/permissions.py` (new) | Pure permission constants + built-in role matrix + validators |
| `src/db_manager.py` | 3 tables (`roles`, `role_permissions`, `activity_log`) + `updated_at` migration; roles/permissions API; `has_permission`; `log_activity`/`get_activity`; audit hooks in `delete_element`/`log_ingestion`/`update_element` |
| `src/sync/metadata_bundle.py` (new) | Pure `export_list_bundle` / `import_bundle` / `read_manifest` (stdlib zip/json) |
| `src/sync/connector.py` (new) | `CollaborationConnector` ABC + registry + `LocalBundleConnector` |
| `src/sync/__init__.py` (new) | Package marker |
| `src/ui/activity_panel.py` (new) | `ActivityPanel` dock with filters |
| `src/ui/settings_panel.py` | Admin **Roles**, **Sync** tabs (role matrix, export/import, connectors list) |
| `main.py` | `check_permission`; Activity dock wiring; thread `actor` into audited call sites |

Pure layers (`permissions.py`, `metadata_bundle.py`) are Qt-free and DB-light so they unit-test without a display or a network.

---

## 7. Testing Strategy

- **Unit (no Qt, no network):**
  - `permissions`: `PERMISSIONS`/`BUILTIN_ROLES` consistency; `default_permissions_for`; `is_valid_permission`.
  - Roles: `seed_builtin_roles` idempotent; `create_role`/`get_roles`/`set_role_permissions`/`get_role_permissions`; `delete_role` refuses built-ins.
  - `has_permission`: admin→all; per-role membership; unknown user/role→False.
  - `activity_log`: `log_activity` write; `get_activity` newest-first + action/actor/target filters + limit.
  - Audit hooks: `delete_element(actor=…)`, `log_ingestion(actor=…, status="success")`, `update_element(_actor=…)` each append the expected row; omitting the actor writes nothing.
  - `updated_at`: migration adds column; `update_element` bumps it.
  - Bundle **round-trip** on `tmp_path`: export a seeded list → new bundle file exists with `manifest.json`/`elements.json`; import into a fresh list adds all; re-import skips (same timestamp); import after a newer bundle edit updates; older bundle skips. Assert `{added,updated,skipped}` counts.
  - Connector registry: `LocalBundleConnector.capabilities() == {"push","pull"}`; `get_connectors()` returns it; base `is_available()` False.
- **GUI (headless offscreen):**
  - `ActivityPanel.refresh()` lists rows and filters by action.
  - Roles tab renders the matrix, gates add/edit controls on admin, and `set_role_permissions` persists a toggled cell.
  - Sync tab export writes a bundle file and an `export` activity row; import shows a summary.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `users.role` CHECK constraint blocks new role names | Keep `admin`/`user` writable as today; new roles are additive `roles` rows joined by name — enforcement reads `role_permissions`, not the CHECK. Document that a stricter SP4 migration can widen the CHECK later. |
| Audit hooks change hot method signatures | New params are **optional and keyword-only-ish** (`actor=None`, `_actor=None`); omitting them preserves current behavior and current tests, so nothing breaks when a caller hasn't been threaded yet. |
| Timestamp merge loses concurrent edits | Merge is newest-wins with an explicit `skipped`/`updated` **report** the UI surfaces; not silent. Field-level merge is a documented non-goal; `updated_at` gives a deterministic, testable rule. |
| Bundle previews bloat the zip | `include_previews` is a flag; only preview thumbnails (not source media) travel; large libraries export per-list, not whole-DB. |
| Connector stub tempts a premature live bridge | ABC ships with `is_available()==False` and no SDK import; §10 records the deferral rationale so a reviewer can gate any real bridge behind its own EP. |
| Activity log grows unbounded on the shared DB | Append-only with indexed `at`; `get_activity` is always `LIMIT`-bounded; a future retention/prune job is noted in §10 (not blocking). |
| Running before SP1 (no `write=` kwarg / migration runner) | Plan code uses plain `get_connection()` (verified current signature) and the `CREATE TABLE IF NOT EXISTS` idempotent pattern already used by `_apply_migrations`. |

---

## 9. Deliverables Checklist
- [ ] `permissions.py` (constants + built-in matrix + validators) with unit tests.
- [ ] `roles` + `role_permissions` tables + `seed_builtin_roles` + roles/permissions CRUD.
- [ ] `has_permission` + `MainWindow.check_permission` enforcement; audited call sites.
- [ ] Admin **Roles** matrix UI (admin-gated) writing `role_change` events.
- [ ] `activity_log` table + `log_activity`/`get_activity` (filters + limit).
- [ ] Audit hooks in `delete_element` / `log_ingestion` / `update_element`.
- [ ] `ActivityPanel` dock with Action/Actor filters, wired in `main.py`.
- [ ] `elements.updated_at` migration + `update_element` bump.
- [ ] `metadata_bundle.export_list_bundle` / `import_bundle` / `read_manifest` (stdlib).
- [ ] `CollaborationConnector` ABC + registry + `LocalBundleConnector`.
- [ ] Admin **Sync** tab (export/import + connectors list) writing `export`/`import` events.
- [ ] Unit + headless GUI tests green.

---

## 10. Follow-on (deferred integrations — rationale)

EP8 deliberately ships **no live external bridge**. Rationale: each PM/DCC integration carries a heavy third-party SDK, its own auth/secret handling, and a distinct data model — bundling any one of them into EP8 would (a) add a non-stdlib dependency the program has not yet approved, (b) blur EP8's testable, network-free boundary, and (c) couple three unrelated release cadences. Instead EP8 ships the **`CollaborationConnector` seam** so each becomes an isolated, independently-reviewable EP:

- **F044 — Kitsu bridge:** future `KitsuConnector(CollaborationConnector)` mapping stacks/lists ↔ Kitsu projects/shots; publish/status push. Needs the `gazu` SDK + host/token config → its own EP.
- **F045 — Ftrack bridge:** `FtrackConnector` for task-status + notes sync via `ftrack-python-api`.
- **F046 — Flow/ShotGrid bridge:** `FlowConnector` for project context + version sync via `shotgun-api3`.
- **F047 — Additional DCC connectors (Blender/Houdini/Unreal/Resolve):** "send to DCC" actions; extends the existing `nuke_bridge` pattern, not the collaboration connector, but registers capabilities through the same registry for a unified Integrations surface.
- **F048 — Integration-manager UI:** the read-only **Connectors** list shipped in §5.5 is the stub; the full manager (enable/configure/test each connector, store secrets) lands once ≥1 live bridge exists.

Retention/pruning of `activity_log`, and field-level (three-way) metadata merge, are also recorded here as later enhancements on top of EP8's foundation.
