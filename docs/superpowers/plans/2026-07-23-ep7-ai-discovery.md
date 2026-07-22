# EP7 — AI Discovery (local-only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local-only AI discovery to StaX — semantic search (F001), visual search by reference image (F002), similar-asset search (F003), color-palette search (F004, non-AI), and AI auto-tagging — layered on EP2's `FilterSpec`/result surface. A local `Embedder` (CLIP-ONNX) is the only model; when it is unavailable every AI path degrades gracefully. Embeddings/colors live in SQLite; similarity is brute-force numpy. F005 (transcripts) and F006 (scene descriptors) are out of scope (see the design doc §2).

**Architecture:** A local-only `Embedder` abstraction (`FakeEmbedder` for tests, `ClipOnnxEmbedder` for production, `get_embedder()` returning `None` when unavailable) produces 512-dim L2-normalized vectors. `DatabaseManager` stores vectors/colors as blobs and returns numpy matrices. `AiSearchService` runs brute-force cosine and hands EP2's result surface ordinary element rows plus a `score`. An `AiIndexWorker` (SP2 QThread pattern) + an `ingest_file` hook compute embeddings/colors. Color search is pure PIL/numpy and needs no model. Every test injects a deterministic fake embedder — no downloads.

**Tech Stack:** Python 3.9, SQLite (via `DatabaseManager`), numpy + Pillow (present), `onnxruntime` (new; model downloaded at runtime), PySide2 (headless offscreen), pytest / pytest-qt.

## Global Constraints

- **Platforms:** Windows + Linux. **Python:** 3.9. **Imports:** flat (`from ai.embedder import ...`, `from db_manager import ...`). **Logging:** `logging`, not `print`. **Commits:** conventional.
- **LOCAL-ONLY. No cloud/API embedder is ever added.** The only real model is a local CLIP-ONNX run through `onnxruntime` on CPU.
- **Graceful degradation is mandatory.** `get_embedder(config)` returns `None` when the runtime/model is missing; every AI method guards `self.embedder` and returns `[]` (UI disables with a message). Color search is non-AI and always works.
- **One new dependency:** `onnxruntime` (CPU). The model + tokenizer are **downloaded at runtime**, never committed or pip-installed.
- **Tests never require the real model.** Inject `FakeEmbedder` (deterministic vectors). Any real-model test is marked `@pytest.mark.manual` and is not collected by `pytest -m "not manual"`.
- **numpy only at the boundary:** vectors are stored as `np.float32().tobytes()` blobs and read back with `np.frombuffer`.
- **Dependency — SP1:** `get_connection(write=True|False)` and the migration runner exist. If executing before SP1, drop the `write=` kwarg.
- **Dependency — SP2:** the `preview_worker.PreviewWorker` QThread+queue pattern and the `ingest_file` seam exist.
- **Dependency — EP2:** `filter_spec.py`, `search_elements_advanced`, and `MediaDisplayWidget.apply_filter`/`_render_elements`. If EP2 is absent, fall back to `get_all_elements` for candidates and mark the FilterSpec-composition assertions `xfail(strict=True)` with the EP2 id.
- New AI modules live under `src/ai/` (single responsibility); new widgets get their own files.

---

## Key facts (verified against the codebase)

- `elements` PK is `element_id`; useful columns: `preview_path`, `filepath_hard`, `filepath_soft`, `tags`, `type` (`src/db_manager.py:216`).
- `get_connection()` yields a `sqlite3.Connection` with `row_factory = sqlite3.Row` and commits on context exit (`src/db_manager.py:82`). SP1 adds the `write=` kwarg (EP2 already uses it).
- Schema is created in `_create_schema` (`src/db_manager.py:183`) and evolved idempotently in `_apply_migrations` via `SELECT name FROM sqlite_master WHERE type='table' AND name=?` guards (`src/db_manager.py:359`).
- `create_element(list_id, name, element_type, **kwargs)` returns the new `element_id` (`src/db_manager.py:741`); `ingest_file` calls it at `src/ingestion_core.py:854` and runs an optional `post_hook` right after (`:882`).
- `get_element_by_id(element_id)` exists (`src/db_manager.py:829`); `get_all_tags()` returns a sorted unique tag list parsed from comma-joined `elements.tags` (`src/db_manager.py:1307`).
- pHash precedent for guarded optional-dependency + graceful fallback: `duplicate_detection.compute_phash` (`src/duplicate_detection.py:59`) — mirror its try/except-ImportError shape for `ClipOnnxEmbedder`.
- Async worker precedent: `preview_worker.PreviewWorker(QtCore.QThread)` with `Signal` members and a `run()` queue drain (`src/preview_worker.py:120`).
- `pillow` and `numpy>=2` are already in `pyproject.toml`; `imagehash`/`opencv` also present.
- SP0 fixture `stax_db` builds a real `DatabaseManager` on a temp DB.

---

# Cluster 7A — Embedding & index core

## Task 1: `Embedder` abstraction + `FakeEmbedder` + `get_embedder`

**Files:**
- Create: `src/ai/__init__.py`, `src/ai/embedder.py`
- Test: `tests/unit/test_ep7_embedder.py`

**Interfaces:**
- Produces: `Embedder` (ABC-like), `FakeEmbedder(dim=512)` (`is_available`, `embed_text`, `embed_image` → L2-normalized `np.float32[dim]`), `ClipOnnxEmbedder(model_dir)`, `get_embedder(config=None) -> Embedder|None`, `default_model_dir()`, `EMBED_DIM`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep7_embedder.py`:

```python
import numpy as np
import pytest
from ai.embedder import FakeEmbedder, get_embedder, EMBED_DIM


@pytest.mark.unit
def test_fake_embedder_is_deterministic_and_normalized():
    emb = FakeEmbedder()
    v1 = emb.embed_text("fire explosion")
    v2 = emb.embed_text("fire explosion")
    assert v1.dtype == np.float32
    assert v1.shape == (EMBED_DIM,)
    assert np.allclose(v1, v2)                       # deterministic
    assert abs(float(np.linalg.norm(v1)) - 1.0) < 1e-5   # L2-normalized


@pytest.mark.unit
def test_fake_text_and_image_differ_and_image_is_pathkeyed():
    emb = FakeEmbedder()
    assert not np.allclose(emb.embed_text("x"), emb.embed_image("x"))
    assert np.allclose(emb.embed_image("/a/b.png"), emb.embed_image("/a/b.png"))


@pytest.mark.unit
def test_get_embedder_returns_none_when_unavailable(tmp_path):
    # empty model dir -> ClipOnnxEmbedder.is_available() is False -> None
    assert get_embedder({"ai_model_dir": str(tmp_path)}) is None
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep7_embedder.py -v`
Expected: FAIL — `ai.embedder` module missing.

- [ ] **Step 3: Implement**

Create `src/ai/__init__.py`:

```python
# -*- coding: utf-8 -*-
"""StaX local-only AI discovery package (EP7)."""
```

Create `src/ai/embedder.py`:

```python
# -*- coding: utf-8 -*-
"""Local-only embedding abstraction for AI discovery (EP7).

No cloud/API provider is ever used. The real implementation runs a
downloaded CLIP ViT-B/32 model through onnxruntime on CPU. When the model or
runtime is unavailable, get_embedder() returns None and every AI code path
degrades gracefully.
"""

import hashlib
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

EMBED_DIM = 512


def _l2_normalize(vec):
    vec = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return (vec / norm).astype(np.float32)


def default_model_dir():
    """Where downloaded CLIP-ONNX files live (see tools/download_clip_model.py)."""
    base = os.environ.get("STAX_AI_MODEL_DIR")
    if base:
        return base
    return os.path.join(os.path.expanduser("~"), ".stax", "models", "clip-vit-b32-onnx")


class Embedder(object):
    """Abstract local embedder mapping text/images to unit vectors."""

    id = "abstract"
    dim = EMBED_DIM

    def is_available(self):
        raise NotImplementedError

    def embed_text(self, text):
        raise NotImplementedError

    def embed_image(self, image_path):
        raise NotImplementedError


class FakeEmbedder(Embedder):
    """Deterministic, dependency-free embedder for tests.

    Vectors are seeded from a hash of the input, so identical inputs always
    map to identical vectors and cosine relationships are stable across runs.
    """

    id = "fake-v1"

    def __init__(self, dim=EMBED_DIM):
        self.dim = dim

    def is_available(self):
        return True

    def _vec(self, key):
        seed = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        return _l2_normalize(rng.rand(self.dim))

    def embed_text(self, text):
        return self._vec("t:" + (text or ""))

    def embed_image(self, image_path):
        return self._vec("i:" + str(image_path))


class ClipOnnxEmbedder(Embedder):
    """Real local CLIP ViT-B/32 embedder via onnxruntime (CPU).

    Model + tokenizer are fetched once by tools/download_clip_model.py into
    model_dir. Heavy imports are deferred and guarded (mirrors
    duplicate_detection.compute_phash) so a missing runtime never breaks import.
    Real inference is exercised only by @pytest.mark.manual tests.
    """

    id = "clip-vit-b32-onnx"

    def __init__(self, model_dir=None):
        self.model_dir = model_dir or default_model_dir()
        self._image_session = None
        self._text_session = None
        self._tokenizer = None

    def _image_path(self):
        return os.path.join(self.model_dir, "clip_image.onnx")

    def _text_path(self):
        return os.path.join(self.model_dir, "clip_text.onnx")

    def is_available(self):
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return False
        return os.path.isfile(self._image_path()) and os.path.isfile(self._text_path())

    # --- real inference (deferred; covered by manual tests) -----------------
    def _ensure_loaded(self):
        if self._image_session is None:
            import onnxruntime
            from clip_tokenizer import ClipTokenizer  # vendored BPE tokenizer
            self._image_session = onnxruntime.InferenceSession(
                self._image_path(), providers=["CPUExecutionProvider"])
            self._text_session = onnxruntime.InferenceSession(
                self._text_path(), providers=["CPUExecutionProvider"])
            self._tokenizer = ClipTokenizer(self.model_dir)

    def embed_text(self, text):
        self._ensure_loaded()
        tokens = self._tokenizer.encode(text or "")            # (1, 77) int64
        inp = self._text_session.get_inputs()[0].name
        out = self._text_session.run(None, {inp: tokens})[0][0]
        return _l2_normalize(out)

    def embed_image(self, image_path):
        self._ensure_loaded()
        from PIL import Image
        img = Image.open(image_path).convert("RGB").resize((224, 224))
        arr = np.asarray(img, dtype=np.float32) / 255.0
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        arr = (arr - mean) / std
        chw = np.transpose(arr, (2, 0, 1))[None, :, :, :].astype(np.float32)
        inp = self._image_session.get_inputs()[0].name
        out = self._image_session.run(None, {inp: chw})[0][0]
        return _l2_normalize(out)


def get_embedder(config=None):
    """Return an available local Embedder, or None (AI disabled). Never raises."""
    try:
        model_dir = None
        if config is not None:
            try:
                model_dir = config.get("ai_model_dir")
            except AttributeError:
                model_dir = getattr(config, "ai_model_dir", None)
        emb = ClipOnnxEmbedder(model_dir or default_model_dir())
        if emb.is_available():
            return emb
        logger.info("AI embedder unavailable (model/runtime missing) — AI features disabled.")
        return None
    except Exception:
        logger.exception("Failed to construct embedder")
        return None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep7_embedder.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai/__init__.py src/ai/embedder.py tests/unit/test_ep7_embedder.py
git commit -m "feat(ep7): add local-only Embedder abstraction + FakeEmbedder + get_embedder"
```

---

## Task 2: `element_embeddings` table + store/load DB API

**Files:**
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep7_embedding_store.py`

**Interfaces:**
- Produces table `element_embeddings` and: `store_element_embedding(element_id, model_id, vector)`, `get_element_embedding(element_id) -> np.ndarray|None`, `get_all_embeddings(model_id=None) -> (ids, matrix)`, `get_elements_missing_embedding(model_id) -> list[int]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep7_embedding_store.py`:

```python
import numpy as np
import pytest


def _seed(stax_db, n=3):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        for i in range(n):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')",
                         ("e{}".format(i),))


@pytest.mark.unit
def test_store_and_get_roundtrip(stax_db):
    _seed(stax_db)
    v = np.arange(512, dtype=np.float32) / 512.0
    stax_db.store_element_embedding(1, "m1", v)
    got = stax_db.get_element_embedding(1)
    assert got is not None
    assert np.allclose(got, v)


@pytest.mark.unit
def test_get_all_embeddings_shape(stax_db):
    _seed(stax_db)
    for eid in (1, 2):
        stax_db.store_element_embedding(eid, "m1", np.ones(512, dtype=np.float32) * eid)
    ids, matrix = stax_db.get_all_embeddings("m1")
    assert set(ids) == {1, 2}
    assert matrix.shape == (2, 512)


@pytest.mark.unit
def test_missing_embedding_includes_unindexed_and_stale(stax_db):
    _seed(stax_db)
    stax_db.store_element_embedding(1, "m1", np.zeros(512, dtype=np.float32))
    stax_db.store_element_embedding(2, "OLD", np.zeros(512, dtype=np.float32))
    missing = set(stax_db.get_elements_missing_embedding("m1"))
    assert missing == {2, 3}   # 2 is stale (model 'OLD'), 3 never indexed
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep7_embedding_store.py -v`
Expected: FAIL — table/methods missing.

- [ ] **Step 3: Implement schema + migration + methods**

Add the table to `_create_schema` and the idempotent `_apply_migrations` block (mirror the `sqlite_master` guard at `db_manager.py:405`):

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS element_embeddings (
                element_fk INTEGER PRIMARY KEY,
                model_id   TEXT NOT NULL,
                dim        INTEGER NOT NULL,
                vector     BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
            )
        """)
```

Add methods to `DatabaseManager`:

```python
    def store_element_embedding(self, element_id, model_id, vector):
        import numpy as np
        arr = np.asarray(vector, dtype=np.float32).reshape(-1)
        with self.get_connection(write=True) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO element_embeddings (element_fk, model_id, dim, vector) "
                "VALUES (?, ?, ?, ?)",
                (element_id, model_id, int(arr.shape[0]), arr.tobytes()))

    def get_element_embedding(self, element_id):
        import numpy as np
        with self.get_connection(write=False) as conn:
            row = conn.execute(
                "SELECT vector FROM element_embeddings WHERE element_fk = ?",
                (element_id,)).fetchone()
        if not row:
            return None
        return np.frombuffer(row["vector"], dtype=np.float32)

    def get_all_embeddings(self, model_id=None):
        """Return (ids: list[int], matrix: np.ndarray[N, dim]) for cosine search."""
        import numpy as np
        sql = "SELECT element_fk, vector FROM element_embeddings"
        params = []
        if model_id:
            sql += " WHERE model_id = ?"
            params.append(model_id)
        ids, vecs = [], []
        with self.get_connection(write=False) as conn:
            for r in conn.execute(sql, params).fetchall():
                ids.append(r["element_fk"])
                vecs.append(np.frombuffer(r["vector"], dtype=np.float32))
        if not vecs:
            return [], np.zeros((0, 0), dtype=np.float32)
        return ids, np.vstack(vecs)

    def get_elements_missing_embedding(self, model_id):
        """Elements never embedded OR embedded under a different model_id."""
        with self.get_connection(write=False) as conn:
            rows = conn.execute(
                "SELECT e.element_id FROM elements e "
                "LEFT JOIN element_embeddings em ON em.element_fk = e.element_id "
                "WHERE em.element_fk IS NULL OR em.model_id != ? "
                "ORDER BY e.element_id",
                (model_id,)).fetchall()
        return [r[0] for r in rows]
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep7_embedding_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_manager.py tests/unit/test_ep7_embedding_store.py
git commit -m "feat(ep7): add element_embeddings table + blob store/load API"
```

---

## Task 3: `AiSearchService` cosine core (semantic / visual / similar)

**Files:**
- Create: `src/ai/ai_search.py`
- Test: `tests/unit/test_ep7_ai_search.py`

**Interfaces:**
- Consumes: a `DatabaseManager` and an `Embedder` (fake in tests); `get_all_embeddings`, `get_element_embedding`, `get_element_by_id`, optional `search_elements_advanced` (EP2).
- Produces: `AiSearchService(db, embedder)` with `semantic_search`, `visual_search`, `similar_to`, `suggest_tags`; each returns element rows (dicts with a `score`) except `suggest_tags` which returns `(tag, score)` pairs. All AI methods return `[]` when `embedder` is `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep7_ai_search.py`:

```python
import numpy as np
import pytest
from ai.embedder import FakeEmbedder
from ai.ai_search import AiSearchService


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("fire", "water", "city"):
            conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,?, '2D', ?)",
                         (name, name))


def _index(stax_db, emb):
    # embed each element by its NAME so text queries have a known nearest match
    for eid, name in ((1, "fire"), (2, "water"), (3, "city")):
        stax_db.store_element_embedding(eid, emb.id, emb.embed_text(name))


@pytest.mark.unit
def test_semantic_search_ranks_exact_match_first(stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    _index(stax_db, emb)
    svc = AiSearchService(stax_db, emb)
    res = svc.semantic_search("fire", top_k=3)
    assert res[0]["name"] == "fire"
    assert "score" in res[0]


@pytest.mark.unit
def test_similar_to_excludes_self(stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    _index(stax_db, emb)
    svc = AiSearchService(stax_db, emb)
    res = svc.similar_to(1, top_k=3)
    assert all(r["element_id"] != 1 for r in res)


@pytest.mark.unit
def test_all_ai_methods_empty_without_embedder(stax_db):
    _seed(stax_db)
    svc = AiSearchService(stax_db, None)
    assert svc.semantic_search("fire") == []
    assert svc.visual_search("/x.png") == []
    assert svc.similar_to(1) == []
    assert svc.suggest_tags(1) == []


@pytest.mark.unit
def test_suggest_tags_picks_matching_vocab(stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    # element 1's image embedding equals the text vector for "fire"
    stax_db.store_element_embedding(1, emb.id, emb.embed_text("fire"))
    svc = AiSearchService(stax_db, emb)
    tags = svc.suggest_tags(1, vocabulary=["fire", "water", "city"], top_k=1, min_score=-1.0)
    assert tags[0][0] == "fire"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep7_ai_search.py -v`
Expected: FAIL — `ai.ai_search` missing.

- [ ] **Step 3: Implement**

Create `src/ai/ai_search.py`:

```python
# -*- coding: utf-8 -*-
"""Brute-force cosine similarity over locally-stored embeddings (EP7).

All AI methods guard self.embedder: with no embedder they return []. FilterSpec
(EP2) restricts the candidate set so AI search composes with facets. Results are
plain element rows with an added 'score' so EP2's result surface renders them.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


class AiSearchService(object):
    def __init__(self, db, embedder):
        self.db = db
        self.embedder = embedder

    # --- candidate scoping via EP2 (optional) -------------------------------
    def _allowed_ids(self, filter_spec):
        if not filter_spec:
            return None
        try:
            rows = self.db.search_elements_advanced(filter_spec)
        except AttributeError:
            logger.debug("search_elements_advanced (EP2) absent — no FilterSpec scoping")
            return None
        return set(r["element_id"] for r in rows)

    # --- core cosine rank ---------------------------------------------------
    def _rank(self, query_vec, top_k, allowed_ids):
        model_id = self.embedder.id if self.embedder else None
        ids, matrix = self.db.get_all_embeddings(model_id)
        if not ids:
            return []
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        qn = float(np.linalg.norm(q))
        if qn == 0.0:
            return []
        q = q / qn
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        sims = matrix.dot(q) / norms
        order = np.argsort(-sims)
        out = []
        for idx in order:
            eid = ids[int(idx)]
            if allowed_ids is not None and eid not in allowed_ids:
                continue
            out.append((eid, float(sims[int(idx)])))
            if len(out) >= top_k:
                break
        return out

    def _rows(self, ranked):
        out = []
        for eid, score in ranked:
            row = self.db.get_element_by_id(eid)
            if row:
                row = dict(row)
                row["score"] = score
                out.append(row)
        return out

    # --- public API ---------------------------------------------------------
    def semantic_search(self, text, top_k=50, filter_spec=None):
        if not self.embedder:
            return []
        return self._rows(self._rank(self.embedder.embed_text(text), top_k,
                                     self._allowed_ids(filter_spec)))

    def visual_search(self, image_path, top_k=50, filter_spec=None):
        if not self.embedder:
            return []
        return self._rows(self._rank(self.embedder.embed_image(image_path), top_k,
                                     self._allowed_ids(filter_spec)))

    def similar_to(self, element_id, top_k=50, filter_spec=None):
        if not self.embedder:
            return []
        vec = self.db.get_element_embedding(element_id)
        if vec is None:
            return []
        ranked = self._rank(vec, top_k + 1, self._allowed_ids(filter_spec))
        ranked = [(eid, s) for eid, s in ranked if eid != element_id][:top_k]
        return self._rows(ranked)

    def suggest_tags(self, element_id, vocabulary=None, top_k=8, min_score=0.22):
        if not self.embedder:
            return []
        vec = self.db.get_element_embedding(element_id)
        if vec is None:
            return []
        vocab = list(vocabulary) if vocabulary is not None else self.db.get_all_tags()
        if not vocab:
            return []
        tag_matrix = np.vstack([self.embedder.embed_text(t) for t in vocab])
        v = np.asarray(vec, dtype=np.float32).reshape(-1)
        vn = float(np.linalg.norm(v)) or 1.0
        sims = tag_matrix.dot(v / vn)
        order = np.argsort(-sims)
        out = [(vocab[int(i)], float(sims[int(i)])) for i in order
               if float(sims[int(i)]) >= min_score]
        return out[:top_k]
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep7_ai_search.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai/ai_search.py tests/unit/test_ep7_ai_search.py
git commit -m "feat(ep7): add AiSearchService cosine core (semantic/visual/similar/suggest_tags)"
```

---

## Task 4: Color signature (`element_colors`) + color search

**Files:**
- Create: `src/ai/color_index.py`
- Modify: `src/db_manager.py`
- Test: `tests/unit/test_ep7_color.py`

**Interfaces:**
- Produces: `compute_color_signature(image_path) -> dict|None` (`{"histogram": np.float32[12], "dominant": [[r,g,b,w],...]}`), `rgb_to_histogram(rgb) -> np.float32[12]`, `color_search(db, rgb, top_k=50) -> list[(element_id, score)]`; DB `store_element_color`, `get_all_colors() -> (ids, matrix)`. **No embedder required.**

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep7_color.py`:

```python
import numpy as np
import pytest
from PIL import Image
from ai.color_index import compute_color_signature, rgb_to_histogram, color_search


def _img(tmp_path, name, rgb):
    p = tmp_path / name
    Image.new("RGB", (32, 32), rgb).save(str(p))
    return str(p)


@pytest.mark.unit
def test_signature_histogram_normalized_and_red_peaks(tmp_path):
    sig = compute_color_signature(_img(tmp_path, "red.png", (255, 0, 0)))
    assert sig is not None
    hist = sig["histogram"]
    assert hist.shape == (12,)
    assert abs(float(hist.sum()) - 1.0) < 1e-4
    # red hue ~0 -> first bin dominates
    assert int(np.argmax(hist)) == 0


@pytest.mark.unit
def test_signature_none_on_missing_file():
    assert compute_color_signature("/no/such/file.png") is None


@pytest.mark.unit
def test_color_search_ranks_matching_color_first(stax_db, tmp_path):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'red','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'blue','2D')")
    stax_db.store_element_color(1, rgb_to_histogram((255, 0, 0)), None)
    stax_db.store_element_color(2, rgb_to_histogram((0, 0, 255)), None)
    ranked = color_search(stax_db, (250, 10, 10), top_k=2)
    assert ranked[0][0] == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep7_color.py -v`
Expected: FAIL — `ai.color_index` / DB methods missing.

- [ ] **Step 3: Implement**

Create `src/ai/color_index.py`:

```python
# -*- coding: utf-8 -*-
"""Dominant-color signatures for color-palette search (EP7, F004).

Dependency-light: Pillow + numpy only. No AI model involved, so color search
works even when the embedder is unavailable.
"""

import colorsys
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

HIST_BINS = 12


def _rgb_pixels_to_hist(arr):
    """arr: float32 [N,3] in 0..1 -> saturation*value weighted 12-bin hue hist."""
    hist = np.zeros(HIST_BINS, dtype=np.float32)
    for r, g, b in arr:
        h, s, v = colorsys.rgb_to_hsv(float(r), float(g), float(b))
        bin_idx = min(HIST_BINS - 1, int(h * HIST_BINS))
        hist[bin_idx] += s * v
    total = float(hist.sum())
    if total > 0:
        hist /= total
    return hist.astype(np.float32)


def rgb_to_histogram(rgb):
    """A single RGB (0..255) as a normalized hue histogram (for queries)."""
    arr = np.asarray([rgb], dtype=np.float32) / 255.0
    return _rgb_pixels_to_hist(arr)


def _dominant_colors(arr, k=5):
    """Coarse dominant colors: bucket to a 4x4x4 RGB grid, return top-k by weight."""
    buckets = {}
    for r, g, b in arr:
        key = (int(r * 3.999), int(g * 3.999), int(b * 3.999))
        buckets[key] = buckets.get(key, 0) + 1
    total = float(len(arr)) or 1.0
    top = sorted(buckets.items(), key=lambda kv: -kv[1])[:k]
    out = []
    for (br, bg, bb), count in top:
        out.append([int((br + 0.5) / 4 * 255), int((bg + 0.5) / 4 * 255),
                    int((bb + 0.5) / 4 * 255), round(count / total, 4)])
    return out


def compute_color_signature(image_path, sample=64):
    if not image_path or not os.path.isfile(image_path):
        return None
    try:
        from PIL import Image
        img = Image.open(image_path).convert("RGB").resize((sample, sample))
        arr = (np.asarray(img, dtype=np.float32) / 255.0).reshape(-1, 3)
    except Exception as exc:
        logger.debug("color signature failed for %s: %s", image_path, exc)
        return None
    return {"histogram": _rgb_pixels_to_hist(arr), "dominant": _dominant_colors(arr)}


def color_search(db, rgb, top_k=50):
    """Rank stored elements by L1 hue-histogram distance to the query color."""
    query = rgb_to_histogram(rgb)
    ids, matrix = db.get_all_colors()
    if not ids:
        return []
    dists = np.abs(matrix - query).sum(axis=1)
    order = np.argsort(dists)[:top_k]
    return [(ids[int(i)], float(1.0 - dists[int(i)] / 2.0)) for i in order]
```

Add the table to `_create_schema` + `_apply_migrations`:

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS element_colors (
                element_fk INTEGER PRIMARY KEY,
                histogram  BLOB NOT NULL,
                dominant   TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (element_fk) REFERENCES elements(element_id) ON DELETE CASCADE
            )
        """)
```

Add DB methods:

```python
    def store_element_color(self, element_id, histogram, dominant=None):
        import json
        import numpy as np
        blob = np.asarray(histogram, dtype=np.float32).reshape(-1).tobytes()
        dom = json.dumps(dominant) if dominant is not None else None
        with self.get_connection(write=True) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO element_colors (element_fk, histogram, dominant) "
                "VALUES (?, ?, ?)", (element_id, blob, dom))

    def get_all_colors(self):
        import numpy as np
        ids, hists = [], []
        with self.get_connection(write=False) as conn:
            for r in conn.execute("SELECT element_fk, histogram FROM element_colors").fetchall():
                ids.append(r["element_fk"])
                hists.append(np.frombuffer(r["histogram"], dtype=np.float32))
        if not hists:
            return [], np.zeros((0, 0), dtype=np.float32)
        return ids, np.vstack(hists)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep7_color.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai/color_index.py src/db_manager.py tests/unit/test_ep7_color.py
git commit -m "feat(ep7): add non-AI color signatures + palette search (F004)"
```

---

## Task 5: `index_element` step + `AiIndexWorker` + ingest hook

**Files:**
- Create: `src/ai/indexer.py`
- Modify: `src/ingestion_core.py`
- Test: `tests/unit/test_ep7_indexer.py`

**Interfaces:**
- Produces: `index_element(db, element_id, embedder=None) -> dict` (colors always, embedding only with an available embedder; never raises), `AiIndexWorker(QtCore.QThread)` (SP2 pattern: `enqueue(id)`, signals `indexed(int)`, `progress(int,int)`, `finished()`).
- Modifies: `IngestionCore.__init__` gains `self.ai_index_hook = None`; `ingest_file` calls it after `create_element`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ep7_indexer.py`:

```python
import numpy as np
import pytest
from PIL import Image
from ai.embedder import FakeEmbedder
from ai.indexer import index_element


def _seed_with_preview(stax_db, tmp_path):
    p = tmp_path / "prev.png"
    Image.new("RGB", (16, 16), (255, 0, 0)).save(str(p))
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,preview_path) VALUES (1,'a','2D',?)",
                     (str(p),))


@pytest.mark.unit
def test_index_writes_color_without_embedder(stax_db, tmp_path):
    _seed_with_preview(stax_db, tmp_path)
    res = index_element(stax_db, 1, embedder=None)
    assert res["colored"] is True
    assert res["embedded"] is False
    ids, matrix = stax_db.get_all_colors()
    assert ids == [1]


@pytest.mark.unit
def test_index_writes_both_with_embedder(stax_db, tmp_path):
    _seed_with_preview(stax_db, tmp_path)
    res = index_element(stax_db, 1, embedder=FakeEmbedder())
    assert res["colored"] is True and res["embedded"] is True
    assert stax_db.get_element_embedding(1) is not None


@pytest.mark.unit
def test_index_never_raises_on_bad_element(stax_db):
    res = index_element(stax_db, 9999, embedder=FakeEmbedder())
    assert res["embedded"] is False and res["colored"] is False
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/unit/test_ep7_indexer.py -v`
Expected: FAIL — `ai.indexer` missing.

- [ ] **Step 3: Implement**

Create `src/ai/indexer.py`:

```python
# -*- coding: utf-8 -*-
"""At-ingest + backfill indexing (EP7). Reuses the SP2 async-worker pattern
(preview_worker.PreviewWorker). index_element is a pure step: colors always,
embeddings only when an embedder is available. It never raises."""

import logging
import queue

from ai.color_index import compute_color_signature

logger = logging.getLogger(__name__)


def _image_for(row):
    return (row.get("preview_path") or row.get("filepath_hard")
            or row.get("filepath_soft"))


def index_element(db, element_id, embedder=None):
    """Compute + store color (always) and embedding (if embedder available)."""
    result = {"element_id": element_id, "embedded": False, "colored": False}
    row = db.get_element_by_id(element_id)
    if not row:
        return result
    row = dict(row)
    image_path = _image_for(row)

    try:
        sig = compute_color_signature(image_path)
        if sig is not None:
            db.store_element_color(element_id, sig["histogram"], sig["dominant"])
            result["colored"] = True
    except Exception:
        logger.exception("color index failed for element %s", element_id)

    if embedder is not None:
        try:
            if embedder.is_available() and image_path:
                vec = embedder.embed_image(image_path)
                db.store_element_embedding(element_id, embedder.id, vec)
                result["embedded"] = True
        except Exception:
            logger.exception("embedding failed for element %s", element_id)
    return result


try:
    from PySide2 import QtCore

    class AiIndexWorker(QtCore.QThread):
        """Drains a queue of element_ids and indexes them off the GUI thread."""

        indexed = QtCore.Signal(int)
        progress = QtCore.Signal(int, int)   # (done, total)
        finished_all = QtCore.Signal()

        def __init__(self, db, embedder=None, parent=None):
            super(AiIndexWorker, self).__init__(parent)
            self.db = db
            self.embedder = embedder
            self._queue = queue.Queue()
            self._running = True
            self._done = 0
            self._total = 0

        def enqueue(self, element_id):
            self._total += 1
            self._queue.put(element_id)

        def enqueue_many(self, element_ids):
            for eid in element_ids:
                self.enqueue(eid)

        def stop(self):
            self._running = False
            self._queue.put(None)

        def run(self):
            while self._running:
                eid = self._queue.get()
                if eid is None:
                    break
                index_element(self.db, eid, self.embedder)
                self._done += 1
                self.indexed.emit(eid)
                self.progress.emit(self._done, self._total)
                if self._queue.empty():
                    self.finished_all.emit()

except ImportError:   # headless without PySide2
    AiIndexWorker = None   # type: ignore
```

Wire the ingest hook. In `IngestionCore.__init__` add:

```python
        self.ai_index_hook = None   # set by main.py: lambda eid: ai_worker.enqueue(eid)
```

In `ingest_file`, right after the `create_element` call (`src/ingestion_core.py:870`) and before/after the existing `post_hook`:

```python
            if self.ai_index_hook:
                try:
                    self.ai_index_hook(element_id)
                except Exception:
                    logger.exception("ai_index_hook failed for element %s", element_id)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_ep7_indexer.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai/indexer.py src/ingestion_core.py tests/unit/test_ep7_indexer.py
git commit -m "feat(ep7): add index_element + AiIndexWorker backfill + ingest hook"
```

---

# Cluster 7B — AI search surfaces

## Task 6: `ImageDropZone` widget + AI result surface

**Files:**
- Create: `src/ui/image_drop_zone.py`
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep7_visual_search.py`

**Interfaces:**
- Produces: `ImageDropZone(parent=None)` with signal `image_dropped(str)` (accepts a dropped/browsed image path); `MediaDisplayWidget.show_ai_results(rows, heading="")` (renders ranked rows via the existing `_render_elements`) and `MediaDisplayWidget.run_visual_search(path)`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep7_visual_search.py`:

```python
import numpy as np
import pytest
from PIL import Image
from ai.embedder import FakeEmbedder
from ai.ai_search import AiSearchService


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'fire','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'water','2D')")


@pytest.mark.gui
def test_drop_zone_emits_path(qtbot, tmp_path):
    from ui.image_drop_zone import ImageDropZone
    p = tmp_path / "ref.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(str(p))
    zone = ImageDropZone()
    qtbot.addWidget(zone)
    with qtbot.waitSignal(zone.image_dropped, timeout=1000):
        zone.accept_path(str(p))


@pytest.mark.gui
def test_run_visual_search_renders_results(qtbot, stax_db):
    _seed(stax_db)
    emb = FakeEmbedder()
    # index element 1 so its image-embedding is the query's nearest neighbour
    ref = "/ref/frame.png"
    stax_db.store_element_embedding(1, emb.id, emb.embed_image(ref))
    stax_db.store_element_embedding(2, emb.id, emb.embed_text("water"))
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    w.ai_service = AiSearchService(stax_db, emb)
    qtbot.addWidget(w)
    rows = w.run_visual_search(ref)
    assert rows[0]["element_id"] == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep7_visual_search.py -v`
Expected: FAIL — module/methods missing.

- [ ] **Step 3: Implement**

Create `src/ui/image_drop_zone.py`:

```python
# -*- coding: utf-8 -*-
"""Reference-image drop zone for visual search (EP7, F002)."""

import os

from PySide2 import QtWidgets, QtCore

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".exr")


class ImageDropZone(QtWidgets.QFrame):
    image_dropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(ImageDropZone, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        layout = QtWidgets.QVBoxLayout(self)
        self._label = QtWidgets.QLabel("Drop a reference image\nor click Browse")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._label)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._on_browse)
        layout.addWidget(browse)

    def accept_path(self, path):
        if path and os.path.splitext(path)[1].lower() in _IMAGE_EXTS:
            self.image_dropped.emit(path)

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose reference image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.exr)")
        if path:
            self.accept_path(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.accept_path(url.toLocalFile())
            break
```

In `MediaDisplayWidget`, add the AI service holder + result surface (reuse the existing element-render entry point that EP2's `apply_filter` uses, i.e. `_render_elements`):

```python
        self.ai_service = None   # set by main.py: AiSearchService(db, get_embedder(config))
```

```python
    def show_ai_results(self, rows, heading=""):
        """Render a ranked, non-paginated AI result set via the existing surface."""
        self._render_elements(rows)   # same entry EP2 apply_filter uses
        if hasattr(self, "chip_bar"):
            self.chip_bar.count_label.setText("{} results{}".format(
                len(rows), " — " + heading if heading else ""))
        return rows

    def run_visual_search(self, image_path):
        if not self.ai_service or not self.ai_service.embedder:
            logger.info("visual search unavailable — no embedder")
            return []
        spec = getattr(self, "current_filter", None)
        rows = self.ai_service.visual_search(image_path, filter_spec=spec)
        return self.show_ai_results(rows, "similar to reference image")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep7_visual_search.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/image_drop_zone.py src/ui/media_display_widget.py tests/gui/test_ep7_visual_search.py
git commit -m "feat(ep7): add reference-image drop zone + visual search surface (F002)"
```

---

## Task 7: Semantic search toggle + "Find similar" action

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep7_semantic_similar.py`

**Interfaces:**
- Produces: `MediaDisplayWidget.run_semantic_search(text)` (F001, honors the AI toggle + current FilterSpec), `run_similar_search(element_id)` (F003), and `ai_enabled()` (drives toggle/menu enable-state). The "Find similar" context action calls `run_similar_search`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep7_semantic_similar.py`:

```python
import pytest
from ai.embedder import FakeEmbedder
from ai.ai_search import AiSearchService


def _seed_indexed(stax_db, emb):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        for name in ("fire", "water", "city"):
            conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,?, '2D')", (name,))
    for eid, name in ((1, "fire"), (2, "water"), (3, "city")):
        stax_db.store_element_embedding(eid, emb.id, emb.embed_text(name))


@pytest.mark.gui
def test_semantic_search_returns_best_match_first(qtbot, stax_db):
    emb = FakeEmbedder()
    _seed_indexed(stax_db, emb)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    w.ai_service = AiSearchService(stax_db, emb)
    qtbot.addWidget(w)
    rows = w.run_semantic_search("fire")
    assert rows[0]["name"] == "fire"


@pytest.mark.gui
def test_ai_disabled_when_no_embedder(qtbot, stax_db):
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    w.ai_service = AiSearchService(stax_db, None)
    qtbot.addWidget(w)
    assert w.ai_enabled() is False
    assert w.run_semantic_search("fire") == []
    assert w.run_similar_search(1) == []
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep7_semantic_similar.py -v`
Expected: FAIL — methods missing.

- [ ] **Step 3: Implement**

Add to `MediaDisplayWidget`:

```python
    def ai_enabled(self):
        return bool(self.ai_service and self.ai_service.embedder)

    def run_semantic_search(self, text):
        if not self.ai_enabled():
            logger.info("semantic search unavailable — no embedder")
            return []
        spec = getattr(self, "current_filter", None)
        rows = self.ai_service.semantic_search(text, filter_spec=spec)
        return self.show_ai_results(rows, "semantic: " + text)

    def run_similar_search(self, element_id):
        if not self.ai_enabled():
            logger.info("similar search unavailable — no embedder")
            return []
        rows = self.ai_service.similar_to(
            element_id, filter_spec=getattr(self, "current_filter", None))
        return self.show_ai_results(rows, "similar assets")
```

Wire the surfaces (integration; anchor to existing local names — read the file first):
- Add an **"AI" checkable toggle** beside the search box; when checked, `on_search(text)` (`src/ui/media_display_widget.py:546`) routes plain text to `run_semantic_search(text)` instead of EP2's `run_text_search`. Disable the toggle (with a tooltip) when `ai_enabled()` is `False`.
- Add a **"Find similar"** entry to the element context menu (gallery + table) calling `run_similar_search(element_id)`; disable it when `ai_enabled()` is `False`.
- Host the `ImageDropZone` (Task 6) in the search/filter panel and connect its `image_dropped` signal to `run_visual_search`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep7_semantic_similar.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep7_semantic_similar.py
git commit -m "feat(ep7): add semantic-search toggle + Find similar action (F001/F003)"
```

---

# Cluster 7C — Color picker & auto-tagging

## Task 8: Color picker in the filter drawer

**Files:**
- Modify: `src/ui/media_display_widget.py`
- Test: `tests/gui/test_ep7_color_picker.py`

**Interfaces:**
- Produces: `MediaDisplayWidget.run_color_search(rgb)` (F004; uses `color_index.color_search`, renders via `show_ai_results`) and a color swatch/button in the filter drawer that calls it. **Works with no embedder.**

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep7_color_picker.py`:

```python
import pytest
from ai.color_index import rgb_to_histogram


def _seed_colored(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'red','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'blue','2D')")
    stax_db.store_element_color(1, rgb_to_histogram((255, 0, 0)), None)
    stax_db.store_element_color(2, rgb_to_histogram((0, 0, 255)), None)


@pytest.mark.gui
def test_color_search_works_without_embedder(qtbot, stax_db):
    _seed_colored(stax_db)
    from ui.media_display_widget import MediaDisplayWidget
    w = MediaDisplayWidget(stax_db)
    w.ai_service = None   # color search must not need AI
    qtbot.addWidget(w)
    rows = w.run_color_search((250, 10, 10))
    assert rows[0]["element_id"] == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep7_color_picker.py -v`
Expected: FAIL — `run_color_search` missing.

- [ ] **Step 3: Implement**

Add to `MediaDisplayWidget`:

```python
    def run_color_search(self, rgb):
        from ai.color_index import color_search
        ranked = color_search(self.db, rgb)
        rows = []
        for eid, score in ranked:
            row = self.db.get_element_by_id(eid)
            if row:
                row = dict(row)
                row["score"] = score
                rows.append(row)
        return self.show_ai_results(rows, "color match")
```

Integration: add a **color swatch button** to the filter drawer (`FacetDrawer` or the media panel toolbar) that opens `QtWidgets.QColorDialog.getColor()` and, on accept, calls `run_color_search((c.red(), c.green(), c.blue()))`. This surface does **not** check `ai_enabled()` — color is non-AI.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep7_color_picker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/media_display_widget.py tests/gui/test_ep7_color_picker.py
git commit -m "feat(ep7): add color-palette picker + search (F004, non-AI)"
```

---

## Task 9: Auto-tag suggestion dialog (human-in-the-loop)

**Files:**
- Create: `src/ui/tag_suggest_dialog.py`
- Test: `tests/gui/test_ep7_tag_suggest.py`

**Interfaces:**
- Produces: `TagSuggestDialog(suggestions, existing_tags=None, parent=None)` with checkboxes per `(tag, score)`; `accepted_tags() -> list[str]` (only checked); a static `merge_tags(existing_csv, new_tags) -> str` (deduped comma-join reusing EP2's tag idiom).

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep7_tag_suggest.py`:

```python
import pytest
from ui.tag_suggest_dialog import TagSuggestDialog


@pytest.mark.gui
def test_only_checked_tags_are_returned(qtbot):
    dlg = TagSuggestDialog([("fire", 0.9), ("smoke", 0.7), ("city", 0.3)])
    qtbot.addWidget(dlg)
    dlg.set_checked("fire", True)
    dlg.set_checked("smoke", False)
    dlg.set_checked("city", False)
    assert dlg.accepted_tags() == ["fire"]


@pytest.mark.gui
def test_merge_tags_dedupes(qtbot):
    assert TagSuggestDialog.merge_tags("fire, city", ["fire", "smoke"]) == "fire, city, smoke"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep7_tag_suggest.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/ui/tag_suggest_dialog.py`:

```python
# -*- coding: utf-8 -*-
"""Human-in-the-loop auto-tag accept dialog (EP7). Suggestions are never
written automatically — the user checks the tags to add."""

from PySide2 import QtWidgets, QtCore


class TagSuggestDialog(QtWidgets.QDialog):
    def __init__(self, suggestions, existing_tags=None, parent=None):
        super(TagSuggestDialog, self).__init__(parent)
        self.setWindowTitle("Suggested tags")
        self._boxes = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("AI-suggested tags (check the ones to add):"))
        existing = set(t.strip().lower() for t in (existing_tags or []))
        for tag, score in suggestions:
            cb = QtWidgets.QCheckBox("{}  ({:.0%})".format(tag, score))
            cb.setChecked(score >= 0.35 and tag.lower() not in existing)
            layout.addWidget(cb)
            self._boxes[tag] = cb
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_checked(self, tag, checked):
        if tag in self._boxes:
            self._boxes[tag].setChecked(checked)

    def accepted_tags(self):
        return [tag for tag, cb in self._boxes.items() if cb.isChecked()]

    @staticmethod
    def merge_tags(existing_csv, new_tags):
        out, seen = [], set()
        for t in [x.strip() for x in (existing_csv or "").split(",") if x.strip()]:
            key = t.lower()
            if key not in seen:
                seen.add(key); out.append(t)
        for t in new_tags:
            key = t.strip().lower()
            if key and key not in seen:
                seen.add(key); out.append(t.strip())
        return ", ".join(out)
```

Integration: add a **"Suggest tags"** action to the element context menu / inspector. It calls `ai_service.suggest_tags(element_id)`, opens `TagSuggestDialog(suggestions, existing_tags=current)`, and on accept writes `TagSuggestDialog.merge_tags(current_csv, dlg.accepted_tags())` back via the element's tag-update path. Disable the action when `ai_enabled()` is `False`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep7_tag_suggest.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ui/tag_suggest_dialog.py tests/gui/test_ep7_tag_suggest.py
git commit -m "feat(ep7): add human-in-the-loop auto-tag suggestion dialog"
```

---

## Task 10: Settings AI tab (status, download, reindex) + `pyproject` dep

**Files:**
- Modify: `src/ui/settings_panel.py`, `pyproject.toml`
- Create: `tools/download_clip_model.py`
- Test: `tests/gui/test_ep7_settings_ai.py`

**Interfaces:**
- Consumes: `get_embedder`, `get_elements_missing_embedding`, `AiIndexWorker`.
- Produces: `SettingsPanel._build_ai_tab() -> QWidget` added via `addTab(tab, "AI")`; a `ai_status_label` reflecting model availability + indexed count; a "Reindex library" button that enqueues `get_elements_missing_embedding(model_id)`; a "Download model" button invoking the downloader. Controls degrade gracefully when no embedder.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep7_settings_ai.py`:

```python
import pytest


class _Main:
    def check_admin_permission(self):
        return True


@pytest.mark.gui
def test_ai_tab_reports_unavailable_when_no_model(qtbot, stax_db, tmp_path):
    from ui.settings_panel import SettingsPanel
    panel = SettingsPanel(stax_db, config={"ai_model_dir": str(tmp_path)},
                          main_window=_Main())
    qtbot.addWidget(panel)
    assert "not installed" in panel.ai_status_label.text().lower()
    # reindex is safe to click even with no model (color-only) but should not raise
    panel._on_reindex_library()
```

> Match `SettingsPanel.__init__`'s real signature (same `config` / `main_window` source EP1/EP2 tabs use). If it takes `config=None`, thread the AI model dir from there.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep7_settings_ai.py -v`
Expected: FAIL — `ai_status_label` / `_build_ai_tab` missing.

- [ ] **Step 3: Implement**

In `SettingsPanel.setup_ui`, after the other `addTab` calls:

```python
        self.tab_widget.addTab(self._build_ai_tab(), "AI")
```

Add the builder + helpers (guarded; never require the model):

```python
    def _build_ai_tab(self):
        from PySide2 import QtWidgets
        from ai.embedder import get_embedder
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        self._ai_embedder = get_embedder(self.config)
        self.ai_status_label = QtWidgets.QLabel()
        self._refresh_ai_status()
        layout.addWidget(self.ai_status_label)

        self.download_model_button = QtWidgets.QPushButton("Download model…")
        self.download_model_button.clicked.connect(self._on_download_model)
        layout.addWidget(self.download_model_button)

        self.reindex_button = QtWidgets.QPushButton("Reindex library")
        self.reindex_button.clicked.connect(self._on_reindex_library)
        layout.addWidget(self.reindex_button)

        layout.addStretch(1)
        return tab

    def _refresh_ai_status(self):
        emb = getattr(self, "_ai_embedder", None)
        if emb is None:
            self.ai_status_label.setText(
                "AI model: <b>not installed</b> — semantic/visual/similar/auto-tag disabled. "
                "Color search still works. Click Download model to enable AI.")
            return
        try:
            missing = len(self.db.get_elements_missing_embedding(emb.id))
        except Exception:
            missing = 0
        self.ai_status_label.setText(
            "AI model: <b>available</b> ({}). {} asset(s) awaiting indexing.".format(
                emb.id, missing))

    def _on_download_model(self):
        from PySide2 import QtWidgets
        try:
            import tools.download_clip_model as dl  # noqa
            QtWidgets.QMessageBox.information(
                self, "Download model",
                "Run: python -m tools.download_clip_model\n"
                "Then reopen Settings → AI.")
        except Exception:
            QtWidgets.QMessageBox.warning(self, "Download model",
                                          "Downloader unavailable.")

    def _on_reindex_library(self):
        from ai.embedder import get_embedder
        emb = get_embedder(self.config)
        model_id = emb.id if emb else "none"
        try:
            ids = self.db.get_elements_missing_embedding(model_id) if emb else []
        except Exception:
            ids = []
        worker = getattr(self, "ai_index_worker", None)
        if worker is not None and ids:
            worker.enqueue_many(ids)
        self._refresh_ai_status()
```

Create `tools/download_clip_model.py` (first-run downloader; mirrors the existing ffmpeg downloader — URLs/checksums filled in at build time):

```python
# -*- coding: utf-8 -*-
"""Download the local CLIP ViT-B/32 ONNX model + BPE tokenizer for EP7.

No cloud inference — this only fetches model files once so ClipOnnxEmbedder can
run locally. Files land in ai.embedder.default_model_dir() and are checksum-verified.
"""

import hashlib
import os
import sys
import urllib.request

# (filename, url, sha256) — populate with the release-hosted artifacts.
FILES = [
    ("clip_image.onnx", "", ""),
    ("clip_text.onnx", "", ""),
    ("bpe_simple_vocab_16e6.txt.gz", "", ""),
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    from ai.embedder import default_model_dir
    dest = default_model_dir()
    os.makedirs(dest, exist_ok=True)
    for name, url, sha in FILES:
        if not url:
            print("No URL configured for {} — skipping.".format(name))
            continue
        out = os.path.join(dest, name)
        print("Downloading {} -> {}".format(name, out))
        urllib.request.urlretrieve(url, out)
        if sha and _sha256(out) != sha:
            print("Checksum mismatch for {}".format(name)); return 1
    print("Model ready in {}".format(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add the dependency to `pyproject.toml` (justified inline in the PR body / spec §1):

```toml
    "onnxruntime>=1.17.0",
```

> Justification: local CPU inference runtime for the CLIP ONNX model. No PyTorch, ~15 MB prebuilt Win+Linux wheels. The model itself is downloaded at runtime, not pip-installed.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep7_settings_ai.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full EP7 suite**

Run: `pytest -m "not manual" -k ep7 -v`
Expected: all EP7 unit + gui tests pass (no model downloaded).

- [ ] **Step 6: Commit**

```bash
git add src/ui/settings_panel.py tools/download_clip_model.py pyproject.toml tests/gui/test_ep7_settings_ai.py
git commit -m "feat(ep7): add Settings AI tab (status/download/reindex) + onnxruntime dep"
```

---

## Task 11: `main.py` wiring — embedder, service, worker, ingest hook

**Files:**
- Modify: `main.py`
- Test: `tests/gui/test_ep7_wiring.py`

**Interfaces:**
- Consumes: `get_embedder`, `AiSearchService`, `AiIndexWorker`.
- Produces: on startup the main window builds `self.embedder = get_embedder(config)`, `media_display.ai_service = AiSearchService(db, self.embedder)`, starts `self.ai_index_worker = AiIndexWorker(db, self.embedder)`, and sets `ingestion_core.ai_index_hook = self.ai_index_worker.enqueue`. All guarded so a `None` embedder never breaks startup.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_ep7_wiring.py`:

```python
import pytest
from ai.ai_search import AiSearchService


@pytest.mark.gui
def test_ingest_hook_enqueues_new_element(qtbot, stax_db, tmp_path):
    # A minimal stand-in for the wiring contract: setting ai_index_hook on the
    # ingestion core causes ingest_file to enqueue the new element id.
    from ingestion_core import IngestionCore
    core = IngestionCore(stax_db, config={})
    enqueued = []
    core.ai_index_hook = lambda eid: enqueued.append(eid)
    stax_db.create_stack("S", str(tmp_path / "S"))
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
    src = tmp_path / "a.png"
    from PIL import Image
    Image.new("RGB", (8, 8), (0, 128, 0)).save(str(src))
    res = core.ingest_file(str(src), target_list_id=1, copy_policy="soft")
    assert res["success"] is True
    assert enqueued == [res["element_id"]]
```

> Match `IngestionCore.__init__`'s real signature (read `src/ingestion_core.py`). If ingest needs more setup (config keys, target dirs), mirror an existing ingestion test in `tests/`.

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/gui/test_ep7_wiring.py -v`
Expected: FAIL — `ai_index_hook` not called (until Task 5's hook + this wiring land). If Task 5 already added the hook, this verifies the enqueue contract directly.

- [ ] **Step 3: Implement**

In the main window startup (where the DB, config, `MediaDisplayWidget`, and `IngestionCore` are already constructed), add:

```python
        from ai.embedder import get_embedder
        from ai.ai_search import AiSearchService
        from ai.indexer import AiIndexWorker

        self.embedder = get_embedder(self.config)
        self.media_display.ai_service = AiSearchService(self.db, self.embedder)
        if AiIndexWorker is not None:
            self.ai_index_worker = AiIndexWorker(self.db, self.embedder)
            self.ai_index_worker.start()
            self.ingestion_core.ai_index_hook = self.ai_index_worker.enqueue
        else:
            self.ai_index_worker = None
        if self.embedder is None:
            logger.info("EP7: AI embedder unavailable — AI discovery features disabled "
                        "(color search still active).")
```

Ensure the worker is stopped on shutdown (in the window's `closeEvent`):

```python
        if getattr(self, "ai_index_worker", None) is not None:
            self.ai_index_worker.stop()
            self.ai_index_worker.wait(2000)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/gui/test_ep7_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full EP7 suite**

Run: `pytest -m "not manual" -k ep7 -v`
Expected: all EP7 unit + gui tests pass.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/gui/test_ep7_wiring.py
git commit -m "feat(ep7): wire embedder + AiSearchService + index worker + ingest hook"
```

---

## Self-Review

**1. Spec coverage:**
- Local-only `Embedder` + `FakeEmbedder` + `ClipOnnxEmbedder` + `get_embedder` (graceful `None`) → Task 1 ✓
- Embeddings in SQLite (blob) + store/load + stale/missing detection → Task 2 ✓
- Brute-force cosine `AiSearchService`: semantic (F001), visual (F002), similar (F003), auto-tag suggest → Tasks 3, 6, 7, 9 ✓
- Color-palette search (F004, non-AI, PIL/numpy) + store + picker → Tasks 4, 8 ✓
- Backfill/index worker (SP2 pattern) + at-ingest hook → Tasks 5, 11 ✓
- Reuse EP2 FilterSpec/result surface (`_render_elements`, `search_elements_advanced`, `current_filter`) → Tasks 3, 6, 7, 8 ✓
- Drop zone (F002), "Find similar" action (F003), color picker (F004), auto-tag human-in-loop → Tasks 6, 7, 8, 9 ✓
- Model honesty: name/size/obtain + first-run indexing + Settings AI tab + downloader + `onnxruntime` dep → Task 10 ✓
- Deferred F005/F006 documented (design §2); no cloud provider anywhere ✓
- Tests never need the real model (fake injected everywhere); real-model tests `@pytest.mark.manual` → all tasks ✓

**2. Placeholder scan:** New units (embedder + fake, embedding store, `AiSearchService`, color index, `index_element`, drop zone, tag dialog) have complete runnable code. Integration tasks (6/7/8/9/11) give complete new-method code plus concrete wiring snippets anchored to verified seams (`on_search:546`, `create_element:854`/hook `:870`, `_render_elements`, `current_filter`), naming the exact reuse point rather than leaving it open. `ClipOnnxEmbedder` real inference and `download_clip_model.py` URLs are the only intentionally-deferred pieces (model-dependent, covered by `@pytest.mark.manual`) — explicitly flagged.

**3. Type consistency:** Vectors are `np.float32` L2-normalized `(512,)` everywhere: produced by `Embedder.embed_*` (Task 1), stored/read as blobs (Task 2), consumed by `AiSearchService._rank` (Task 3), written by `index_element` (Task 5). `get_all_embeddings`/`get_all_colors` both return `(ids: list[int], matrix: np.ndarray[N, D])`, consumed identically in `_rank` and `color_search`. AI query methods return **element rows (dicts) with a `score` key** — the same shape EP2's `search_elements_advanced` returns — so `show_ai_results` → `_render_elements` reuses the EP2 surface unchanged. `suggest_tags` returns `[(tag, score)]`, consumed by `TagSuggestDialog` (Task 9). `embedder.id` (model_id) is the single identity string threaded through store/rank/missing-detection/status. Every AI method guards `self.embedder`/`ai_enabled()` and returns `[]` when `None` (Tasks 3, 6, 7), while color (Tasks 4, 8) never touches the embedder.

**Note for the executor:** EP7 assumes SP1 + SP2 + EP2 (and EP1) have landed. If running before SP1, drop the `write=` kwarg on `get_connection`. If EP2 is absent, `AiSearchService._allowed_ids` already degrades (no FilterSpec scoping) and the UI tasks reuse `_render_elements`/`current_filter`/`on_search` — read `media_display_widget.py` and `settings_panel.py` for the exact local names before editing and adjust reuse calls to the real method names. The real model is never required to pass CI: keep `FakeEmbedder` injected and mark any real-`ClipOnnxEmbedder` test `@pytest.mark.manual`. Never weaken a test to pass; mark `xfail(strict=True)` with the dependency id if a seam is genuinely absent.
