# brain/symbolic/analogy_engine.py
# Structural analogy matching — find past problems with similar structure and
# map their solutions to the current context.
#
# Two-tier scoring:
#
#   Tier 1 — Surface (Jaccard, cheap):
#     Bag-of-words overlap to shortlist candidates quickly.
#
#   Tier 2 — Structural (graph isomorphism proxy + goal similarity):
#     a) SPO extraction: pull (Subject, Predicate, Object) triples from text.
#        Two problems are structurally analogous if their SPO graphs share the
#        same RELATION TYPE even when subjects/objects differ.
#        e.g. "X blocks Y" ≅ "A prevents B" — both are OBSTRUCTION relations.
#     b) Goal/intent type: classify both query and memory into intent buckets
#        (HOW-TO, WHY, WHAT-IS, COMPARE, DEBUG, DESIGN, PLAN).
#        Same intent type = structural bonus regardless of surface words.
#     c) Outcome polarity: memories with resolved/positive outcome score higher
#        because their mapped solution is more likely to transfer.
#
# Final score = 0.35*jaccard + 0.40*structural + 0.25*goal_sim
# Threshold 0.15 to surface a result; 0.30 to trust it for routing.
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Set, Tuple

from utils.json_utils import load_json
from utils.log import log_activity
from brain.paths import LONG_MEMORY_FILE

_STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "this", "that", "these",
    "those", "it", "its", "i", "me", "my", "we", "you", "he", "she",
    "they", "what", "which", "who", "how", "when", "where", "why",
}

_CACHE: List[Dict] = []
_CACHE_TS: float = 0.0
_CACHE_TTL: float = 300.0

# ─── Intent type classification ───────────────────────────────────────────────
# Each entry: (pattern, intent_label)
_INTENT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bhow (do|can|should|to)\b", re.IGNORECASE), "HOW_TO"),
    (re.compile(r"\bwhy (does|did|is|are|do)\b", re.IGNORECASE), "WHY"),
    (re.compile(r"\bwhat (is|are|was|were)\b", re.IGNORECASE), "WHAT_IS"),
    (re.compile(r"\b(compare|difference|versus|vs\.?|contrast)\b", re.IGNORECASE), "COMPARE"),
    (re.compile(r"\b(debug|fix|error|bug|fail|broken|crash)\b", re.IGNORECASE), "DEBUG"),
    (re.compile(r"\b(design|architect|structure|pattern|build)\b", re.IGNORECASE), "DESIGN"),
    (re.compile(r"\b(plan|next step|should i|what to do|approach)\b", re.IGNORECASE), "PLAN"),
]

# ─── Relation type vocabulary for SPO extraction ──────────────────────────────
# Maps verb clusters to abstract relation types.
_RELATION_MAP: Dict[str, str] = {
    "cause":   "CAUSES", "causes": "CAUSES", "caused": "CAUSES",
    "prevent": "BLOCKS", "prevents": "BLOCKS", "block": "BLOCKS", "blocks": "BLOCKS",
    "enable":  "ENABLES", "enables": "ENABLES", "allow": "ENABLES", "allows": "ENABLES",
    "require": "REQUIRES", "requires": "REQUIRES", "need": "REQUIRES", "needs": "REQUIRES",
    "improve": "IMPROVES", "improves": "IMPROVES", "help": "IMPROVES", "helps": "IMPROVES",
    "reduce":  "REDUCES", "reduces": "REDUCES", "decrease": "REDUCES",
    "increase": "INCREASES", "increases": "INCREASES",
    "contain": "CONTAINS", "contains": "CONTAINS", "include": "CONTAINS",
    "use":     "USES", "uses": "USES", "using": "USES",
    "define":  "DEFINES", "defines": "DEFINES", "mean": "MEANS", "means": "MEANS",
    "fail":    "FAILS", "fails": "FAILS", "break": "FAILS", "breaks": "FAILS",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _intent_type(text: str) -> str:
    for pattern, label in _INTENT_PATTERNS:
        if pattern.search(text):
            return label
    return "GENERAL"


def _extract_relations(text: str) -> Set[str]:
    """
    Extract abstract relation types present in text.
    Returns a set of relation type strings like {"CAUSES", "REQUIRES"}.
    This is a lightweight proxy for full SPO parsing — same relation type
    across two texts signals structural analogy.
    """
    found: Set[str] = set()
    words = re.findall(r"[a-z]+", text.lower())
    for w in words:
        rel = _RELATION_MAP.get(w)
        if rel:
            found.add(rel)
    return found


def _structural_score(q_relations: Set[str], m_relations: Set[str]) -> float:
    """Jaccard over abstract relation types — structural isomorphism proxy."""
    return _jaccard(q_relations, m_relations) if (q_relations or m_relations) else 0.0


def _goal_sim_score(q_intent: str, m_intent: str) -> float:
    if q_intent == m_intent:
        return 1.0
    # Partial credit for related intent types
    _RELATED = {
        ("HOW_TO", "PLAN"): 0.6,
        ("PLAN", "HOW_TO"): 0.6,
        ("DEBUG", "HOW_TO"): 0.4,
        ("WHAT_IS", "WHY"): 0.4,
        ("WHY", "WHAT_IS"): 0.4,
        ("DESIGN", "PLAN"): 0.5,
        ("PLAN", "DESIGN"): 0.5,
    }
    return _RELATED.get((q_intent, m_intent), 0.0)


def _load_memories() -> List[Dict]:
    global _CACHE, _CACHE_TS
    if _CACHE and (time.time() - _CACHE_TS) < _CACHE_TTL:
        return _CACHE
    raw = load_json(LONG_MEMORY_FILE, default_type=list) or []
    _CACHE = [e for e in raw if isinstance(e, dict) and e.get("content")]
    _CACHE_TS = time.time()
    return _CACHE


def _score_memory(
    mem: Dict,
    q_toks: Set[str],
    q_relations: Set[str],
    q_intent: str,
) -> float:
    content = mem.get("content", "")
    m_toks = _tokenize(content)
    m_relations = _extract_relations(content)
    m_intent = _intent_type(content)

    surface = _jaccard(q_toks, m_toks)
    structural = _structural_score(q_relations, m_relations)
    goal_sim = _goal_sim_score(q_intent, m_intent)

    score = 0.35 * surface + 0.40 * structural + 0.25 * goal_sim

    # Outcome polarity boost
    event_type = mem.get("event_type", "")
    if event_type in ("goal_closed", "skill_synthesis", "dream_insight"):
        score *= 1.15
    elif event_type in ("failure", "error"):
        score *= 0.80  # failures still useful but penalised slightly

    return round(min(score, 1.0), 3)


# ─── Public API ───────────────────────────────────────────────────────────────

def find_analogues(
    query: str,
    *,
    top_n: int = 3,
    min_score: float = 0.15,
) -> List[Dict]:
    """
    Return up to `top_n` long-memory entries structurally analogous to `query`.
    Each result has: content, score, emotion, event_type, mapped_solution,
                     structural_relations, intent_type.
    """
    q_toks = _tokenize(query)
    if not q_toks:
        return []
    q_relations = _extract_relations(query)
    q_intent = _intent_type(query)

    memories = _load_memories()
    scored: List[Tuple[float, Dict]] = []

    try:
        from utils.text_sanity import is_corrupt_text as _ict
    except Exception:
        _ict = None

    for mem in memories:
        # Quarantine (Phase 1.4): corrupted memory text (chunk headers,
        # truncation artifacts) must not become an analogy source.
        if _ict is not None and _ict(str(mem.get("content", ""))):
            continue
        s = _score_memory(mem, q_toks, q_relations, q_intent)
        if s >= min_score:
            scored.append((s, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, mem in scored[:top_n]:
        results.append({
            "content": mem.get("content", ""),
            "score": score,
            "emotion": mem.get("emotion", ""),
            "event_type": mem.get("event_type", ""),
            "mapped_solution": _extract_solution(mem),
            "structural_relations": sorted(_extract_relations(mem.get("content", ""))),
            "intent_type": _intent_type(mem.get("content", "")),
        })

    if results:
        log_activity(
            f"[analogy] {len(results)} analogues (intent={q_intent}, "
            f"relations={sorted(q_relations)}, top={results[0]['score']})"
        )
    return results


def _extract_solution(mem: Dict) -> str:
    content = mem.get("content", "")
    for marker in ("solution:", "→", "resolved by", "answered by", "worked because",
                   "the fix was", "to fix this"):
        idx = content.lower().find(marker)
        if idx != -1:
            return content[idx + len(marker):].strip()[:300]
    return content[:300]


def best_analogue_answer(query: str) -> Optional[str]:
    """
    Return a formatted analogy-based suggestion, or None if nothing useful.
    Requires structural score >= 0.30 to avoid low-quality surface matches.
    """
    analogues = find_analogues(query, top_n=1, min_score=0.30)
    if not analogues:
        return None
    a = analogues[0]
    solution = a["mapped_solution"]
    if len(solution) < 20:
        return None
    intent = a.get("intent_type", "")
    rels = ", ".join(a.get("structural_relations", [])[:3])
    header = f"[analogy/{intent}]" + (f" [{rels}]" if rels else "")
    return f"{header} Similar situation (score={a['score']}): {solution}"
