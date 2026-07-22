# EP7 — AI Discovery (local-only) — Design

**Date:** 2026-07-23
**Status:** Approved (design)
**Part of:** the StaX feature-enhancement program (EP1–EP9), from `STAX_FEATURE_ENHANCEMENT_REPORT.md`.
**Covers report features:** F001 (semantic search by intent), F002 (visual search by reference image), F003 (similar-asset search from a selected item), F004 (color-palette search), and AI auto-tagging (§5.1 / Release Package D). **Defers** F005 (transcript/spoken-word search) and F006 (scene-descriptor search) — see §2.

---

## 1. Background & Motivation

StaX search today is structured only: `LIKE` over name/comment/tags plus EP2's faceted `FilterSpec` query builder. Users still have to remember a name or a tag to find an asset. The market (Eagle, Axle AI, Connecter AI Studio) rewards **content-aware discovery**: type an intent and get matching footage, drop a reference frame and get look-alikes, pick an asset and get "more like this", or search by color. EP7 delivers those on top of EP2's existing result surface — **entirely locally, with no cloud/API ever**.

The whole feature set rests on one primitive: a **vector embedding** per asset (a CLIP-style joint image/text space) plus a **dominant-color signature** (non-AI). Semantic, visual, similar-asset, and auto-tagging all reduce to cosine similarity over those vectors; color search reduces to histogram distance. At StaX library scale a brute-force numpy scan is fine, so **no external vector DB** is introduced — embeddings live in SQLite as blobs.

### Locked design decisions

- **LOCAL-ONLY, NO CLOUD, EVER.** EP7 defines an `Embedder` abstraction with a **single real implementation** — a bundled/downloaded **CLIP ViT-B/32** model run through **onnxruntime (CPU)**. There is no cloud/API provider class, now or later.
- **Graceful degradation is mandatory.** `get_embedder(config)` returns `None` when the model or runtime is unavailable. Every AI code path guards for a missing embedder and disables (with a clear message) rather than crashing. Color-palette search is **non-AI** and keeps working with no model.
- **Storage in SQLite.** An `element_embeddings` table (vector as a `float32` blob) and an `element_colors` table (histogram blob + dominant-color JSON). Similarity is **brute-force cosine in numpy** over the library; color is L1 histogram distance in numpy. No FAISS/Chroma/pgvector.
- **Reuse EP2.** AI results are returned as ordinary element rows (with an added `score` key) and rendered through EP2's existing result surface (`MediaDisplayWidget`); FilterSpec pre-filters the candidate set so AI search composes with facets.
- **First-run indexing is required.** Embeddings/colors are computed at ingest (a hook) and by a **backfill/index job** (SP2 async-worker pattern) for existing assets. Until an asset is indexed it does not appear in AI results.
- **Minimal new dependency.** One runtime dep (`onnxruntime`); the model + tokenizer are **downloaded on first run**, not pip-installed. `pillow`/`numpy` are already present.
- Windows + Linux; hybrid 3-tier testing; flat imports; `logging` not `print`.

### The model dependency (explicit and honest)

- **Model:** OpenAI **CLIP ViT-B/32**, exported to ONNX as two graphs — `clip_image.onnx` (image encoder) and `clip_text.onnx` (text encoder) — both producing **512-dim** vectors in a shared space. Plus a vendored pure-Python CLIP BPE tokenizer + its `bpe_simple_vocab_16e6.txt.gz` (~1.3 MB).
- **Runtime:** `onnxruntime` CPU wheel (~15 MB, prebuilt Win+Linux, **no PyTorch**). CPU inference on a 224×224 frame is ~50–150 ms — acceptable for a background index job.
- **Size / obtain:** image+text ONNX ≈ **120–170 MB** (fp32; an int8-quantized variant ≈ 60 MB is acceptable). Not committed to the repo. A `tools/download_clip_model.py` helper (mirroring the existing `tools/` ffmpeg downloader) fetches the files into a cache dir and verifies a SHA-256 checksum. If the download/runtime is absent, AI features are simply disabled.

### Dependencies (must land first)

- **SP1** — consolidated `DatabaseManager`, `get_connection(write=…)`, migration runner, column whitelisting.
- **SP2** — the async worker pattern (`preview_worker.PreviewWorker` QThread + queue) reused for the backfill/index worker, and the `ingestion_core.ingest_file` seam for the at-ingest index hook.
- **EP1** — `elements.rating` / `elements.label_fk` (AI results stay compatible with rating/label facets).
- **EP2** — `filter_spec.py` (`FilterSpec`, `empty_filter`, `normalize`), `search_elements_advanced` (candidate pre-filter), and `MediaDisplayWidget.apply_filter` / `_render_elements` (the result surface AI results reuse). Treated as an interface; if EP2 has not landed, the service falls back to `get_all_elements` for the candidate set.
- **SP0** — `stax_db` / headless-Qt fixtures for tests; a `fake_embedder` fixture injects deterministic vectors so no test downloads a model.

### Delivery clusters (incremental, in order)

- **7A — Embedding & index core:** `Embedder` abstraction + `FakeEmbedder` + `ClipOnnxEmbedder` + `get_embedder`; `element_embeddings` table + store/load API; the cosine `AiSearchService`; the backfill worker + at-ingest hook. Independently shippable (indexing works headless).
- **7B — AI search surfaces:** semantic search mode (F001), reference-image drop zone (F002), and "Find similar" context action (F003), all reusing EP2's result surface.
- **7C — Color & auto-tagging:** `element_colors` histogram computed at ingest (F004, non-AI) + color-palette search + color picker; AI auto-tag suggestion with human-in-the-loop accept.

---

## 2. Goals / Non-Goals

### Goals
- A local-only `Embedder` abstraction with a CLIP-ONNX implementation and a deterministic fake for tests.
- Embeddings + color signatures stored in SQLite; brute-force cosine / histogram search in numpy.
- Semantic (F001), visual-by-reference-image (F002), similar-asset (F003), color-palette (F004) search.
- AI auto-tagging: nearest tags from a known vocabulary, surfaced for human confirmation.
- A backfill/index job (async worker) + at-ingest indexing hook.
- Full graceful degradation when no model/runtime is present.

### Non-Goals (deferred)

- **F005 — transcript / spoken-word search.** Requires a bundled speech-to-text stack (e.g. `faster-whisper` / Vosk): another large model, per-clip audio decode, a transcript store, and time-coded search — a materially bigger dependency and pipeline than image embedding. **Out of scope for EP7**; a follow-on (EP7.5) can add a `transcripts` table and reuse the same async-worker + FilterSpec result surface once STT model packaging is decided.
- **F006 — scene-descriptor search (people/objects/actions).** Requires an object/action detection or captioning model and a per-frame descriptor index, plus a chip UI over detected concepts. **Out of scope for EP7**; the CLIP embedding already gives coarse zero-shot concept matching via semantic search, and a dedicated detector is a separate follow-on.
- Cloud/API embedding providers — **explicitly never** part of EP7.
- An external vector database / ANN index — brute force is sufficient at StaX scale; revisit only if libraries reach the hundreds of thousands of assets.
- GPU inference / model fine-tuning.

---

## 3. Detailed Design — Cluster 7A (Embedding & index core)

### 3.1 Embedder abstraction (`src/ai/embedder.py`)

```
class Embedder:                       # abstract
    id: str                            # model identity, stored alongside vectors
    dim: int = 512
    is_available() -> bool
    embed_text(text: str)  -> np.ndarray   # (dim,) float32, L2-normalized
    embed_image(image_path) -> np.ndarray  # (dim,) float32, L2-normalized

class FakeEmbedder(Embedder):          # tests only — deterministic, numpy-only
    # vectors seeded from sha1(input): identical input -> identical vector

class ClipOnnxEmbedder(Embedder):      # real, local; heavy imports deferred + guarded
    id = "clip-vit-b32-onnx"
    is_available()  -> onnxruntime importable AND model files present
    embed_text/embed_image -> onnxruntime session run on CPU

def get_embedder(config=None) -> Embedder | None
    # returns an available ClipOnnxEmbedder, else None (AI disabled) — never raises
```

`FakeEmbedder` ships in the module (numpy-only, no model) so every unit/GUI test can inject deterministic vectors without a download. `ClipOnnxEmbedder`'s real inference is exercised only by `@pytest.mark.manual` tests. All vectors are **L2-normalized on return**, so cosine similarity is a plain dot product.

### 3.2 Storage (`element_embeddings`)

```sql
CREATE TABLE element_embeddings (
    element_fk INTEGER PRIMARY KEY,
    model_id   TEXT NOT NULL,          -- e.g. 'clip-vit-b32-onnx'; detects stale on model change
    dim        INTEGER NOT NULL,
    vector     BLOB NOT NULL,          -- np.float32 tobytes(), length dim*4
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
);
```

DB API (numpy at the boundary only):
```
store_element_embedding(element_id, model_id, vector)
get_element_embedding(element_id) -> np.ndarray | None
get_all_embeddings(model_id=None) -> (ids: list[int], matrix: np.ndarray[N, dim])
get_elements_missing_embedding(model_id) -> list[int]   # never-indexed OR stale model_id
```

### 3.3 Similarity service (`src/ai/ai_search.py`)

`AiSearchService(db, embedder)` — the single entry point for every AI query. Brute-force cosine in numpy over `get_all_embeddings`; FilterSpec restricts candidates via EP2's `search_elements_advanced`; results are element rows with an added `score`.

```
semantic_search(text, top_k=50, filter_spec=None) -> list[dict]   # F001
visual_search(image_path, top_k=50, filter_spec=None) -> list[dict]  # F002
similar_to(element_id, top_k=50, filter_spec=None) -> list[dict]     # F003 (excludes self)
suggest_tags(element_id, vocabulary=None, top_k=8, min_score=0.22) -> list[(tag, score)]  # auto-tag
```

Every method **guards `self.embedder`**: when it is `None`, semantic/visual/similar/auto-tag return `[]` and callers show the "AI unavailable" state. `similar_to` uses the stored vector (no model needed to *read* it, but ranking still needs the same-space matrix). Result rows drop straight into `MediaDisplayWidget._render_elements`.

### 3.4 Backfill / index job (SP2 async worker + ingest hook)

- **Pure worker step** (`src/ai/indexer.py::index_element(db, element_id, embedder=None)`): computes the **color signature always** (non-AI) and the **embedding only when an embedder is available**; stores both; **never raises** (logs and continues). Returns `{"element_id", "embedded": bool, "colored": bool}`.
- **Async worker** `AiIndexWorker(QtCore.QThread)` — mirrors `preview_worker.PreviewWorker`: drains a `queue.Queue` of `element_id`s, calls `index_element`, emits `indexed(int)`, `progress(int, int)`, `finished()`. A **"Reindex library"** action (Settings → AI) enqueues `get_elements_missing_embedding(model_id)` (or all, on model change).
- **At-ingest hook:** `ingestion_core.ingest_file` calls an optional `self.ai_index_hook(element_id)` after `create_element` (next to the existing `post_hook`). `main.py` sets it to enqueue onto the worker. If unset, ingest is unchanged.

---

## 4. Detailed Design — Cluster 7B (AI search surfaces)

All three surfaces call `AiSearchService`, then hand the returned rows to the **existing** EP2 result path; a small helper `MediaDisplayWidget.show_ai_results(rows, heading)` renders a ranked, non-paginated result set and a "clear AI results" affordance.

- **Semantic search (F001):** an **AI toggle** beside the search box switches plain text from EP2's `run_text_search` to `AiSearchService.semantic_search(text, filter_spec=self.current_filter)`. The active FilterSpec still scopes the candidate set (facets + AI compose). When the embedder is `None` the toggle is disabled with a tooltip ("AI model not installed — run Settings → AI → Download model").
- **Visual search by reference image (F002):** a **drop zone** (`ui/image_drop_zone.py`, `QWidget` accepting `dropEvent` of an image file, plus a "Browse…" button) in the search panel. On drop it calls `visual_search(path, filter_spec=…)`. Accepts any Pillow-readable image; no ingest required.
- **Similar-asset search (F003):** a **"Find similar"** entry in the element context menu (gallery + table) calling `similar_to(element_id, filter_spec=…)`. Disabled when the asset has no stored embedding (with a "not indexed yet" tooltip).

### Degradation surface
A single `ai_status()` helper (`get_embedder` result + count of indexed elements) drives: toggle/menu enable-state, tooltips, and a status line in Settings → AI ("Model: available / not installed", "Indexed: N / M assets", "Reindex library").

---

## 5. Detailed Design — Cluster 7C (Color & auto-tagging)

### 5.1 Color-palette search (F004, non-AI)

Dependency-light PIL + numpy, computed at ingest (same hook as embeddings) and by the backfill job.

- **Signature** (`src/ai/color_index.py::compute_color_signature(image_path)`): open the preview/thumbnail via Pillow, resize to 64×64, convert to HSV, build a **12-bin hue histogram weighted by saturation×value** (so greys/darks don't dominate), L1-normalized; plus a short list of **dominant RGB colors** (coarse RGB binning, top-k by weight). Returns `{"histogram": np.float32[12], "dominant": [[r,g,b,weight], …]}` or `None`.

```sql
CREATE TABLE element_colors (
    element_fk INTEGER PRIMARY KEY,
    histogram  BLOB NOT NULL,          -- np.float32[12] tobytes()
    dominant   TEXT,                    -- JSON [[r,g,b,weight], ...]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
);
```

DB API: `store_element_color(element_id, histogram, dominant)`, `get_all_colors() -> (ids, matrix[N,12])`.
Service: `color_search(db, rgb, top_k=50) -> list[(element_id, score)]` — build the query's hue histogram, L1 distance over the matrix in numpy, rank; `score = 1 - dist/2`. **No embedder required** — color search works with AI fully disabled.

- **UI:** a **color picker** in EP2's filter drawer (a swatch → `QColorDialog`, or a fixed swatch palette). Selecting a color runs `color_search` and shows results via the same result surface.

### 5.2 AI auto-tagging

`AiSearchService.suggest_tags(element_id, vocabulary=None, top_k=8, min_score)`: embed each vocabulary term with the **text** encoder, cosine against the element's **image** embedding, return the top tags above `min_score`. Vocabulary defaults to `db.get_all_tags()` (the studio's own tag language) so suggestions stay on-vocabulary; a curated seed list can be added later.

**Human-in-the-loop** (report risk mitigation "AI feature quality noise"): a **"Suggest tags"** action (inspector / element context menu) opens a small dialog listing candidate tags with confidence + checkboxes; only checked tags are merged into the element's `tags`. Nothing is written automatically. Guarded — the action is disabled when the embedder is `None`.

---

## 6. Architecture & File Impact

| File | Change |
|---|---|
| `src/ai/__init__.py` (new) | package marker |
| `src/ai/embedder.py` (new) | `Embedder` ABC, `FakeEmbedder`, `ClipOnnxEmbedder`, `get_embedder`, `default_model_dir` |
| `src/ai/ai_search.py` (new) | `AiSearchService` (semantic/visual/similar/suggest_tags) + `color_search` |
| `src/ai/color_index.py` (new) | `compute_color_signature`, hue/rgb helpers (PIL + numpy, non-AI) |
| `src/ai/indexer.py` (new) | `index_element` pure step + `AiIndexWorker(QThread)` (SP2 pattern) |
| `src/db_manager.py` | `element_embeddings` + `element_colors` tables + migrations; embedding/color store/load + `get_elements_missing_embedding` |
| `src/ingestion_core.py` | `ingest_file` calls optional `self.ai_index_hook(element_id)` post-insert |
| `src/ui/image_drop_zone.py` (new) | reference-image drop zone widget (F002) |
| `src/ui/media_display_widget.py` | AI search toggle, `show_ai_results`, color picker in the drawer, "Find similar" context action |
| `src/ui/tag_suggest_dialog.py` (new) | human-in-loop auto-tag accept dialog |
| `src/ui/settings_panel.py` | AI tab: model status, Download model, Reindex library, indexed-count |
| `tools/download_clip_model.py` (new) | first-run model/tokenizer downloader + checksum verify |
| `main.py` | construct `get_embedder(config)` + `AiSearchService` + `AiIndexWorker`; set `ingestion_core.ai_index_hook` |
| `pyproject.toml` | add `onnxruntime` (justified; model itself is downloaded, not pip) |

Pure logic (`embedder` fake, `ai_search` ranking, `color_index`, `indexer.index_element`) is kept free of Qt so it is unit-testable with the fake embedder and no model download.

---

## 7. Testing Strategy

- **Unit (`tests/unit`, no model, no Qt):**
  - `FakeEmbedder`: determinism (same input → identical vector), L2-normalized, correct `dim`.
  - `get_embedder`: returns `None` when runtime/model absent (never raises).
  - `store/get_element_embedding` round-trip through the blob; `get_all_embeddings` shape; `get_elements_missing_embedding` (never-indexed + stale `model_id`).
  - `AiSearchService` with an injected `FakeEmbedder`: `semantic_search` ranks the seeded near-vector first; `visual_search` by image path; `similar_to` excludes self; **all return `[]` when embedder is `None`**; `filter_spec` restricts the candidate set (EP2 seam, `xfail` if EP2 absent).
  - `compute_color_signature`: histogram sums to 1, a solid-red image peaks in the red hue bin; `color_search` ranks the matching-color asset first (no embedder).
  - `suggest_tags`: with a fake, an element embedded from an image whose fake vector matches tag "fire" ranks "fire" first; empty when embedder `None` / no vocab.
  - `index_element`: colors written with no embedder; both written with a fake; never raises on a bad path.
  - Migrations create `element_embeddings` + `element_colors`.
- **GUI (`tests/gui`, headless, fake embedder injected):**
  - AI toggle disabled when embedder `None`; enabled + routes to `semantic_search` when present.
  - `ImageDropZone` emits the dropped path; visual results render via the result surface.
  - "Find similar" context action calls `similar_to` and shows ranked rows.
  - Color picker runs `color_search` and renders results.
  - `TagSuggestDialog` writes only checked tags.
  - Settings AI tab reflects `ai_status()` (available / not installed, indexed count).
- **Manual/slow (`@pytest.mark.manual`):** real `ClipOnnxEmbedder` load + one text/image embed round-trip, only when the model is present. **Not run in CI.**

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Model/runtime absent on a user's machine | `get_embedder` → `None`; every AI path guards and disables with a clear message; color search + all of EP1/EP2 keep working. Tests never need the model (fake injected). |
| Large model download / first-run indexing cost | Download is explicit (Settings → AI → Download model, checksum-verified); indexing runs on the SP2 background worker with progress; assets appear in AI results as they finish. |
| New heavy dependency | Only `onnxruntime` (CPU, no PyTorch, ~15 MB, prebuilt Win+Linux). The model is downloaded, not pip-installed. Justified in `pyproject.toml`. |
| AI tag/search noise erodes trust | Auto-tag is **suggest-only** with confidence + checkboxes (never auto-writes); search shows a `score`; thresholds tunable. |
| Brute-force cosine on a huge library | O(N·dim) numpy matmul is sub-second at StaX scale; `get_all_embeddings` can cache the matrix per session; ANN index is a documented later option. |
| Model swap invalidates stored vectors | `model_id` stored per row; `get_elements_missing_embedding` treats a changed `model_id` as stale so "Reindex library" re-embeds only what's needed. |
| Embedding non-image assets (3D/toolset) | Index the generated preview/thumbnail (already produced at ingest); if none, skip embedding (still colorless-safe) — the asset simply won't appear in AI results. |
| Comma-joined `tags` when merging auto-tags | Reuse EP2's tag-merge/dedupe idiom; suggestions are unioned into existing tags, deduped. |

---

## 9. Deliverables Checklist
- [ ] `Embedder` ABC + `FakeEmbedder` + `ClipOnnxEmbedder` + `get_embedder` (local-only, guarded).
- [ ] `element_embeddings` table + store/load + `get_elements_missing_embedding`.
- [ ] `AiSearchService`: semantic (F001), visual (F002), similar (F003), `suggest_tags`.
- [ ] `index_element` + `AiIndexWorker` backfill + `ingest_file` at-ingest hook.
- [ ] AI search toggle, `ImageDropZone`, "Find similar" context action on the EP2 result surface.
- [ ] `element_colors` + `compute_color_signature` + `color_search` + color picker (non-AI, F004).
- [ ] AI auto-tag `suggest_tags` + human-in-loop `TagSuggestDialog`.
- [ ] Settings AI tab (model status, download, reindex, indexed count) + graceful-degradation surface.
- [ ] `tools/download_clip_model.py`; `onnxruntime` added + justified in `pyproject.toml`.
- [ ] Unit + headless GUI tests green with the fake embedder; real-model tests `@pytest.mark.manual`.

---

## 10. Follow-on
EP7.5 can add **F005 transcript search** (bundle an STT model, a `transcripts` table, time-coded results reusing the FilterSpec surface) and **F006 scene descriptors** (a detection/captioning model + concept chips). EP4 custom fields can be **auto-populated from AI analysis** (colors → a "palette" field; top auto-tags → a "subjects" field). The stored embeddings also enable future **duplicate/near-duplicate clustering** beyond EP2's pHash.
