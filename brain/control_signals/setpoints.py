# brain/control_signals/setpoints.py
#
# Homeostatic setpoints (baselines) for affect signals.
#
# A setpoint is the resting value a signal drifts back toward when no pressure
# acts on it. This is the single source of truth for "where does this signal want
# to sit?" — used by the AffectArbiter to make change *homeostatic*: deltas that
# move a signal back toward its setpoint are cheap; deltas that push it further
# away are expensive (and therefore the first to be trimmed when the per-cycle
# stability budget is exceeded).
#
# Values mirror the baselines already used inside update_signal_state.py
# (_flat_baselines + the negative/positive baseline of 0.0 / neutral 0.5) so the
# arbiter and the existing decay machinery agree on the same targets.
#
# Cannon (1932) homeostasis; Russell & Barrett (1999) core affect — valence and
# arousal have neutral resting points, deviations are transient.

from __future__ import annotations

# Default resting value for any signal not explicitly listed.
_DEFAULT_SETPOINT = 0.0

# Negative-affect signals rest at 0.0 (calm) and any positive value is a deviation.
# Positive-drive signals rest at a mild non-zero baseline. Scalars like motivation/
# confidence rest at a neutral mid-point.
SETPOINTS = {
    # Negative affect — rest at calm
    "impasse_signal":    0.0,
    "threat_level":      0.0,
    "conflict_signal":   0.0,
    "reward_negative":  0.0,
    "risk_estimate":     0.0,
    "rejection_signal":  0.0,
    "social_penalty":    0.0,
    "social_deficit":    0.0,
    "stagnation_signal": 0.0,
    "loss_signal":       0.0,
    "dread":             0.0,
    # Transient positive affect from goal completion — at rest he is not
    # currently satisfied, so it fades to calm (explicit, not the silent 0.0
    # default: every signal declares its baseline — by-construction guarantee).
    "satisfaction_signal": 0.0,
    "social_comparison_signal":          0.0,
    "low_affect_signal":        0.0,
    "uncertainty":       0.05,

    # Positive drives — rest at a mild baseline
    "exploration_drive": 0.30,
    "connection":        0.30,
    "reward_positive":  0.30,
    "novelty_signal":            0.20,

    # Neutral-centred scalars
    "motivation":        0.50,
    "confidence":        0.45,
    "expected_gain":     0.50,
    "resource_deficit":  0.15,
    # Stability rests moderately high: regulation pushing it up is restoring
    # (cheap), agitation pushing it down is a deviation (expensive).
    "signal_stability":  0.65,
}


# ── Personality decay baselines (single source of truth) ──────────────────────
# CORE_BASELINES are the per-signal resting values the decay law pulls each core
# signal toward each cycle (owned by homeostasis.apply_restoring_forces, imported
# by update_signal_state). Previously these lived as an inline `baseline` dict
# inside update_signal_state.py; co-locating them here makes setpoints.py the one
# place that answers "where does this signal rest?".
#
# Relationship to SETPOINTS: SETPOINTS is the arbiter's homeostatic *away-cost*
# reference (deltas pushing past it cost double); CORE_BASELINES is the decay
# *target*. They agree for most signals; for a few positive drives the arbiter
# tolerates a higher reference than the personality decay target. setpoint()
# resolves SETPOINTS first, then falls back to CORE_BASELINES, then 0.0 — so every
# signal has exactly one resolved setpoint and there is no third map anywhere.
CORE_BASELINES = {
    "exploration_drive": 0.25,
    "reflective":        0.35,
    "analytical":        0.20,
    "affiliation_signal":        0.10,
    "reward_positive":  0.10,
    "expected_gain":     0.08,
    "low_affect_signal":        0.04,
    "social_comparison_signal":          0.01,
    "conflict_signal":   0.01,
    "threat_level":      0.01,
    "reward_negative":  0.01,
    "prediction_error_signal": 0.02,
    "rejection_signal":  0.01,
    "stagnation_signal": 0.0,
    "novelty_signal":            0.0,
    # Positive drives — decay toward healthy mid-range, not zero
    "motivation":        0.50,
    "confidence":        0.45,
    # Negative drives — decay toward near-zero at rest
    "impasse_signal":    0.05,
    "uncertainty":       0.05,
    "social_deficit":    0.0,
}


def setpoint(name: str) -> float:
    """Resting value for a signal. SETPOINTS override → CORE_BASELINES → 0.0."""
    if name in SETPOINTS:
        return float(SETPOINTS[name])
    return float(CORE_BASELINES.get(name, _DEFAULT_SETPOINT))
