# Finding 8 (embedding-based goal/function matching): _capability_overlap was
# pure stopword-filtered keyword overlap, which scores 0.0 for genuine
# paraphrases that share no content words ("research and investigate a topic
# by searching the web" vs. "look into quantum computing online"). It now
# blends in MiniLM cosine similarity (utils.embed_similarity) when available,
# taking the max of the two scores so embeddings can only ADD matches that
# keyword overlap missed, never remove one that already cleared the floor.
import pytest

from brain.think.think_utils.select_function import (
    _CAP_STOPWORDS,
    _capability_descriptions,
    _capability_overlap,
    _kw_overlap_score,
    _tokenize,
)
from brain.utils.embed_similarity import embeddings_available

_RESEARCH_DESC = "research and investigate a topic by searching the web and reading sources to find out information and learn about something"


def _kw_only(ref: str, goal: str) -> float:
    a = [t for t in _tokenize(ref) if t not in _CAP_STOPWORDS]
    b = [t for t in _tokenize(goal) if t not in _CAP_STOPWORDS]
    return _kw_overlap_score(" ".join(a), " ".join(b))


@pytest.mark.parametrize("ref,goal", [
    (_RESEARCH_DESC, "look into quantum computing online"),
    ("reflect on and examine my own beliefs assumptions and self model", "think about what I value"),
    ("write a new tool", "completely unrelated text about gardening"),
])
def test_capability_overlap_never_below_keyword_only_score(ref, goal):
    assert _capability_overlap(ref, goal) >= _kw_only(ref, goal) - 1e-9


@pytest.mark.skipif(not embeddings_available(), reason="requires sentence-transformers/MiniLM")
def test_capability_overlap_finds_lexical_paraphrase_via_embeddings():
    ref = _capability_descriptions().get("research_topic") or _RESEARCH_DESC
    # Shares only "topic" with `ref` after stopword filtering -> keyword
    # overlap alone is weak, well under the semantic floor.
    goal = "look into quantum computing as a topic"
    kw = _kw_only(ref, goal)
    overlap = _capability_overlap(ref, goal)
    from brain.config.tuning import SEMANTIC_MATCH_FLOOR
    assert kw < SEMANTIC_MATCH_FLOOR
    # The embedder recognises "research ... searching the web" ~ "look into".
    assert overlap > kw
    assert overlap >= SEMANTIC_MATCH_FLOOR


@pytest.mark.skipif(not embeddings_available(), reason="requires sentence-transformers/MiniLM")
def test_capability_overlap_unrelated_text_stays_below_semantic_floor():
    ref = _capability_descriptions().get("research_topic") or _RESEARCH_DESC
    goal = "organize my desk and clean the kitchen"
    from brain.config.tuning import SEMANTIC_MATCH_FLOOR
    assert _capability_overlap(ref, goal) < SEMANTIC_MATCH_FLOOR
