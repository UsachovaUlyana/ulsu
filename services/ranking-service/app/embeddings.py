"""Semantic similarity for interests using Word2Vec embeddings (Russian).

Model: NLPL #184 — Russian Wikipedia word2vec with UPOS tags.
Words are stored as lemma_POS (e.g. "музыка_NOUN", "играть_VERB").
We use pymorphy2 to lemmatise user-supplied interests before lookup.
"""

from __future__ import annotations

import os
from typing import cast

import numpy as np
from shared.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL_PATH = "/app/models/model.bin"
MODEL_PATH = os.environ.get("W2V_MODEL_PATH", DEFAULT_MODEL_PATH)

SIMILARITY_THRESHOLD = 0.35
VOCAB_LIMIT = 30_000

_kv = None
_morph = None


def _load_model():
    """Lazy-load word2vec model. Returns None if unavailable."""
    global _kv
    if _kv is not None:
        return _kv
    if not os.path.exists(MODEL_PATH):
        logger.warning("word2vec_model_not_found", path=MODEL_PATH)
        return None
    try:
        from gensim.models import KeyedVectors

        logger.info("loading_word2vec_model", path=MODEL_PATH, limit=VOCAB_LIMIT)
        _kv = KeyedVectors.load_word2vec_format(
            MODEL_PATH, binary=True, limit=VOCAB_LIMIT
        )
        logger.info("word2vec_model_loaded", vocab_size=len(_kv.key_to_index))
        return _kv
    except Exception:
        logger.exception("word2vec_load_failed")
        return None


def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3

        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def _upos_tag(pymorphy_tag) -> str | None:
    """Convert pymorphy2 tag to Universal POS tag used by the model."""
    if "NOUN" in pymorphy_tag:
        return "NOUN"
    if "VERB" in pymorphy_tag or "INFN" in pymorphy_tag:
        return "VERB"
    if "ADJF" in pymorphy_tag or "ADJS" in pymorphy_tag:
        return "ADJ"
    if "ADVB" in pymorphy_tag:
        return "ADV"
    if "NUMR" in pymorphy_tag:
        return "NUM"
    if "NPRO" in pymorphy_tag:
        return "PRON"
    if "PROPN" in pymorphy_tag:
        return "PROPN"
    return None


def _vector_for(word: str):
    """Return the vector for a word, or None if OOV."""
    kv = _load_model()
    if kv is None:
        return None

    w = word.lower().strip()
    if w in kv.key_to_index:
        return cast(np.ndarray, kv[w])

    # Try lemma + POS via pymorphy2
    try:
        morph = _get_morph()
        parsed = morph.parse(w)
        if not parsed:
            return None
        p = parsed[0]
        lemma = p.normal_form
        pos = _upos_tag(p.tag)
        if pos:
            key = f"{lemma}_{pos}"
            if key in kv.key_to_index:
                return cast(np.ndarray, kv[key])
    except Exception:
        pass

    return None


def word_similarity(w1: str, w2: str) -> float:
    """Cosine similarity between two words. Returns 0.0 if either is OOV."""
    if w1.lower().strip() == w2.lower().strip():
        return 1.0
    v1 = _vector_for(w1)
    v2 = _vector_for(w2)
    if v1 is None or v2 is None:
        return 0.0
    dot = float(np.dot(v1, v2))
    norm = float(np.linalg.norm(v1) * np.linalg.norm(v2))
    if norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / norm))


def semantic_interest_boost(viewer_interests, candidate_interests) -> float:
    """Compute semantic overlap bonus using word embeddings.

    For every interest of the viewer we try to find the most similar
    interest of the candidate. If the best similarity exceeds the
    threshold we count it as a match. The bonus is capped at +0.15
    (same cap as the old exact-match algorithm).
    """
    if not viewer_interests or not candidate_interests:
        return 0.0

    # Fast path: if model is missing, fall back to exact matching
    kv = _load_model()
    if kv is None:
        a = {x.lower() for x in viewer_interests}
        b = {x.lower() for x in candidate_interests}
        overlap = len(a & b)
        if not overlap:
            return 0.0
        return overlap / max(len(viewer_interests), len(candidate_interests))

    matched = 0
    seen = set()
    for vi in viewer_interests:
        best_sim = 0.0
        best_ci = None
        for ci in candidate_interests:
            if ci in seen:
                continue
            sim = word_similarity(vi, ci)
            if sim > best_sim:
                best_sim = sim
                best_ci = ci
        if best_sim >= SIMILARITY_THRESHOLD:
            matched += 1
            if best_ci is not None:
                seen.add(best_ci)

    if not matched:
        return 0.0
    return matched / max(len(viewer_interests), len(candidate_interests))
