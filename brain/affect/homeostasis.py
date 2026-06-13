# brain/affect/homeostasis.py
#
# HomeostasisManager — the single owner of *restoring forces* on affect.
#
# THE PROBLEM IT SOLVES (V3_AUDIT.md §3.2, D3/D8)
# Restoring/decay logic used to be scattered across at least six locations with
# independent rates and targets, and two of them disagreed on where a signal
# should rest (the now-deleted decay_affect_state pulled everything toward 0.5,
# while update_affect_state decays toward per-signal baselines). A homeostatic
# system cannot have two setpoints for one signal.
#
# This module centralises the restoring forces that act on core_signals each
# cycle:
#   1. apply_restoring_forces — exponential decay of every signal toward its
#      resting baseline (setpoints.CORE_BASELINES, the single source of truth),
#      plus the antagonist cross-inhibition pull that keeps impossible
#      co-saturations (e.g. impasse=1.0 AND confidence=1.0) from persisting.
#   2. enforce_velocity_budget — a hard cap on the NET L1 movement of the whole
#      core vector in one cycle, so that decay + buffer drain + triggers combined
#      can never lurch affect faster than a configured maximum (the "max emotional
#      velocity" the homeostatic model requires).
#
# Cannon (1932) homeostasis; Russell & Barrett (2000) core affect.
from __future__ import annotations

from typing import Dict, List

from affect.setpoints import CORE_BASELINES

# Antagonist pairs for sustained cross-inhibition. When a dominant signal is
# chronically elevated, its antagonists are pulled toward baseline faster than
# their natural decay — preventing impossible co-saturations.
ANTAGONISTS: Dict[str, List[str]] = {
    "positive_valence":  ["negative_valence", "melancholy"],
    "negative_valence":  ["positive_valence", "expected_gain"],
    "conflict_signal":   ["compassion", "peace"],
    "threat_level":      ["confidence", "boldness"],
    "impasse_signal":    ["confidence", "motivation", "positive_valence"],
    "confidence":        ["threat_level", "uncertainty"],
    "motivation":        ["negative_valence", "stagnation_signal"],
    "exploration_drive": ["stagnation_signal"],
    "stagnation_signal": ["exploration_drive", "wonder", "motivation"],
    "uncertainty":       ["confidence"],
}

_INHIBIT_THRESHOLD = 0.70
_INHIBIT_RATE = 0.04

# Default per-cycle net velocity cap on the core vector (L1). Tuned so a normal
# cycle (a few small nudges + gentle decay) passes untouched, but a cycle where
# many forces fire at once cannot move the whole vector more than this in total.
DEFAULT_MAX_L1 = 1.20


def apply_restoring_forces(
    state: Dict,
    core: Dict[str, float],
    *,
    decay_rate: float,
    hours_passed: float,
) -> None:
    """
    Apply the single decay law (toward CORE_BASELINES) plus antagonist
    cross-inhibition to `core` in place.

    Mirrors the exact numeric behaviour previously inlined in
    update_affect_state, now owned here so there is one restoring-force authority.
    Honours state["emotional_decay"] (default True) for the baseline decay.
    """
    # ── 1. Baseline decay: exponential approach to each signal's resting value ──
    if state.get("emotional_decay", True):
        for emo, val in list(core.items()):
            val_f = float(val) if isinstance(val, (int, float)) else CORE_BASELINES.get(emo, 0.0)
            target = CORE_BASELINES.get(emo, 0.0)
            neutral_pull = target - val_f
            core[emo] = max(0.0, min(1.0, val_f + neutral_pull * (1 - pow(1 - decay_rate, hours_passed))))


def apply_cross_inhibition(core: Dict[str, float]) -> None:
    """
    Sustained cross-inhibition: when a dominant signal exceeds the inhibition
    threshold, pull its antagonists toward baseline, amplified by the excess.
    Prevents impossible co-saturations persisting cycle after cycle.
    """
    for emo, opps in ANTAGONISTS.items():
        val = float(core.get(emo, 0.0))
        if val > _INHIBIT_THRESHOLD:
            excess = val - _INHIBIT_THRESHOLD
            for opp in opps:
                if opp in core:
                    opp_val = float(core[opp])
                    base = CORE_BASELINES.get(opp, 0.0)
                    pull = base - opp_val
                    core[opp] = max(base, opp_val + pull * _INHIBIT_RATE * (excess / 0.1))


def enforce_velocity_budget(
    core: Dict[str, float],
    prev_core: Dict[str, float],
    *,
    max_l1: float = DEFAULT_MAX_L1,
) -> float:
    """
    Cap the NET per-cycle L1 movement of the core vector relative to its
    cycle-start snapshot. If the summed absolute change across all signals exceeds
    max_l1, scale every signal's delta down proportionally so the total movement
    equals max_l1. Returns the pre-clamp total L1 movement (for telemetry).

    This is the single mathematical "max emotional velocity" cap the homeostatic
    model requires — it bounds the combined effect of decay + buffer drain +
    triggers + appraisal that all mutate core within one update cycle.
    """
    if not isinstance(prev_core, dict) or not prev_core:
        return 0.0

    deltas: Dict[str, float] = {}
    total = 0.0
    for k, v in core.items():
        try:
            cur = float(v)
        except (TypeError, ValueError):
            continue
        if k not in prev_core:
            continue
        try:
            prev = float(prev_core[k])
        except (TypeError, ValueError):
            continue
        d = cur - prev
        if d:
            deltas[k] = d
            total += abs(d)

    if total <= max_l1 or total <= 0.0:
        return total

    scale = max_l1 / total
    for k, d in deltas.items():
        prev = float(prev_core[k])
        core[k] = max(0.0, min(1.0, prev + d * scale))
    return total
