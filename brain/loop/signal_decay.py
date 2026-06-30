"""Cognitive-loop crisis-detection stage (Phase 4.5B, from sense.py).

`_apply_transient_signal_decay` — an extracted `stage(context) -> context`
pipeline stage that tracks sustained crisis for the emergency_self_modification
gate. sense.py re-exports it (so ORRIN_loop and the stage's unit tests keep
importing it from brain.loop.sense), and the sense stage calls it once per cycle.

NOTE (Grounded Cognition plan, Phase 1B / invariant #1): this stage used to ALSO
decay a handful of negative signals toward zero each cycle — a SECOND decay
authority competing with homeostasis.apply_restoring_forces. That decay was
vestigial: the canonical store for those signals is `core_signals`, and this stage
operated on the TOP-LEVEL affect_state shadow, which is empty for all of them
except `stagnation_signal` (a mere read-fallback). So the lines decayed nothing
live for 5/6 keys and ran an independent second decay law on one fallback shadow.
The single owner of restoring forces on core signals is `homeostasis`; this stage
now only keeps the stagnation read-fallback CONSISTENT with the authoritative core
value (no independent decay) and does its real job — crisis detection.
"""
from __future__ import annotations

from typing import Any, Dict

from brain.utils.failure_counter import record_failure
from brain.config.tuning import (
    CRISIS_ABOVE_HALF_COUNT,
    CRISIS_ABOVE_HALF_THRESHOLD,
    CRISIS_ACUTE_PEAK,
    CRISIS_CHRONIC_MEAN,
)

Context = Dict[str, Any]


def _apply_transient_signal_decay(context: "Context") -> "Context":
    """
    Pipeline stage (Finding 1's stage(context) -> context pattern): decay
    short-lived affect signals (impasse/penalty/conflict/threat/stagnation/
    uncertainty) toward zero each cycle, then check whether the decayed
    core-negative signals indicate a sustained crisis — either an acute spike
    (one signal >= CRISIS_ACUTE_PEAK plus CRISIS_ABOVE_HALF_COUNT others >=
    CRISIS_ABOVE_HALF_THRESHOLD) or a chronic broad collapse (mean of all core
    negatives >= CRISIS_CHRONIC_MEAN). Updates context["_extreme_cycles"], the
    counter the emergency_self_modification gate watches: +1 per crisis cycle
    (capped at 50), -3 per non-crisis cycle (recovers 3x faster than it
    accumulates so a past crisis doesn't linger as ancient history).
    Fail-safe — any error during crisis detection leaves _extreme_cycles
    untouched for this cycle.
    """
    affect_state = context.get("affect_state", {})
    # Keep the top-level stagnation_signal read-fallback consistent with the
    # authoritative core value (homeostasis owns its decay) — do NOT run a second
    # decay law here (invariant #1; see module docstring).
    _core = affect_state.get("core_signals")
    if isinstance(_core, dict) and "stagnation_signal" in _core:
        affect_state["stagnation_signal"] = _core["stagnation_signal"]
    else:
        affect_state.setdefault("stagnation_signal", 0.0)
    context["affect_state"] = affect_state

    # Track sustained crisis for emergency_self_modification gate.
    # Two paths: acute spike (one emotion ≥ 0.85 + two others ≥ 0.50)
    # OR broad collapse (mean of all negatives ≥ 0.70).
    try:
        _gc  = (affect_state.get("core_signals") or affect_state) or {}
        # Core negatives — all confirmed keys in core_signals
        _core_negs = [
            float(_gc.get("impasse_signal") or 0),
            float(_gc.get("threat_level")        or 0),
            float(_gc.get("reward_negative")     or 0),
            float(_gc.get("conflict_signal")       or 0),
            float(_gc.get("rejection_signal")     or 0),
        ]
        # Top-level negatives — these live outside core_signals
        _core_negs.append(float(affect_state.get("risk_estimate")   or 0))
        _core_negs.append(float(affect_state.get("social_deficit") or 0))

        _peak  = max(_core_negs)
        _above_half = sum(1 for v in _core_negs if v >= CRISIS_ABOVE_HALF_THRESHOLD)
        _mean  = sum(_core_negs) / len(_core_negs)

        _acute   = _peak >= CRISIS_ACUTE_PEAK and _above_half >= CRISIS_ABOVE_HALF_COUNT
        _chronic = _mean >= CRISIS_CHRONIC_MEAN
        _in_crisis = _acute or _chronic

        if _in_crisis:
            context["_extreme_cycles"] = min(50, int(context.get("_extreme_cycles") or 0) + 1)
        else:
            # Recover 3x faster than we accumulated — crisis should not linger as ancient history
            context["_extreme_cycles"] = max(0, int(context.get("_extreme_cycles") or 0) - 3)
    except Exception as _e:
        record_failure("ORRIN_loop._apply_transient_signal_decay", _e)

    return context
