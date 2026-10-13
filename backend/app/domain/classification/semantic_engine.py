"""Semantic tier: sentence-transformers cosine similarity to reference examples.

Lazy model load (first classification in the worker pays the ~2s cost),
thread-safe, and it degrades to the lexical scorer when sentence-transformers
or torch is not installed (lightweight mode / dev laptops).
"""

import logging
import threading

from app.core.config import settings
from app.core.enums import RiskCategory
from app.domain.classification.registry import SEMANTIC_CATEGORIES, lexical_scores, reference_examples

logger = logging.getLogger("aidlp.classification.semantic")

_model = None
_model_failed = False
_ref_embeddings: dict[str, object] = {}  # category -> numpy matrix
_lock = threading.Lock()


def _load_model():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    with _lock:
        if _model is not None or _model_failed:
            return _model
        if not settings.semantic_enabled:
            _model_failed = True
            logger.info("Semantic tier disabled by SEMANTIC_ENABLED=false")
            return None
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(settings.semantic_model)
            logger.info("Loaded embedding model %s", settings.semantic_model)
        except Exception as exc:
            _model_failed = True
            logger.warning("sentence-transformers unavailable, lexical fallback active (%s: %s)",
                           type(exc).__name__, exc)
    return _model


def _reference_texts(category: str) -> list[str]:
    spec = reference_examples()[category]
    return list(spec["examples"]) + [kw.strip() for kw in spec["keywords"] if len(kw.strip()) > 3]


def _ensure_reference_embeddings(model, np) -> None:
    if _ref_embeddings:
        return
    with _lock:
        if _ref_embeddings:
            return
        for cat in SEMANTIC_CATEGORIES:
            texts = _reference_texts(cat.value)
            if not texts:
                continue
            emb = model.encode(texts, normalize_embeddings=True)
            _ref_embeddings[cat.value] = emb


def semantic_scores(text: str) -> dict[RiskCategory, float]:
    """Per-category similarity in [0, 1]; falls back to lexical scoring."""
    model = _load_model()
    if model is None:
        return lexical_scores(text)
    try:
        import numpy as np

        _ensure_reference_embeddings(model, np)
        query = model.encode([text], normalize_embeddings=True)[0]
        scores: dict[RiskCategory, float] = {}
        for cat in SEMANTIC_CATEGORIES:
            refs = _ref_embeddings.get(cat.value)
            if refs is None or len(refs) == 0:
                scores[cat] = 0.0
                continue
            sims = np.asarray(refs) @ query  # vectors are L2-normalised → cosine
            scores[cat] = round(float(np.clip(sims.max(), 0.0, 1.0)), 4)
        return scores
    except Exception as exc:
        logger.warning("Embedding failed (%s: %s); using lexical scores", type(exc).__name__, exc)
        return lexical_scores(text)


def engines_active() -> tuple[bool, bool]:
    """(presidio available, semantic model loaded-or-loadable) — used for /health."""
    from app.domain.classification.presidio_engine import engine as presidio

    presidio._ensure()
    return presidio.available, _model is not None
