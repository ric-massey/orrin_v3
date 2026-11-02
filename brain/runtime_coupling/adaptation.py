"""
runtime_coupling/adaptation.py

Online adaptation — post-cycle Hebbian learning and memory tagging.

In biology, plasticity is a property of every neural event, not a separate
module. Every cognitive cycle leaves a trace that makes future cycles
slightly different. This module implements that at three levels:

1. (Removed 2026-11-02, F3.) Hebbian emotion→function reinforcement wrote a
   second, scaled copy of every outcome into signal_function_map.json, read
   affect AFTER the act rather than the affect it was chosen under, and its
   negatives were floored to +0.1 by the map. execute_cognition_function's
   update is now the map's one writer.

2. Spreading activation update
   The function that ran primes related functions for the next cycle.
   Stored in context["_primed_functions"] as {fn_name: float} weight map.
   The select_function can optionally read this to bias toward related picks.

3. Emotional memory tagging
   Recent WM entries get tagged with the emotional state at time of formation,
   weighted by intensity. High-emotion experiences become more durable.

API:
  apply_adaptation(fn_name, context, reward)  — call post-cycle from ORRIN_loop
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

from typing import Any, Dict, List
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# How many related functions to prime (by name similarity / co-occurrence)
_PRIME_TOP_N = 5
_PRIME_DECAY = 0.85  # existing priming decays each cycle

# Minimum reward magnitude to bother with plasticity updates
_MIN_REWARD = -1.0  # always apply (negative reward = weakening)


def apply_adaptation(
    fn_name: str,
    context: Dict[str, Any],
    reward: float,
) -> None:
    """
    Main entry point. Called from ORRIN_loop after each cognitive cycle.
    Wraps all three plasticity mechanisms in try/except so nothing breaks.
    """
    if not fn_name:
        return

    try:
        _spreading_activation(fn_name, context, reward)
    except Exception as _e:
        record_failure("adaptation.apply_adaptation.2", _e)

    try:
        _tag_recent_memories(context)
    except Exception as _e:
        record_failure("adaptation.apply_adaptation.3", _e)


# ------------------------------------------------------------------
# 2. Spreading activation

def _spreading_activation(fn_name: str, context: Dict[str, Any], reward: float) -> None:
    """
    When a function runs, it primes related functions for the next cycle.
    Priming is stored in context["_primed_functions"] and decays each cycle.
    select_function can optionally read this to add a small bias.
    """
    # Decay existing priming
    primed: Dict[str, float] = context.get("_primed_functions") or {}
    primed = {k: v * _PRIME_DECAY for k, v in primed.items() if v * _PRIME_DECAY > 0.05}

    if reward <= 0.0:
        # Negative outcome — suppress related functions slightly
        primed[fn_name] = max(primed.get(fn_name, 0.0) - 0.15, -0.20)
        context["_primed_functions"] = primed
        return

    # Find related functions by name-component overlap
    fn_parts = set(fn_name.replace("_", " ").split())
    related = _find_related_functions(fn_parts, fn_name)

    prime_strength = min(0.25, reward * 0.20)
    for related_fn in related[:_PRIME_TOP_N]:
        primed[related_fn] = min(0.30, primed.get(related_fn, 0.0) + prime_strength)

    # Also prime the function itself slightly (recency bias)
    primed[fn_name] = min(0.20, primed.get(fn_name, 0.0) + prime_strength * 0.5)

    context["_primed_functions"] = primed


def _find_related_functions(fn_parts: set, exclude: str) -> List[str]:
    """
    Find functions in the cognitive registry that share name components.
    Lightweight — no LLM, just string overlap.
    """
    related: List[str] = []
    try:
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
        for name in COGNITIVE_FUNCTIONS:
            if name == exclude:
                continue
            name_parts = set(name.replace("_", " ").split())
            if fn_parts & name_parts:
                related.append(name)
    except Exception as _e:
        record_failure("adaptation._find_related_functions", _e)
    return related


# ------------------------------------------------------------------
# 3. Emotional memory tagging

def _tag_recent_memories(context: Dict[str, Any]) -> None:
    """
    Tag the most recent working memory entries with current emotional state.
    High-emotion tagging makes memories more salient for retrieval.
    Only tags entries that don't already have emotional metadata.
    """
    try:
        from brain.utils.json_utils import load_json, save_json
        from brain.paths import WORKING_MEMORY_FILE

        wm = load_json(WORKING_MEMORY_FILE, default_type=list)
        if not isinstance(wm, list) or not wm:
            return

        es = context.get("affect_state") or {}
        core = (es.get("core_signals") or es) or {}
        numeric = {k: float(v) for k, v in core.items()
                   if isinstance(v, (int, float)) and 0.0 < float(v) <= 1.0}

        if not numeric:
            return

        dominant = max(numeric, key=numeric.get)
        dom_val  = numeric[dominant]

        # Only tag if there's a meaningful emotional state
        if dom_val < 0.30:
            return

        modified = False
        # Tag last 3 entries that lack emotional tagging
        for entry in wm[-3:]:
            if not isinstance(entry, dict):
                continue
            if entry.get("_emotion_tagged"):
                continue
            if entry.get("event_type") in {"subconscious_pattern", "incubated_insight",
                                            "emotional_residue", "dominant_affect"}:
                continue
            entry["_emotion_at_formation"] = dominant
            entry["_emotion_intensity"]    = round(dom_val, 3)
            entry["_emotion_tagged"]       = True
            # Boost importance for high-emotion formation
            if dom_val > 0.65:
                entry["importance"] = max(
                    int(entry.get("importance") or 1),
                    2,
                )
            modified = True

        if modified:
            save_json(WORKING_MEMORY_FILE, wm)

    except Exception as _e:
        record_failure("adaptation._tag_recent_memories", _e)
