# brain/cognition/mood.py
#
# Mood is not an affect — it's the weather you're living in.
#
# Affect signals spike and decay per-cycle. Mood is the slow accumulation
# underneath: the average affective texture over hours, computed as an
# exponential moving average. A bad mood makes negative affect land harder;
# a good mood makes positive affect go further.
#
# Dimensions:
#   valence   — positive vs negative aggregate. Range ~[-0.8..0.8]
#   energy    — activation_level proxy: motivation + exploration_drive - resource_deficit - low_affect_signal
#   stability — smoothed signal_stability field
#
# Effect: after all per-cycle affect bumps, mood nudges affect further in
# the mood-consistent direction — proportional amplification, not override.
#
# Called from finalize.py. Persists to mood_state.json.
#
# SCIENTIFIC BASIS:
#   Watson & Tellegen (1985) — "Toward a consensual structure of mood."
#   Psychological Bulletin, 98(2), 219–235. Two-factor valence/activation_level
#   structure underlying mood (implemented as valence + energy axes).
#   Morris (1989) — "Moods: The frame of mind." Springer.
#   Mood as a background state that amplifies valence-congruent processing
#   without dictating specific action tendencies (cf. discrete affect).

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from brain.utils.log import log_private
from brain.utils.json_utils import load_json, save_json
from brain.paths import MOOD_FILE


_ALPHA      = 0.015    # EMA smoothing — mood drifts ~1.5% per cycle toward current state
_SAVE_EVERY = 10       # flush to disk every N cycles

_cycle_counter = 0

_POSITIVE = frozenset({"reward_positive", "expected_gain", "motivation", "exploration_drive", "confidence",
                        "satisfaction", "novelty_signal", "excitement"})
_NEGATIVE = frozenset({"impasse_signal", "risk_estimate", "threat_level", "low_affect_signal", "reward_negative",
                        "social_penalty", "uncertainty", "conflict_signal", "rejection_signal"})


# ── Computation ────────────────────────────────────────────────────────────────

def _valence(core: Dict) -> float:
    """Positive minus negative, normalized by how many are active."""
    pos = sum(float(core.get(e) or 0) for e in _POSITIVE)
    neg = sum(float(core.get(e) or 0) for e in _NEGATIVE)
    n_pos = max(1, sum(1 for e in _POSITIVE if float(core.get(e) or 0) > 0.05))
    n_neg = max(1, sum(1 for e in _NEGATIVE if float(core.get(e) or 0) > 0.05))
    return round((pos / n_pos - neg / n_neg) / 2.0, 4)


def _energy(core: Dict, emo: Dict) -> float:
    mot  = float(core.get("motivation") or emo.get("motivation") or 0.5)
    cur  = float(core.get("exploration_drive") or 0.3)
    fat  = float(emo.get("resource_deficit") or core.get("resource_deficit") or 0.0)
    mel  = float(core.get("low_affect_signal") or 0.0)
    return round(max(-1.0, min(1.0, mot + cur * 0.5 - fat - mel * 0.5)), 4)


# ── Main entry point ───────────────────────────────────────────────────────────

def update_smoothed_state(context: Dict[str, Any]) -> Dict:
    """
    Called each cycle from finalize.py.
    Updates EMA mood, applies amplification, sets context["_mood"].
    Returns the current mood dict.
    """
    global _cycle_counter
    _cycle_counter += 1
    try:
        return _update(context)
    except Exception as e:
        log_private(f"[mood] error: {e}")
        return {}


def _update(context: Dict[str, Any]) -> Dict:
    emo  = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return {}

    cur_val  = _valence(core)
    cur_nrg  = _energy(core, emo)
    cur_stab = float(emo.get("signal_stability") or 0.6)

    stored   = load_json(MOOD_FILE, default_type=dict) or {}
    old_val  = float(stored.get("valence")   or cur_val)
    old_nrg  = float(stored.get("energy")    or cur_nrg)
    old_stab = float(stored.get("stability") or cur_stab)

    mood = {
        "valence":    round(_ALPHA * cur_val  + (1 - _ALPHA) * old_val,  4),
        "energy":     round(_ALPHA * cur_nrg  + (1 - _ALPHA) * old_nrg,  4),
        "stability":  round(_ALPHA * cur_stab + (1 - _ALPHA) * old_stab, 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if _cycle_counter % _SAVE_EVERY == 0:
        save_json(MOOD_FILE, mood)

    context["_mood"] = mood

    # Amplification: mood makes mood-consistent movements slightly larger
    _amplify(context, mood, core, emo)
    return mood


def _amplify(context: Dict, mood: Dict, core: Dict, emo: Dict) -> None:
    """
    Proportional nudge based on mood valence. Small — max ~4% per cycle.
    Bad mood: negative emotions drift a bit higher, positive a bit lower.
    Good mood: opposite.
    """
    val = float(mood.get("valence") or 0.0)
    if abs(val) < 0.08:
        return   # mood too neutral to have a detectable effect

    amp = min(0.04, abs(val) * 0.12)

    if val < 0:
        for e in _NEGATIVE:
            v = float(core.get(e) or 0.0)
            if v > 0.08:
                core[e] = min(1.0, v + amp * v)
        for e in _POSITIVE:
            v = float(core.get(e) or 0.0)
            if v < 0.85:
                core[e] = max(0.0, v - amp * 0.4)
    else:
        for e in _POSITIVE:
            v = float(core.get(e) or 0.0)
            if v > 0.05:
                core[e] = min(1.0, v + amp * v)
        for e in _NEGATIVE:
            v = float(core.get(e) or 0.0)
            if v > 0.08:
                core[e] = max(0.0, v - amp * 0.4)

    if isinstance(emo.get("core_signals"), dict):
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo
