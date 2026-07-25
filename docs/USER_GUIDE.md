<!-- markdownlint-disable MD013 -->
# StaX — Quick User Guide

A practical walkthrough of everyday StaX workflows, with a focus on the new
**local AI discovery** features. For architecture and contributor docs see
[`CLAUDE.md`](../CLAUDE.md) and [`STAX_AUDIT_REPORT.md`](../STAX_AUDIT_REPORT.md).

> **Platforms:** Windows & Linux · **Python:** 3.9+ · **UI:** PySide2 (Qt5)

---

## 1. Concepts in 30 seconds

StaX organizes everything in three levels:

```
Stack  →  List (nestable)  →  Element
(project/    (folder/           (a clip, image sequence,
 library)     collection)        3D asset, or Nuke toolset)
```

- **Stacks** are top-level libraries.
- **Lists** group Elements and can nest into sub-lists.
- **Elements** are the actual assets, with previews, metadata, ratings, tags, and labels.

---

## 2. Install & launch

```powershell
# Clone (submodules include the bundled 3D viewer)
git clone --recurse-submodules https://github.com/aramadan0096/Stax.git
cd Stax

# Install libraries into a portable lib/ + .venv
.\tools\install_libs_requirements_uv.ps1

# Download FFmpeg (first run only) and start the app
.\tools\run_standalone.ps1
```

On Linux use the equivalent `tools/*.sh` scripts (`build.sh`, `run_standalone.sh`).

> **Harmless startup message:** on launch you may see a block that ends with
> `A module that was compiled using NumPy 1.x ...` and a short `Traceback`.
> This is a **cosmetic NumPy notice** from the bundled Qt — the app runs
> normally. Ignore it.

---

## 3. Ingesting assets

1. **Ingest files** or **Ingest library** from the toolbar (requires the
   `can_ingest` permission).
2. StaX auto-detects **image sequences**, discovers frame ranges, and extracts
   metadata.
3. Choose **hard copy** (copied into the managed repository) or **soft copy**
   (a reference link to the original location).
4. Previews (thumbnail / GIF / video) are generated **in the background** — the
   UI stays responsive.

**Automation (optional):**

- **Watch-folders** poll a directory and ingest new files automatically.
- **Ingest recipes** apply a saved set of options (target list, metadata
  template, proxy profile) to an ingest.
- **Duplicate policies** decide what happens when an incoming file matches an
  existing asset (skip / allow / variant).
- A durable **job queue** tracks each ingest with retry, so a failure doesn't
  lose work.

---

## 4. Browsing & curating

- **Start page** surfaces **Recent**, **Favorites**, and **Most-used** assets
  when nothing is selected.
- **Gallery** and **table** views; the table adds Rating and Label columns.
- **Ratings** (0–5 stars) and **color labels** — set them inline via hover
  quick-edit on a grid tile, or in the inspector.
- **Favorites** and **playlists** for personal collections.
- **Multi-select action tray**: select many assets and apply an action
  (add to favorites, tag, label, etc.) in one go.
- **Inspector** (right pane) shows and edits metadata, custom fields, and
  related assets. Editing metadata requires the `can_edit_metadata` permission.

---

## 5. Search & discovery (non-AI)

- **Facets**: filter by type, tags, rating, label, and more. Facets are
  tri-state (include / exclude / ignore) so you can build negative filters.
- **Filter chips** show the active filter set and the live result count.
- **Saved searches** (personal) and **smart collections** (shared) live in the
  left nav and re-run their filter on click.
- **Synonyms**, **"did-you-mean"** correction, and a **recent-search**
  autocomplete make text search more forgiving.

---

## 6. AI Discovery

StaX includes an **entirely local** AI layer for finding assets by meaning,
by example, and by color. **No cloud, no API, nothing leaves your machine** —
inference runs on CPU via a downloaded CLIP model, and embeddings are stored in
your local SQLite database.

### 6.1 What you get

| Feature | What it does | Needs the AI model? |
|---|---|---|
| **Semantic (text) search** | Type natural language ("golden-hour city skyline") and rank assets by meaning, across all lists | Yes |
| **Visual (image) search** † | Find assets visually similar to a reference image | Yes |
| **Find similar** | Right-click an asset → find assets like it | Yes |
| **Auto-tag suggestions** | Right-click → **Suggest tags** → a ranked shortlist from your tag vocabulary, which **you** approve | Yes |
| **Color / palette search** | Find assets by dominant color (palette button, or a color picker) | **No — works without the model** |

The model used is **CLIP ViT-B/32**, run locally through **onnxruntime (CPU)**.

> † **Visual (image) search** is implemented and wired to a drag-and-drop
> zone, but that zone is hidden in the current build (no on-screen reveal
> control yet), so there is no user trigger for it right now. Semantic,
> find-similar, auto-tag, and color search are all reachable from the UI.

### 6.2 The model (cached in the repo)

The CLIP model ships **cached in the repo** at
`weights/clip-vit-b32-onnx/` (uint8-quantized ONNX, ~150 MB total), so AI works
out of the box — **Settings → AI** should already read *"AI model: available"*.

If the weights are ever missing (fresh checkout without them, or you cleaned the
folder), re-fetch them — downloaded once and SHA-256 verified:

```powershell
python -m tools.download_clip_model
```

- Files land in `weights/clip-vit-b32-onnx/` by default; override with the
  `STAX_AI_MODEL_DIR` environment variable.
- If `onnxruntime` or the model files are missing, StaX **degrades gracefully**:
  every AI action simply returns no results instead of erroring, and color
  search keeps working.
- Model details and attribution: [`weights/README.md`](../weights/README.md).

### 6.3 Indexing (how assets become searchable)

AI search works over **embeddings** — one per asset per model.

- **At ingest:** new assets are indexed automatically on a background worker
  (color signature always; AI embedding when the model is available).
- **Backfill existing assets:** open **Settings → AI → Reindex library**. This
  enqueues every asset that is missing an embedding for the current model. The
  status line shows how many assets are still awaiting indexing.

### 6.4 Using it

- **Semantic search:** toggle the **AI** button in the search bar (it's enabled
  once the model is installed), then type a description and search. Results are
  ranked by similarity and shown on the standard result surface; they compose
  with any active facet filters.
- **Find similar / Suggest tags:** right-click any asset.
- **Color search:** click the **🎨 palette** button to pick a color and rank
  assets by dominant hue. Always available — no model required.
- **Visual (image) search:** implemented but not yet surfaced in the UI (see the
  † note above).

### 6.5 Privacy

Everything is local: the model runs on your CPU, embeddings and color
signatures are stored in your StaX SQLite DB, and no asset or query is ever sent
to an external service.

---

## 7. Team collaboration

- **Roles & permissions:** admins manage a **role → permission matrix** in
  **Settings → Roles**. Permissions are granular:
  `can_ingest`, `can_delete`, `can_edit_metadata`, `can_manage_users`,
  `can_manage_schema`. Admins bypass all gates.
- **Activity feed:** who changed what, when.
- **`.staxbundle` export / import:** share metadata and previews between StaX
  installs. Import merges with a **newest-wins** policy, so bundles stay safe to
  exchange without clobbering newer local edits.

---

## 8. Analytics

Open the **Analytics** dock from the toolbar (or press **Ctrl+4**). No external
plotting libraries — built-in bar charts + tables, all exportable to CSV:

- **Search analytics:** query success rate and a list of zero-result queries
  (what people search for but don't find).
- **Storage hygiene:** storage totals plus duplicate clusters and the
  reclaimable bytes they represent.
- **Top-used assets:** most-inserted elements, from the insertion log.

---

## 9. Nuke integration

- Run standalone, or embed StaX as a **Nuke panel**.
- **Drag & drop** an asset into the Node Graph to create the right node
  automatically (**Read** for footage/images, **ReadGeo** for geometry).
- Register and insert **toolsets**.

---

## 10. Troubleshooting

| Symptom | Explanation / fix |
|---|---|
| `A module that was compiled using NumPy 1.x ...` on launch | Cosmetic NumPy notice from the bundled Qt. Harmless — the app runs. |
| AI search returns nothing | The CLIP weights (`weights/clip-vit-b32-onnx/`) are missing. Re-fetch with `python -m tools.download_clip_model`, then check **Settings → AI**. Color search works regardless. |
| "Reindex library" seems to do nothing | It only enqueues assets **missing** an embedding for the current model. If the model isn't installed, there's nothing to enqueue. |
| An action is greyed out or refused | You may lack the permission for it (e.g. `can_ingest`, `can_delete`, `can_edit_metadata`). Ask an admin to grant it in **Settings → Roles**. |
| App looks unstyled | Ensure you launched via `run_standalone` so the bundled Qt and `resources/style.qss` are used. |

---

*StaX is in Beta and under active development. Feedback and bug reports are
welcome via GitHub Issues.*
