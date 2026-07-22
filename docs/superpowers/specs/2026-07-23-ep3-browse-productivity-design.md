# EP3 — Browse Productivity Shell — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F049 (command palette), F050 (spacebar quicklook), F051 (sticky inspector), F054 (onboarding checklist), F055 (layout presets), F056 (keyboard map/help overlay), F057 (accessibility), F058 (personalized start page), plus §7.7 progressive/skeleton loading.

---

## 1. Background & Motivation

StaX has a capable 3-pane shell (stacks | media | preview) with menus, a toolbar, docks, and a few shortcuts, but power-user ergonomics are thin: no command palette, no keyboard quicklook, no persistent editable inspector (metadata only appears in the transient Alt-hover popup), no layout presets, no accessibility controls, and a blank shell on launch. EP3 layers a productivity shell over the existing panes so routine curation is fast, keyboard-driven, and obvious — without disturbing the core navigation.

### Locked design decisions
- **Command palette** auto-harvests existing menu/toolbar `QAction`s + a small extra-command registry (no duplicated command list).
- **Sticky inspector** lives in the right pane, stacked **below the preview** (one combined context panel), reusing `MediaInfoPopup` field rendering.
- **Start page** ships **minimal now** (Recent / Favorites / Most-used); Assigned/In-review sections are deferred to EP5/EP8.
- **No new database tables** — layout preset, accessibility, and onboarding state persist in `Config`.
- Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`.

### Dependencies
- **EP1** — `set_element_rating` / `set_element_label` for inspector editing.
- **SP1** — DB; analytics "top-used" (insertion log) for the start page's Most-used (degrades gracefully if absent).
- **SP2** — async preview worker (skeletons cover its in-flight thumbnails).
- **SP6** — UI correctness fixes the inspector/quicklook build on.

### Delivery clusters (incremental)
- **3A — Interaction core:** command palette, spacebar quicklook, keyboard help overlay.
- **3B — Context & loading:** sticky inspector, skeleton loading + scroll retention.
- **3C — Shell polish (trimmable):** layout presets, accessibility, onboarding checklist, minimal start page.

---

## 2. Goals / Non-Goals

### Goals
- Ctrl+K command palette over all actions + jump targets.
- Spacebar quicklook overlay with prev/next navigation.
- A `?`/Help shortcut cheat-sheet.
- A persistent, editable inspector reflecting the current selection.
- Skeleton placeholders during preview generation + scroll-position retention.
- Layout presets, accessibility controls, an onboarding checklist, and a minimal start page.

### Non-Goals (deferred)
- "Assigned" / "In-review" start-page sections → EP5 (review) + EP8 (collaboration/tasks).
- New review/annotation surfaces → EP5.
- Full WCAG conformance audit; EP3 ships pragmatic contrast/scale/focus controls, not a certification.
- Theme authoring beyond the high-contrast toggle.

---

## 3. Detailed Design

### 3.1 Command palette (3A)

`CommandPalette(QDialog)` opened by **Ctrl+K** (a `QShortcut` on `MainWindow`):
- **Harvesting:** walk `MainWindow.menuBar()` actions (recursively into submenus) and `self.toolbar.actions()`, collecting each enabled, text-bearing `QAction` into `(label, action)` entries. De-duplicate by `action` identity.
- **Registry:** a `CommandRegistry` holds extra entries `(label, callable)` — e.g. "Go to stack: <name>", "Go to list: <name>", "Run saved search: <name>" — populated from the DB on open.
- **Filter:** a line edit fuzzy-filters entries (subsequence match + `difflib` ratio for ranking); ↑/↓ move, Enter runs (`action.trigger()` or `callable()`), Esc closes.
- Rebuilt on each open so it always reflects current actions/state.

### 3.2 Spacebar quicklook (3A)

`QuickLookOverlay(QWidget, Qt.FramelessWindowHint)`:
- Triggered by **Space** when a gallery/table item has focus (event filter on the views).
- Shows the large preview of the selected element — image, animated GIF (`QMovie`), or a video-preview frame — resolved via the existing preview-path helpers.
- **Space** or **Esc** closes; **←/→** advance to the previous/next item in the current result set (updates the overlay and the underlying selection).

### 3.3 Keyboard help overlay (3A)

`ShortcutHelpOverlay(QDialog)` opened by **`?`** (or Help → Keyboard Shortcuts):
- Lists shortcuts harvested from each `QAction.shortcut()` (label + key) plus a static block for the EP3 keys (Ctrl+K palette, Space quicklook, ? help).
- Grouped by menu; read-only; Esc closes.

### 3.4 Sticky inspector (3B)

`InspectorPanel(QWidget)` placed in the right pane **below** the `VideoPlayerWidget` (the pane becomes a vertical splitter: preview on top, inspector below):
- Reflects the current selection (connected to the media view's selection-changed signal).
- **Editable fields:** name + comment + tags → `db.update_element(element_id, ...)`; rating → `db.set_element_rating`; label → `db.set_element_label` (EP1). Edits commit on focus-out / Enter and refresh the item badge in place.
- **Read-only fields:** type, format, frame range, size, hard/soft path — rendered with `MediaInfoPopup`'s existing formatting helpers (extracted/shared, not duplicated).
- Empty selection → a compact "No selection" state.

### 3.5 Progressive/skeleton loading + scroll retention (3B)

- **Skeletons:** while a thumbnail is still being generated (SP2's async worker hasn't emitted `preview_ready`), the gallery shows a neutral skeleton placeholder tile; it swaps to the real thumbnail on `preview_ready`. Implemented as the default item pixmap + a "loading" flag cleared by the existing `on_preview_ready` slot.
- **Scroll retention:** capture the gallery/table scrollbar position before opening quicklook / switching to the inspector detail and restore it on return, so users don't lose their place.

### 3.6 Layout presets (3C)

`LayoutManager` (a small helper on `MainWindow`):
- Presets: **Browse** (nav + media + preview), **Review** (media + large preview/inspector, nav collapsed), **Ingest** (media + history dock), **Curation** (nav + media wide, facet drawer open, preview narrow).
- Each preset sets `main_splitter` sizes, right-pane split, and dock visibility. Applied from **View → Layout**; the last-used preset name persists in `Config` and is restored on launch.

### 3.7 Accessibility (3C)

An **Accessibility** section in settings, persisted in `Config`:
- **High contrast** toggle → swaps to a high-contrast palette/QSS.
- **Text scale** (100–150%) → applies an app font point-size multiplier.
- **Focus assist** → stronger focus-ring styling via QSS.
Applied globally on change and at startup.

### 3.8 Onboarding checklist (3C)

`OnboardingChecklist(QWidget)` shown on first run (dismissible), re-openable from Help:
- Steps: *Create a stack*, *Ingest files*, *Insert into Nuke* (each with a one-click action and a done-check derived from DB state, e.g. stacks exist / elements exist / an insertion has been logged).
- Completion + dismissal flags stored in `Config` (`onboarding_dismissed`, per-step done is derived, not stored).

### 3.9 Minimal start page (3C)

`StartPage(QWidget)` shown on launch / when no list is selected:
- **Recent:** recently added elements (by `created_at`) — a new lightweight `db.get_recent_elements(limit)`.
- **Favorites:** the current user's favorites (existing `get_favorites`).
- **Most-used:** SP1 analytics top-used (`get_top_inserted_elements`); if unavailable/empty, the section hides.
- Cards are clickable → select the element / open its list. "Assigned"/"In-review" are not rendered yet (EP5/EP8).

### 3.10 State persistence
All EP3 preferences use `Config` keys: `layout_preset`, `a11y_high_contrast`, `a11y_text_scale`, `a11y_focus_assist`, `onboarding_dismissed`. No schema changes.

---

## 4. Architecture & File Impact

| File | Change |
|---|---|
| `src/ui/command_palette.py` (new) | `CommandPalette` + `CommandRegistry` |
| `src/ui/quicklook_overlay.py` (new) | `QuickLookOverlay` |
| `src/ui/shortcut_help_overlay.py` (new) | `ShortcutHelpOverlay` |
| `src/ui/inspector_panel.py` (new) | `InspectorPanel` |
| `src/ui/onboarding_checklist.py` (new) | `OnboardingChecklist` |
| `src/ui/start_page.py` (new) | `StartPage` |
| `src/ui/layout_manager.py` (new) | `LayoutManager` presets |
| `main.py` | Ctrl+K/`?` shortcuts, right-pane vertical split for inspector, layout menu, a11y application, start-page/onboarding show logic |
| `src/db_manager.py` | `get_recent_elements(limit)` |
| `src/ui/media_display_widget.py` | Space event filter → quicklook; skeleton flag; scroll retention |
| `src/ui/settings_panel.py` | Accessibility section |
| `src/ui/media_info_popup.py` | Extract shared field-formatting helpers reused by `InspectorPanel` |

Each new surface is its own file (single responsibility); shared metadata formatting is extracted once (DRY, and it pays down part of audit L10).

---

## 5. Testing Strategy

- **Unit (`tests/unit`):**
  - Command harvesting collects the expected `(label, action)` set from a stub menu/toolbar; fuzzy filter ranks an exact/subsequence match first.
  - `get_recent_elements` returns newest-first, limited.
  - Accessibility text-scale computes the right point size; layout-preset config round-trips; onboarding step-done derives correctly from DB state.
- **GUI (`tests/gui`, headless):**
  - Ctrl+K opens the palette; Enter triggers the selected action (spy on a stub action).
  - Space opens `QuickLookOverlay` for the selected item; Esc closes; ←/→ change the item.
  - `InspectorPanel` shows the selection and an edit writes through (`set_element_rating` called).
  - Selecting a layout preset produces the expected splitter/dock visibility.
  - `StartPage` renders Recent/Favorites sections (Most-used hidden when empty).

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Command harvesting picks up separators / empty actions | Skip actions with no text or that are separators; de-dup by identity. |
| Right-pane vertical split crowds preview on small screens | Inspector is collapsible; the Review preset gives it more room; remembers split sizes. |
| Skeletons depend on SP2's async worker signals | If SP2 isn't present, skeletons simply never show (thumbnails load synchronously as today) — no regression; wire to the existing `on_preview_ready` slot. |
| Global text-scale/high-contrast fights the existing dark QSS | Apply a11y as an additive QSS layer + font multiplier; test both light/dark base. |
| Start-page Most-used depends on SP1 analytics | Section hides when the analytics call is unavailable or returns empty. |
| Scope (10 features) | 3A ships alone; 3B and 3C are separately committable; 3C (onboarding + start page) is explicitly trimmable. |

---

## 7. Deliverables Checklist
- [ ] Command palette (Ctrl+K) — harvest + registry + fuzzy run.
- [ ] Spacebar quicklook overlay (+ prev/next, Esc).
- [ ] Keyboard help overlay (`?`).
- [ ] Sticky inspector (editable rating/label/tags/comment) in the right pane.
- [ ] Skeleton placeholders + scroll retention.
- [ ] Layout presets (Browse/Review/Ingest/Curation) persisted.
- [ ] Accessibility (high-contrast/text-scale/focus) persisted.
- [ ] Onboarding checklist (first-run, dismissible).
- [ ] Minimal start page (Recent/Favorites/Most-used).
- [ ] `get_recent_elements` + shared metadata-format helpers.
- [ ] Unit + headless GUI tests green.

---

## 8. Follow-on
EP5 (Review) fills the start page's Assigned/In-review sections and adds review-mode layout content. EP7's AI actions register into the same command palette. The extracted metadata-format helpers reduce audit L10 duplication that SP8 also targets.
