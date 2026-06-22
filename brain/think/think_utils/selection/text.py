"""Text / keyword-overlap utilities for selection (Phase 4D, from
select_function.py).

Pure string helpers: tokenization, soft keyword overlap, and the
capability<->goal match score (keyword overlap on content words, raised by
MiniLM cosine similarity when the embedder is available). No dependency on the
selector's manifest caches or constant graph. `_capability_overlap` is
re-exported from select_function for its many external importers.
"""
from __future__ import annotations

import re
from typing import List

from brain.utils.embed_similarity import embeddings_available, text_similarity


def _tokenize(text: str) -> List[str]:
    if not isinstance(text, str) or not text:
        return []
    return re.findall(r"[a-z0-9]+", text.lower())


def _kw_overlap_score(candidate_text: str, ref_text: str) -> float:
    """soft keyword overlap in [0..1]. Works even if defs are short."""
    a = set(_tokenize(candidate_text))
    b = set(_tokenize(ref_text))
    if not a or not b:
        return 0.0
    inter = len(a & b)
    denom = (len(a) ** 0.5) * (len(b) ** 0.5)
    return inter / denom if denom else 0.0


# Function words that carry no capability signal. Plain _kw_overlap_score was
# inflated by these shared tokens (a goal and an unrelated description both
# contain "the"/"and"), which mis-ranked the goal→capability recruitment. The
# capability matcher below strips them so the match keys off CONTENT words only.
_CAP_STOPWORDS: frozenset = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "with", "is", "are", "be", "am", "my", "i", "me", "it", "its", "that",
    "this", "what", "how", "do", "does", "into", "from", "about", "as", "so",
    "if", "up", "out", "over", "than", "then", "they", "them", "have", "has",
    "had", "not", "no", "will", "would", "can", "could", "more", "most", "some",
    "any", "all", "you", "your", "he", "she", "we", "us", "our", "their",
})


def _capability_overlap(ref_text: str, goal_text: str) -> float:
    """Capability↔goal match score in [0, 1] (function_selection_fix_v2.md
    §4.1/§4.2; Finding 8 — replaces pure keyword overlap with embedding
    similarity where available).

    Returns the MAX of:
      - stopword-filtered keyword overlap (the original heuristic, on content
        words only, so it's driven by topical terms like research/reflect/
        beliefs/novelty rather than shared function words), and
      - MiniLM cosine similarity between the raw texts, when the embedder is
        available (utils.embed_similarity).

    Taking the max means embeddings can only ADD matches that keyword overlap
    missed (true synonyms/paraphrases — "investigate" vs. "research_topic"),
    never remove a match that already cleared the keyword floor. When the
    embedder is unavailable this degrades to exactly the prior keyword-only
    behavior, never a crash.
    """
    a = [t for t in _tokenize(ref_text) if t not in _CAP_STOPWORDS]
    b = [t for t in _tokenize(goal_text) if t not in _CAP_STOPWORDS]
    kw_score = _kw_overlap_score(" ".join(a), " ".join(b))
    if embeddings_available():
        kw_score = max(kw_score, text_similarity(ref_text, goal_text))
    return kw_score
