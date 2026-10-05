# goals/handlers/research_claims.py
# Slice 1C.0 (RUN12): the structured research product — extracted from research.py
# (module-size decomposition; research.py re-exports for existing import paths).
#
# The structured-knowledge keystone (governing decision 2026-07-21): every completed
# research goal writes a claims.json beside the memo — extracted propositions
# (entities / relations / an optional telemetry-checkable prediction / sources),
# pulled symbolically from the SAME fetched documents; no sentence generation. The
# memo .md is a rendering layer on top of this; close-out and reuse (Slice 1C.2 /
# 1C.4) score the claims, not prose.
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from brain.utils.subject_terms import mentions, subject_terms

from ..model import Goal

_CLAIM_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "that",
    "this", "it", "its", "is", "are", "was", "were", "be", "been", "as", "at", "by",
    "from", "about", "into", "what", "how", "why", "which", "more", "deeply",
    "understand", "not", "obvious", "something", "new", "learn", "know",
}

# A relation sentence: "<subject> <predicate> <object>" for a small set of
# knowledge-bearing predicates. Deliberately conservative — a miss is fine (we keep
# only high-confidence extractions), a false relation is not.
_REL_RE = re.compile(
    r"\b([A-Za-z][\w\-][\w\- ]{1,58}?)\s+"
    r"(is an?|is the|is|are|was|were|means|refers to|is defined as|is called|"
    r"causes?|caused by|leads to|results in|consists? of|is a type of|is part of|"
    r"is used (?:for|to)|enables?|prevents?|produces?|requires?)\s+"
    r"([A-Za-z][\w\-][\w\- ]{1,78}?)\s*[.,;:]",
    re.IGNORECASE,
)


def _claim_subject_terms(text: str) -> List[str]:
    # Run 12 §3: the shared, scaffold-stopped definition (a question template's
    # "did/get/wrong" are not its subject).
    return [w for w in subject_terms(text) if w not in _CLAIM_STOP]


def _extract_claims(goal: Goal, snippets: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Slice 1C.0: symbolically extract a structured research product from the fetched
    documents. Returns {question, subject_terms, entities, relations, prediction,
    sources, ts}. Best-effort and side-effect-free; keeps only relations that touch
    the question's subject so the product answers the gap, not the topic in general."""
    spec = goal.spec or {}
    question = str(spec.get("question") or goal.title or "")
    subject = _claim_subject_terms(question) or _claim_subject_terms(goal.title or "")
    sources = [{"src": str(src)[:200]} for (src, _t) in snippets]

    entities: List[str] = []
    relations: List[Dict[str, str]] = []
    seen_rel: set[tuple[str, str, str]] = set()
    for src, txt in snippets:
        if len(relations) >= 12:
            break
        for sent in re.split(r"(?<=[.!?])\s+", str(txt or "")):
            m = _REL_RE.search(sent)
            if not m:
                continue
            s = " ".join(m.group(1).split())
            p = " ".join(m.group(2).lower().split())
            o = " ".join(m.group(3).split())
            sl, ol = s.lower(), o.lower()
            # Only claims that touch the question's subject count as answering it.
            if subject and not mentions(subject, f"{s} {o}"):
                continue
            key = (sl[:40], p, ol[:40])
            if key in seen_rel:
                continue
            seen_rel.add(key)
            relations.append({"subject": s[:80], "predicate": p,
                              "object": o[:80], "source": str(src)[:200]})
            for e in (s, o):
                if e and e not in entities:
                    entities.append(e[:80])
            if len(relations) >= 12:
                break

    # Predictions are minted only for characterization / telemetry-checkable goals,
    # which carry a `prediction` spec (RUN12 open-decision 3: relations+concepts
    # universal, predictions only where a claim can be checked against telemetry).
    prediction = None
    pspec = spec.get("prediction")
    if isinstance(pspec, dict) and pspec.get("claim"):
        prediction = {
            "claim": str(pspec.get("claim"))[:200],
            "checkable_against": str(pspec.get("checkable_against") or "")[:80],
            "confidence": float(pspec.get("confidence") or 0.5),
            "resolved": False,    # brain-side prediction_engine resolves it next cycle
            "correct": None,
        }

    return {
        "question": question[:200],
        "subject_terms": subject[:12],
        "entities": entities[:16],
        "relations": relations,
        "prediction": prediction,
        "sources": sources,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
