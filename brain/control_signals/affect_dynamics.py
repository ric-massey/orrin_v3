"""
brain/control_signals/affect_dynamics.py

Four biologically-grounded affective dynamic layers. All rule-based, no LLM.

1. Habituation     — diminishing response to repeated triggers (spontaneous recovery)
2. Velocity        — rate-of-change tracking; refractory periods after peaks
3. Valence/activation_level — Russell's circumplex: composite (v, a) axes from all affects
4. Mood            — slow background drift; modulates appraisal sensitivity

SCIENTIFIC BASIS:
  Habituation:     Thompson & Spencer (1966) — "Habituation: A model phenomenon
                   for the study of neuronal substrates of behavior."
                   Psychological Review, 173(1), 16–43.
  Circumplex:      Russell (1980) — "A circumplex model of affect."
                   Journal of Personality and Social Psychology, 39(6), 1161–1178.
  Core affect:     Russell & Barrett (2000) — "Core affect, prototypical emotional
                   episodes, and other things called emotion."
                   Psychological Review, 106(3), 631–657.

Called from update_affect_state at specific points in the update cycle.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


# ── 1. Habituation ────────────────────────────────────────────────────────────
# Repeated identical triggers produce diminishing affective responses.
# Thompson & Spencer (1966): nine defining features of habituation, including
# frequency-dependence and spontaneous recovery with rest.
# Recovery: spontaneous recovery after _HABIT_DECAY_MIN minutes without trigger.

_HABIT_BASE       = 0.68   # per-repeat multiplier  (0.68^n = intensity at step n)
_HABIT_FLOOR      = 0.18   # minimum multiplier     (never fully habituates)
_HABIT_DECAY_MIN  = 8      # minutes until count recovers by 1
_HABIT_MAX_COUNT  = 8      # clamp count so base**count doesn't go below floor

def _habit_key(emotion: str, content: str) -> str:
    sig = " ".join(content.strip().split()[:5]).lower()[:32]
    return f"{emotion}:{sig}"

def get_habit_factor(emotion: str, content: str, state: Dict[str, Any]) -> float:
    """
    Return the intensity multiplier for this (emotion, trigger) pair.
    1.0 = first time; approaches _HABIT_FLOOR after repeated exposure.
    """
    habit = state.get("habituation", {})
    entry = habit.get(_habit_key(emotion, content))
    if not entry:
        return 1.0
    count = min(int(entry.get("count", 0)), _HABIT_MAX_COUNT)
    return max(_HABIT_FLOOR, _HABIT_BASE ** count)

def record_habit(
    emotion: str,
    content: str,
    state: Dict[str, Any],
    now: datetime,
) -> None:
    """Increment trigger count for this (emotion, content) pair."""
    habit = state.setdefault("habituation", {})
    key   = _habit_key(emotion, content)
    entry = habit.setdefault(key, {"count": 0, "last_ts": now.isoformat()})
    entry["count"]   = min(int(entry.get("count", 0)) + 1, _HABIT_MAX_COUNT + 2)
    entry["last_ts"] = now.isoformat()

def decay_habituation(state: Dict[str, Any], now: datetime) -> None:
    """
    Spontaneous recovery: counts decrease when a trigger hasn't fired recently.
    Entries with count=0 are pruned.
    """
    habit     = state.get("habituation", {})
    to_delete = []
    for key, entry in habit.items():
        try:
            last_ts = datetime.fromisoformat(entry.get("last_ts", "1970-01-01T00:00:00+00:00"))
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            elapsed_min = (now - last_ts).total_seconds() / 60.0
            intervals   = int(elapsed_min / _HABIT_DECAY_MIN)
            if intervals > 0:
                new_count = max(0, int(entry.get("count", 0)) - intervals)
                if new_count <= 0:
                    to_delete.append(key)
                else:
                    entry["count"] = new_count
        except Exception as _e:
            record_failure("affect_dynamics.decay_habituation", _e)
    for k in to_delete:
        del habit[k]
    state["habituation"] = habit


# ── 2. Velocity / Momentum ────────────────────────────────────────────────────
# Track rate-of-change per emotion. Fast rise creates drag; post-peak creates
# a refractory pull so emotions come down after a spike instead of staying pinned.

_VELOCITY_DRAG    = 0.14   # fraction of velocity applied as drag when rising fast
_REFRACTORY_PULL  = 0.12   # extra downward pull in the cycle after a peak
_DRAG_THRESHOLD   = 0.07   # minimum velocity that triggers drag
_PEAK_THRESHOLD   = 0.09   # minimum prev_velocity that triggers refractory

def capture_prev_core(
    state: Dict[str, Any],
    core: Dict[str, float],
) -> Dict[str, float]:
    """
    Save current core snapshot as _prev_core. Returns the PREVIOUS snapshot
    (what was stored last cycle) so the caller can compare.
    """
    prev = dict(state.get("_prev_core") or {})
    state["_prev_core"] = dict(core)
    return prev

def apply_velocity_dynamics(
    core: Dict[str, float],
    prev_core: Dict[str, float],
    state: Dict[str, Any],
) -> None:
    """
    Apply velocity-based dynamics to core (in place).
    Reads previous velocity from state; writes new velocity back.
    """
    prev_velocity = state.get("emotion_velocity") or {}
    new_velocity: Dict[str, float] = {}

    for emo, val in list(core.items()):
        if not isinstance(val, float):
            val = float(val)
        prev_val = float(prev_core.get(emo, val))
        velocity  = val - prev_val
        new_velocity[emo] = round(velocity, 4)

        prev_v = float(prev_velocity.get(emo, 0.0))

        # Drag: resist fast rises
        if velocity > _DRAG_THRESHOLD:
            core[emo] = max(0.0, val - velocity * _VELOCITY_DRAG)

        # Refractory: after a peak (was rising, now stable/falling) → extra pull down
        if prev_v > _PEAK_THRESHOLD and velocity <= 0.01:
            core[emo] = max(0.0, core.get(emo, 0.0) - prev_v * _REFRACTORY_PULL)

    state["emotion_velocity"] = new_velocity


# ── 3. Valence / activation_level (Russell's circumplex) ───────────────────────────────
# Map all emotions onto two orthogonal axes:
#   valence  — pleasant (+1) to unpleasant (-1)
#   activation_level  — activated (+1) to deactivated (-1)
# Intensity-weighted average across all active emotions.

_VALENCE: Dict[str, float] = {
    "positive_valence":         +0.90,
    "expected_gain":        +0.70,
    "wonder":      +0.55,
    "compassion":  +0.50,
    "confidence":  +0.45,
    "motivation":  +0.35,
    "exploration_drive":   +0.20,
    "reflective":  +0.10,
    "surprise":    +0.10,
    "analytical":  +0.05,
    "stagnation_signal":     -0.20,
    "melancholy":  -0.30,
    "social_deficit":  -0.35,
    "uncertainty": -0.30,
    "risk_estimate":     -0.55,
    "negative_valence":     -0.55,
    "threat_level":        -0.65,
    "social_penalty":       -0.60,
    "impasse_signal": -0.60,
    "rejection_signal":     -0.70,
    "conflict_signal":       -0.75,
}

_ACTIVATION_LEVEL: Dict[str, float] = {
    "conflict_signal":       +0.90,
    "threat_level":        +0.80,
    "risk_estimate":     +0.75,
    "surprise":    +0.70,
    "positive_valence":         +0.65,
    "exploration_drive":   +0.60,
    "motivation":  +0.55,
    "wonder":      +0.50,
    "impasse_signal": +0.50,
    "uncertainty": +0.30,
    "expected_gain":        +0.20,
    "compassion":  +0.10,
    "confidence":  +0.15,
    "analytical":  -0.05,
    "reflective":  -0.10,
    "social_deficit":  -0.20,
    "social_penalty":       -0.15,
    "melancholy":  -0.35,
    "negative_valence":     -0.40,
    "stagnation_signal":     -0.50,
}

# Phasic arousers: fast signals whose ONSET should spike activation ABOVE the
# tonic mean (then subside as they decay). The tonic weighted-mean alone washes
# any single acute signal out — one alarming event among many calm ones barely
# shifts the average — which is why arousal sat near-inert (std ~0.008). Real
# arousal is phasic: a surprising / threatening / urgent event drives the
# locus-coeruleus noradrenergic burst up over the background, then relaxes
# (Aston-Jones & Cohen 2005). Value = how strongly each drives that burst.
_PHASIC_AROUSERS: Dict[str, float] = {
    "surprise":          1.00,
    "threat_level":      1.00,
    "conflict_signal":   0.90,
    "risk_estimate":     0.85,
    "impasse_signal":    0.70,
    "urgency":           1.00,   # absent from core today → harmlessly skipped
    "temporal_pressure": 0.80,   # ditto; picked up automatically if ever present
}
_PHASIC_GAIN = 0.70   # fraction of the above-tonic spike that reaches activation

_QUADRANT: Dict[Tuple[bool, bool], str] = {
    (True,  True):  "active_positive",   # excited, enthusiastic, flow
    (True,  False): "calm_positive",     # content, satisfied, peaceful
    (False, True):  "active_negative",   # stressed, anxious, agitated
    (False, False): "passive_negative",  # sad, withdrawn, depleted
}

def compute_valence_activation_level(
    core: Dict[str, Any],
) -> Tuple[float, float, str]:
    """
    Compute (valence, activation_level, quadrant_name) from current emotion intensities.
    Returns values in [-1, +1] and a descriptive quadrant name.
    """
    v_num = a_num = 0.0
    v_w = a_w = 0.0  # separate weight accumulators for valence and activation_level
    for emo, intensity in core.items():
        if not isinstance(intensity, (int, float)):
            continue
        w = float(intensity)
        if w < 0.05:
            continue
        v = _VALENCE.get(emo)
        a = _ACTIVATION_LEVEL.get(emo)
        if v is not None:
            v_num += v * w
            v_w   += w
        if a is not None:
            a_num += a * w
            a_w   += w

    if v_w < 0.01:
        return 0.0, 0.0, "calm_positive"

    valence = max(-1.0, min(1.0, v_num / v_w))

    # Activation = TONIC weighted mean + PHASIC spike. We add the strongest
    # fast-arouser on top of the tonic background rather than letting the mean
    # dilute it, so an acute event lifts arousal and then subsides as the signal
    # decays — phasic-on-tonic (Solomon & Corbit 1974; Aston-Jones & Cohen 2005).
    tonic = a_num / a_w if a_w >= 0.01 else 0.0
    phasic = 0.0
    for _sig, _gain in _PHASIC_AROUSERS.items():
        _inten = core.get(_sig)
        if isinstance(_inten, (int, float)):
            phasic = max(phasic, _gain * float(_inten))
    # Only the part of the spike ABOVE the tonic background lifts arousal: an
    # acute event raises activation, it never lowers it below the resting mean.
    activation_level = max(-1.0, min(1.0, tonic + _PHASIC_GAIN * max(0.0, phasic - max(0.0, tonic))))
    quad    = _QUADRANT[(valence > 0.0, activation_level > 0.0)]
    return round(valence, 3), round(activation_level, 3), quad


# ── 4. Hedonic adaptation ─────────────────────────────────────────────────────
# Sustained emotional states lose their felt charge. The "hedonic baseline" per
# emotion drifts slowly toward the current level — what used to feel intensely
# good (or bad) becomes the new normal, and only deviations from it register.
#
# Psychology basis: Brickman & Campbell (1971), Kahneman & Thaler (hedonic treadmill).
# Applies symmetrically: people adapt to both good and bad sustained states,
# though adaptation to extreme negatives is incomplete (floor).

_HEDONIC_DRIFT_RATE   = 0.010   # per-cycle drift toward current level
_HEDONIC_FLOOR_RATIO  = 0.75    # can't adapt more than 75% of the way to extreme negatives
_HEDONIC_SKIP_THRESH  = 0.08    # don't drift if emotion is near its true baseline (no point)

# True physiological baselines — hedonic drift never fully eliminates deviation from these
_TRUE_BASELINES = {
    "exploration_drive": 0.25, "motivation": 0.50, "confidence": 0.45,
    "impasse_signal": 0.05, "uncertainty": 0.05, "threat_level": 0.01,
    "positive_valence": 0.10, "expected_gain": 0.08, "negative_valence": 0.01, "conflict_signal": 0.01,
    "social_penalty": 0.0, "risk_estimate": 0.0, "stagnation_signal": 0.0, "wonder": 0.0,
    "melancholy": 0.04, "social_deficit": 0.0,
}


def update_hedonic_baselines(
    state: Dict[str, Any],
    core: Dict[str, float],
) -> Dict[str, float]:
    """
    Drift per-emotion hedonic baselines toward current levels.
    Returns the updated baselines dict (also stored in state).
    """
    baselines = state.get("hedonic_baselines") or {}
    if not isinstance(baselines, dict):
        baselines = {}

    for emo, val in core.items():
        if not isinstance(val, (int, float)):
            continue
        val = float(val)
        true_base = _TRUE_BASELINES.get(emo, 0.1)
        current_base = float(baselines.get(emo, true_base))

        # Only adapt when meaningfully above/below true baseline
        if abs(val - true_base) < _HEDONIC_SKIP_THRESH:
            # Drift baseline back toward true baseline when emotion is at rest
            baselines[emo] = round(
                current_base + (true_base - current_base) * _HEDONIC_DRIFT_RATE * 1.5,
                4,
            )
            continue

        # For strong negative sustained states: cap adaptation at floor ratio
        # (you can't fully adapt to severe impasse_signal/threat_level/social_penalty)
        negative_emos = {"impasse_signal", "threat_level", "social_penalty", "risk_estimate", "conflict_signal", "negative_valence"}
        if emo in negative_emos and val > true_base + 0.25:
            max_baseline = true_base + (val - true_base) * _HEDONIC_FLOOR_RATIO
            target = min(max_baseline, val)
        else:
            target = val

        baselines[emo] = round(
            current_base + (target - current_base) * _HEDONIC_DRIFT_RATE,
            4,
        )

    state["hedonic_baselines"] = baselines
    return baselines


def effective_intensity(
    emotion: str,
    val: float,
    hedonic_baselines: Dict[str, float],
) -> float:
    """
    Return the subjectively felt intensity of an emotion, adjusted for
    hedonic adaptation. Range [0, 1].

    effective = val - hedonic_baseline * 0.65
    (baseline only accounts for ~65% of its level — adaptation is partial)
    """
    base = float(hedonic_baselines.get(emotion, 0.0))
    true_base = _TRUE_BASELINES.get(emotion, 0.05)
    adaptation = max(0.0, base - true_base) * 0.65
    return max(0.0, min(1.0, val - adaptation))


# ── 5. Mood (slow background drift) ──────────────────────────────────────────
# Mood drifts slowly toward current valence, creating a persistent emotional
# context that outlasts individual emotion spikes. It modulates how Orrin
# interprets new events via the appraisal system.

_MOOD_DRIFT_RATE = 0.018   # per-cycle drift toward current valence
_MOOD_INITIAL    = 0.0

def update_mood(state: Dict[str, Any], valence: float) -> float:
    """
    Drift mood slowly toward current valence.
    Returns updated mood in [-1, +1].
    """
    mood = float(state.get("smoothed_state", _MOOD_INITIAL) or _MOOD_INITIAL)
    mood = mood + (valence - mood) * _MOOD_DRIFT_RATE
    mood = max(-1.0, min(1.0, round(mood, 4)))
    state["smoothed_state"] = mood  # was "mood" key
    return mood

def mood_delta_modifier(mood: float, delta: float) -> float:
    """
    Scale an appraisal delta by current mood.
    Good mood (>0): amplifies positive deltas, dampens negative.
    Bad mood (<0): dampens positive, amplifies negative.
    Modifier range: ±25%.
    """
    if delta > 0:
        return max(0.01, round(delta * (1.0 + mood * 0.25), 3))
    elif delta < 0:
        return min(-0.01, round(delta * (1.0 - mood * 0.25), 3))
    return 0.0
