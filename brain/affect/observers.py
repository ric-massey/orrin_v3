# brain/affect/observers.py
#
# Canonical, read-only observers over affect_state (V3_AUDIT.md §2.2 / §4.1, D6/D9).
#
# Several consumers used to re-derive the same affect features ad hoc, each
# re-reading core signals and re-applying its own thresholds (e.g. the negative-
# load "distress" sum computed in two different spots in select_function). When
# the formula lives in N places it drifts. These helpers are the single definition
# each consumer reads instead of recomputing.
#
# normalize_affect_state additionally pins the canonical schema (Contract E):
# core_signals nested, the required scalars present — so the dual nested/flat
# layout branching elsewhere degrades to dead defensive code rather than a live
# fork in behaviour.
from __future__ import annotations

from typing import Any, Dict

# The canonical negative-affect signals whose sum is the system's "distress" /
# negative-load feature. One list, read everywhere.
NEGATIVE_SIGNALS = (
    "impasse_signal", "threat_level", "risk_estimate", "conflict_signal", "negative_valence",
)

# Top-level scalars that are NOT core emotion signals — used to keep them out of
# core_signals when migrating a legacy flat-layout state.
_NON_CORE_SCALARS = frozenset({
    "resource_deficit", "affect_stability", "valence", "activation_level", "mood",
    "stability_decay_rate", "emotional_decay", "last_updated", "affect_quadrant",
    "social_deficit", "_ne_proxy", "_stability_signal_proxy", "_affect_velocity_l1",
})


def core_of(affect_state: Any) -> Dict[str, Any]:
    """Return the core-signals dict, tolerating both nested and flat layouts."""
    if not isinstance(affect_state, dict):
        return {}
    core = affect_state.get("core_signals")
    if isinstance(core, dict):
        return core
    return affect_state  # flat layout fallback


def negative_load(affect_state: Any) -> float:
    """
    Canonical distress aggregate: the summed magnitude of the negative-affect
    signals. The single definition that select_function (and any other consumer)
    reads instead of re-deriving its own sum.
    """
    core = core_of(affect_state)
    total = 0.0
    for k in NEGATIVE_SIGNALS:
        try:
            total += float(core.get(k) or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def normalize_affect_state(state: Any) -> Dict[str, Any]:
    """
    Coerce an affect_state dict to the canonical schema in place and return it:
      { core_signals: {str: float}, resource_deficit, affect_stability,
        _emotion_queue, last_updated, ... }

    Non-destructive: a legacy flat-layout state has its numeric emotion keys
    migrated into core_signals (scalars excluded); required scalars are seeded if
    missing. Called by the sole writer (update_affect_state) on load so every
    cycle persists the canonical layout.
    """
    if not isinstance(state, dict):
        return {"core_signals": {}, "resource_deficit": 0.15, "affect_stability": 1.0,
                "_emotion_queue": []}

    core = state.get("core_signals")
    if not isinstance(core, dict):
        # Migrate flat numeric emotion signals into a nested core_signals map.
        core = {
            k: float(v) for k, v in state.items()
            if isinstance(v, (int, float)) and k not in _NON_CORE_SCALARS
        }
        state["core_signals"] = core

    state.setdefault("resource_deficit", 0.15)
    state.setdefault("affect_stability", 1.0)
    state.setdefault("_emotion_queue", [])
    return state
