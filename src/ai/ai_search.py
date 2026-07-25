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
