"""
cognition/concept_memory.py

Persistent semantic memory: structured concept definitions Orrin can query
without an LLM. Backed by brain/data/concepts.json.

Provides:
  lookup(word)               → dict or None
  query(text, limit)         → list of matching concept dicts
  learn(word, ...)           → persist a new or updated concept
  get_context_for_prompt(text) → formatted string for inner loop injection
"""
from __future__ import annotations
from core.runtime_log import get_logger

import re
from typing import Any, Dict, List, Optional

from utils.json_utils import load_json, save_json
_log = get_logger(__name__)

from brain.paths import DATA_DIR
from utils.failure_counter import record_failure
_CONCEPTS_PATH = DATA_DIR / "concepts.json"
_KB_PATH = DATA_DIR / "knowledge_base.json"
_concepts_cache: Optional[Dict[str, Any]] = None
_cache_mtime: float = 0.0
_kb_cache: Optional[list] = None
_kb_mtime: float = 0.0

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
    "my", "your", "his", "its", "our", "their", "that", "this", "these",
    "those", "what", "which", "who", "how", "when", "where", "why", "and",
    "or", "but", "so", "if", "of", "in", "on", "at", "to", "for", "with",
    "by", "from", "as", "do", "did", "does", "have", "has", "had", "not",
    "no", "can", "will", "just", "about", "also", "than", "then", "there",
})


def _load() -> Dict[str, Any]:
    global _concepts_cache, _cache_mtime
    try:
        mtime = _CONCEPTS_PATH.stat().st_mtime
        if _concepts_cache is not None and mtime == _cache_mtime:
            return _concepts_cache
        raw = load_json(_CONCEPTS_PATH, default_type=dict) or {}
        _concepts_cache = {k: v for k, v in raw.items() if not k.startswith("_")}
        _cache_mtime = mtime
    except Exception:
        if _concepts_cache is None:
            _concepts_cache = {}
    return _concepts_cache


def _load_kb() -> list:
    global _kb_cache, _kb_mtime
    try:
        mtime = _KB_PATH.stat().st_mtime
        if _kb_cache is not None and mtime == _kb_mtime:
            return _kb_cache
        _kb_cache = load_json(_KB_PATH, default_type=list) or []
        _kb_mtime = mtime
    except Exception:
        if _kb_cache is None:
            _kb_cache = []
    return _kb_cache


def _invalidate() -> None:
    global _concepts_cache
    _concepts_cache = None


def lookup(word: str) -> Optional[Dict[str, Any]]:
    """Direct concept lookup by exact word (case-insensitive). Returns None if not found."""
    if not word:
        return None
    key = word.strip().lower()
    concepts = _load()
    entry = concepts.get(key)
    if entry is None:
        return None
    return {"word": key, **entry}


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]


def _score(entry: Dict[str, Any], tokens: List[str], word: str) -> float:
    """Score a concept entry's relevance to the query tokens."""
    score = 0.0
    if word in tokens:
        score += 3.0
    definition = (entry.get("definition") or "").lower()
    is_a = [x.lower() for x in (entry.get("is_a") or [])]
    related = [x.lower() for x in (entry.get("related") or [])]
    for tok in tokens:
        if tok == word:
            continue
        if tok in is_a:
            score += 2.0
        elif tok in related:
            score += 1.5
        elif tok in definition:
            score += 0.5
    return score


def query(text: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Return up to `limit` concepts relevant to the given text, ranked by relevance."""
    if not text:
        return []
    tokens = _tokenize(text)
    if not tokens:
        return []
    concepts = _load()
    scored = []
    for word, entry in concepts.items():
        s = _score(entry, tokens, word)
        if s > 0:
            scored.append((s, word, entry))
    scored.sort(key=lambda x: -x[0])
    return [{"word": w, **e} for _, w, e in scored[:limit]]


def learn(
    word: str,
    definition: str,
    is_a: Optional[List[str]] = None,
    related: Optional[List[str]] = None,
    source: str = "conversation",
) -> None:
    """Persist a new or updated concept to concepts.json."""
    if not word or not definition:
        return
    key = word.strip().lower()
    concepts = _load()
    existing = concepts.get(key) or {}
    merged_is_a = list({*existing.get("is_a", []), *(is_a or [])})
    merged_related = list({*existing.get("related", []), *(related or [])})
    concepts[key] = {
        "definition": definition.strip(),
        "is_a": merged_is_a,
        "related": merged_related,
        "source": source,
    }
    try:
        raw = load_json(_CONCEPTS_PATH, default_type=dict) or {}
        raw[key] = concepts[key]
        save_json(_CONCEPTS_PATH, raw)
        _invalidate()
        try:  # surface into the Brain Memory Inspector (concept store)
            from backend.telemetry_bridge import mirror_memory as _mm
            _mm("write", store="concept", key=key, summary=definition.strip())
        except Exception:
            pass
    except Exception as _e:
        record_failure("concept_memory.learn", _e)


_IS_A_PATTERNS = [
    re.compile(r'\b(\w+)\s+is\s+a(?:n)?\s+([a-z][a-z\s]{1,30})', re.I),
    re.compile(r'\b(\w+)\s+are\s+([a-z][a-z\s]{1,30})', re.I),
    re.compile(r'\ba\s+(\w+)\s+is\s+([a-z][a-z\s]{1,40})', re.I),
]


def learn_from_text(text: str, source: str = "conversation") -> None:
    """
    Extract definitional patterns ("X is a Y") from text and persist new concepts.
    Only learns words not already in the store.
    """
    if not text:
        return
    if "[EXTERNAL" in text:
        from utils.content_quarantine import strip_quarantine
        text = strip_quarantine(text)
    concepts = _load()
    for pattern in _IS_A_PATTERNS:
        for m in pattern.finditer(text):
            subject = m.group(1).strip().lower()
            predicate = m.group(2).strip().lower().rstrip(".,;")
            if (len(subject) < 3 or subject in _STOPWORDS
                    or subject in concepts
                    or len(predicate) < 3):
                continue
            category = predicate.split()[0] if predicate.split() else ""
            learn(
                word=subject,
                definition=f"{subject.capitalize()} is a {predicate}.",
                is_a=[category] if category and category not in _STOPWORDS else [],
                source=source,
            )


def _kb_query(tokens: list, limit: int = 2) -> list:
    """Search knowledge_base.json for entries relevant to the query tokens."""
    kb = _load_kb()
    scored = []
    token_set = set(tokens)
    for entry in kb:
        if not isinstance(entry, dict):
            continue
        tags = set(t.lower() for t in (entry.get("tags") or []))
        content_tokens = set(re.findall(r"[a-z]{3,}", (entry.get("content") or "").lower()))
        overlap_tags = len(token_set & tags)
        overlap_content = len(token_set & content_tokens)
        score = overlap_tags * 2.0 + overlap_content * 0.5
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def get_context_for_prompt(text: str, limit: int = 4) -> str:
    """
    Return a compact string of relevant concept definitions and world facts
    for inner loop injection. Searches both concepts.json and knowledge_base.json.
    Returns empty string if nothing relevant found.
    """
    tokens = _tokenize(text)
    if not tokens:
        return ""

    sections = []

    # Concept definitions
    matches = query(text, limit=limit)
    if matches:
        lines = []
        for m in matches:
            word = m["word"]
            defn = m.get("definition", "")
            is_a = m.get("is_a", [])
            if is_a:
                lines.append(f"{word} ({', '.join(is_a[:2])}): {defn}")
            else:
                lines.append(f"{word}: {defn}")
        sections.append("Concepts:\n" + "\n".join(lines))

    # World knowledge facts
    kb_matches = _kb_query(tokens, limit=2)
    if kb_matches:
        facts = [e.get("content", "") for e in kb_matches if e.get("content")]
        if facts:
            sections.append("Facts:\n" + "\n".join(facts))

    return "\n".join(sections) if sections else ""
