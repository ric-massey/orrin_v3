# brain/cognition/local_search_signal.py
# Injects a signal when context suggests Orrin wants to look inside his own files.
#
# Scientific basis:
#   Nelson & Narens (1990) metacognitive monitoring framework distinguishes two
#   retrieval strategies: (1) internal search when a "feeling of knowing" (FOK)
#   is high — the agent senses the answer exists in stored memory; (2) external
#   search when FOK is low. This module acts as the FOK detector for file-based
#   internal knowledge: if context references Orrin's own code, data, or behaviour,
#   the signal fires, routing toward search_own_files rather than web_search.
#
#   The signal strength is graded rather than binary, mirroring Metcalfe &
#   Shimamura (1994) who found FOK varies continuously with cue familiarity.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
from typing import Dict, Any, List

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Cue patterns that suggest an internal-knowledge lookup is warranted.
# Split into tiers by signal strength so familiar patterns score higher.
_HIGH_STRENGTH = [
    r"\bin my (code|files|data|source|brain|codebase)\b",
    r"\bhow (does|do|is) (orrin|this|that|it) (work|run|function|implement|process)\b",
    r"\bwhere (is|are|does|do) (this|that|the|my)\b",
    r"\bwhich file\b",
    r"\bcheck (my|the) (source|code|data|files)\b",
    r"\bfind (it |this |that )?in (my |the )?(code|files|data|source)\b",
    r"\binspect (my|orrin'?s?)\b",
]
_MED_STRENGTH = [
    r"\bhow (does|do|is) (the )?(dream|emotion|reward|bandit|memory|goal|resource_deficit)\b",
    r"\bwhat (does|is) (the )?(function|method|module|file|class)\b",
    r"\blook(ing)? at (my|orrin'?s?|the) (code|source|files?|data)\b",
    r"\breview (my|orrin'?s?|the) (code|source|files?|behaviour)\b",
    r"\bunderstand (my|orrin'?s?|the) (code|source|behaviour|loop|cycle)\b",
]
_LOW_STRENGTH = [
    r"\b(find|search|grep|look up) (in )?(local|own|internal|my)\b",
    r"\b(defined|implemented|written) (in|at|under)\b",
    r"\bself.?(referenc|examin|introspect|modif)\b",
]

_HIGH_SCORE = 0.80
_MED_SCORE  = 0.60
_LOW_SCORE  = 0.40
_MIN_SCORE_TO_INJECT = 0.35


def _score_text(text: str) -> float:
    """Return a FOK-style score in [0..1] for internal-search intent."""
    lower = text.lower()
    for pat in _HIGH_STRENGTH:
        if re.search(pat, lower):
            return _HIGH_SCORE
    for pat in _MED_STRENGTH:
        if re.search(pat, lower):
            return _MED_SCORE
    for pat in _LOW_STRENGTH:
        if re.search(pat, lower):
            return _LOW_SCORE
    return 0.0


def inject_local_search_signal(context: Dict[str, Any]) -> float:
    """
    Scan working memory and current goal for internal-lookup intent.
    If found, inject a signal tagged 'local_search' so the signal_router and
    select_function can route toward search_own_files.
    Returns the signal strength (0.0 if no signal fired).

    Call once per cycle, after process_inputs() has run, so the signal
    competes fairly with other attentional candidates (Desimone & Duncan,
    1995 biased competition model of selective attention).
    """
    ctx = context or {}

    # Collect candidate texts: goal, user input, recent WM
    candidates: List[str] = []
    goal = ctx.get("committed_goal") or {}
    if isinstance(goal, dict):
        g = (goal.get("title") or goal.get("name") or "").strip()
        if g:
            candidates.append(g)

    user_in = str(ctx.get("latest_user_input") or "").strip()
    if user_in:
        candidates.append(user_in[:200])

    wm: List[Any] = ctx.get("working_memory") or []
    for entry in reversed(wm[-6:]):
        text = entry if isinstance(entry, str) else (
            entry.get("content", "") if isinstance(entry, dict) else ""
        )
        text = str(text or "").strip()
        if len(text) > 10:
            candidates.append(text[:200])

    # Score: take max across candidates (strongest cue drives the signal)
    max_score = max((_score_text(t) for t in candidates), default=0.0)

    if max_score < _MIN_SCORE_TO_INJECT:
        return 0.0

    try:
        from brain.utils.signal_utils import create_signal
        sig = create_signal(
            source="local_search_monitor",
            content="local_search_intent: context suggests looking inside own files",
            signal_strength=max_score,
            tags=["local_search", "search_own_files", "internal", "metacognition"],
        )
        ctx.setdefault("raw_signals", []).append(sig)
        # Also set a direct context flag so extract_features() can read it cheaply
        ctx["_local_search_signal"] = max_score
    except Exception as _e:
        record_failure("local_search_signal.inject_local_search_signal", _e)

    log_private(f"[local_search] FOK signal fired strength={max_score:.2f}")
    return max_score
