# brain/utils/embed_similarity.py
# Lightweight cached dense-embedding similarity (all-MiniLM-L6-v2, CPU).
#
# Replaces sparse token-Jaccard for semantic-similarity sites (knowledge-graph
# retrieval, memory-graph linking). Embeddings are cached per text so a given
# string is encoded at most once per process. If sentence-transformers or the
# model is unavailable (offline / not installed), every call degrades to a
# token-Jaccard score — same behaviour as before, never a crash.
from __future__ import annotations

import re
import threading
from functools import lru_cache
from typing import Optional

import numpy as np

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"   # small, fast, CPU-friendly (384-dim)
_model = None
_model_failed = False
_lock = threading.Lock()

_WORD_RE = re.compile(r"[a-z0-9]{2,}")


def _get_model():
    """Lazily load the MiniLM model once. Returns None if it can't be loaded."""
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    with _lock:
        if _model is None and not _model_failed:
            try:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(_MODEL_NAME, device="cpu")
                _log.info("embed_similarity: loaded %s", _MODEL_NAME)
            except Exception as exc:
                _model_failed = True
                _log.warning("embed_similarity: model unavailable (%s) — using Jaccard fallback", exc)
    return _model


def embeddings_available() -> bool:
    """True if dense embeddings are usable; False means callers get the Jaccard fallback."""
    return _get_model() is not None


@lru_cache(maxsize=8192)
def _embed(text: str) -> Optional[np.ndarray]:
    """L2-normalized embedding for `text`, cached. None if model unavailable."""
    model = _get_model()
    if model is None:
        return None
    try:
        vec = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return np.asarray(vec, dtype=np.float32)
    except Exception as exc:
        _log.warning("embed_similarity: encode failed (%s)", exc)
        return None


def _jaccard_text(a: str, b: str) -> float:
    ta = set(_WORD_RE.findall(a.lower()))
    tb = set(_WORD_RE.findall(b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def text_similarity(a: str, b: str) -> float:
    """
    Semantic similarity in [0, 1].
    Cosine of MiniLM embeddings when available; token-Jaccard otherwise.
    """
    if not a or not b:
        return 0.0
    va, vb = _embed(a), _embed(b)
    if va is None or vb is None:
        return _jaccard_text(a, b)
    # both L2-normalized → dot product is cosine in [-1, 1]; clamp to [0, 1]
    return float(max(0.0, min(1.0, float(np.dot(va, vb)))))
