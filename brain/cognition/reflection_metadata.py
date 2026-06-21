"""
cognition/reflection_metadata.py

Structured evidence metadata for reflective claims.

The risk: constant self-reflection on its own outputs creates closed-loop
narrative reinforcement. False or emotionally comfortable stories can
stabilize because nothing challenges them.

Fix: every reflective claim that enters long memory should carry:
  - evidence_sources: what it was derived from (WM entries, goal history, etc.)
  - confidence: 0.0–1.0 derived from source quality and recency
  - known_counterexamples: list of WM entries that contradict this claim
  - validation_status: "unvalidated" | "partially_validated" | "validated" | "refuted"
  - grounding_needed: True if external validation is recommended

This module provides:
  - `wrap_reflective_claim(text, context)` — adds metadata to a claim dict
  - `store_reflective_claim(text, context, ...)` — write to long memory with metadata
  - `audit_reflective_claims()` — scan recent reflection entries for weak claims

The validation_status starts "unvalidated" and is upgraded by prediction
outcomes, user signals, or contradiction resolution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.utils.log import log_private

_CONFIDENCE_SOURCES = {
    "working_memory": 0.40,    # derived from WM — recent but volatile
    "long_memory":    0.60,    # derived from LM — older but survived consolidation
    "goal_history":   0.65,    # derived from completed/failed goals — observable
    "user_signal":    0.80,    # user explicitly confirmed or contradicted
    "prediction_hit": 0.75,    # a prediction based on this was later correct
    "dream_insight":  0.45,    # dream processing — heuristic, not validated
    "empirical":      0.85,    # from experimentation.py with measured outcome
}


def wrap_reflective_claim(
    claim_text: str,
    context: Dict[str, Any],
    sources: Optional[List[str]] = None,
    counterexample_search: bool = True,
) -> Dict[str, Any]:
    """
    Attach structured metadata to a reflective claim string.

    Returns a dict with 'content' + metadata fields ready for long_memory.
    """
    sources = sources or ["working_memory"]
    confidence = max(
        (_CONFIDENCE_SOURCES.get(s, 0.3) for s in sources),
        default=0.3,
    )

    # Search recent WM for potential counterexamples
    counterexamples: List[str] = []
    if counterexample_search:
        claim_lower = claim_text.lower()
        claim_words = {w for w in claim_lower.split() if len(w) > 4}
        wm = context.get("working_memory") or []
        for entry in (wm or [])[-20:]:
            txt = str(entry.get("content", "") if isinstance(entry, dict) else entry)
            # Look for negation of key claim words
            negation_markers = ["not ", "doesn't ", "never ", "failed", "wrong", "incorrect"]
            if any(word in claim_lower for word in claim_words):
                if any(marker in txt.lower() for marker in negation_markers):
                    overlap = sum(1 for w in claim_words if w in txt.lower())
                    if overlap >= 2:
                        counterexamples.append(txt[:100])

    # Grounding needed when confidence is low or no external source
    grounding_needed = (
        confidence < 0.55
        or all(s in ("working_memory", "dream_insight") for s in sources)
    )

    return {
        "content": claim_text,
        "event_type": "reflection",
        "metadata": {
            "evidence_sources": sources,
            "confidence": round(confidence, 3),
            "known_counterexamples": counterexamples[:3],
            "validation_status": "unvalidated",
            "grounding_needed": grounding_needed,
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        },
        "importance": 3 if confidence > 0.55 else 2,
        "priority": 2,
    }


def store_reflective_claim(
    claim_text: str,
    context: Dict[str, Any],
    sources: Optional[List[str]] = None,
    emotion: str = "reflective",
    importance: int = 3,
) -> Dict[str, Any]:
    """
    Wrap a reflective claim and write it to long memory with metadata.
    Returns the wrapped entry.
    """
    wrapped = wrap_reflective_claim(claim_text, context, sources=sources)
    wrapped["emotion"] = emotion
    wrapped["importance"] = importance

    try:
        from brain.cog_memory.long_memory import update_long_memory
        update_long_memory(
            claim_text,
            emotion=emotion,
            event_type="reflection",
            importance=importance,
            priority=2,
            context=context,
        )
        # Also write metadata-rich version to WM so current cycle can see it
        from brain.cog_memory.working_memory import update_working_memory
        meta = wrapped.get("metadata", {})
        conf = meta.get("confidence", 0.0)
        grounding = meta.get("grounding_needed", False)
        flag = " [needs grounding]" if grounding else ""
        update_working_memory({
            "content": f"[reflection/claim conf={conf:.2f}{flag}] {claim_text[:200]}",
            "event_type": "reflection_metadata",
            "importance": 2,
            "priority": 2,
        })
    except Exception as e:
        log_private(f"[reflection_metadata] storage failed: {e}")

    return wrapped


def audit_reflective_claims(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scan recent long-memory reflection entries and flag weak/ungrounded ones.
    Returns list of entries that need external grounding.
    """
    try:
        from brain.utils.json_utils import load_json
        from brain.paths import LONG_MEMORY_FILE
        lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
        weak = []
        for entry in (lm or [])[-50:]:
            if not isinstance(entry, dict):
                continue
            if entry.get("event_type") != "reflection":
                continue
            meta = entry.get("metadata") or {}
            if not meta:
                # No metadata at all — pre-metadata entry, flag for review
                weak.append({**entry, "_audit": "no_metadata"})
                continue
            if meta.get("validation_status") == "unvalidated" and meta.get("grounding_needed"):
                weak.append({**entry, "_audit": "grounding_needed"})
        return weak
    except Exception:
        return []


def validate_claim(claim_id: str, status: str, evidence: str = "") -> bool:
    """
    Update validation_status of a reflection entry in long memory.
    status: "partially_validated" | "validated" | "refuted"
    Returns True on success.
    """
    if status not in ("partially_validated", "validated", "refuted"):
        return False
    try:
        from brain.utils.json_utils import load_json, save_json
        from brain.paths import LONG_MEMORY_FILE
        lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
        updated = False
        for entry in lm:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("id") or "") == claim_id:
                meta = entry.setdefault("metadata", {})
                meta["validation_status"] = status
                if evidence:
                    meta["validation_evidence"] = evidence[:200]
                updated = True
                break
        if updated:
            save_json(LONG_MEMORY_FILE, lm)
        return updated
    except Exception:
        return False
