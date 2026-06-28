# brain/cognition/contagion.py
#
# Orrin catches affect from whoever is speaking.
#
# Not by deciding to — automatically, the way people in the same room
# drift toward each other's affective register.
#
# The bleed is partial and asymmetric:
#   - High user affect intensity → more contagion
#   - High Orrin stability → less permeable to outside affect
#   - Relationship influence modulates the channel
#   - The caught affect fades naturally via update_affect_state's decay
#
# Called once per genuinely new user message from handle_user_input.
#
# SCIENTIFIC BASIS:
#   Hatfield, Cacioppo & Rapson (1993) — "Emotional contagion." Current
#   Directions in Psychological Science, 2(3), 96–99. Automatic mimicry and
#   synchrony of expressions, postures, and physiological responses leads to
#   convergence of affective states between interacting individuals.

from __future__ import annotations

from typing import Any, Dict

from brain.utils.log import log_private
from brain.control_signals.signals import detect_affect


# What Orrin catches from each detected user affect signal.
# Values are base fractions — actual bleed = value × bleed_scale.
_CONTAGION_MAP: Dict[str, Dict[str, float]] = {
    "impasse_signal": {"impasse_signal": 0.28, "uncertainty": 0.08},
    "conflict_signal":       {"impasse_signal": 0.22, "risk_estimate": 0.10},
    "reward_negative":     {"low_affect_signal": 0.24, "affiliation_signal": 0.18},
    "threat_level":        {"risk_estimate": 0.26, "uncertainty": 0.10},
    "risk_estimate":     {"risk_estimate": 0.24, "uncertainty": 0.10},
    "distress":    {"risk_estimate": 0.20, "low_affect_signal": 0.14},
    "rejection_signal":     {"uncertainty": 0.10, "impasse_signal": 0.08},
    "reward_positive":         {"expected_gain": 0.20, "motivation": 0.14},
    "excitement":  {"motivation": 0.22, "exploration_drive": 0.14},
    "expected_gain":        {"expected_gain": 0.24, "motivation": 0.10},
    "exploration_drive":   {"exploration_drive": 0.20},
    "prediction_error_signal": {"exploration_drive": 0.14, "uncertainty": 0.08},
}

_MAX_BLEED = 0.42   # ceiling — Orrin can't be overwhelmed even by intense affect
_MIN_BLEED = 0.08   # floor — always a trace effect from genuine affect


def apply_emotional_contagion(
    user_text: str,
    context: Dict[str, Any],
    influence: float = 0.5,
) -> None:
    """
    Detect the emotional tone of user_text and bleed a fraction into
    Orrin's emotional state. Call only when new user input is confirmed.
    """
    if not user_text or not user_text.strip():
        return
    try:
        _apply(user_text, context, influence)
    except Exception as e:
        log_private(f"[contagion] error: {e}")


def _apply(user_text: str, context: Dict[str, Any], influence: float) -> None:
    result = detect_affect(user_text, use_gpt=False)
    if not isinstance(result, dict):
        return

    emotion_label = str(result.get("emotion") or "neutral").lower()
    intensity     = float(result.get("intensity") or 0.0)

    if emotion_label in ("neutral", "unknown", "") or intensity < 0.05:
        return

    effects = _CONTAGION_MAP.get(emotion_label)
    if not effects:
        return

    emo = context.get("affect_state") or {}
    stability = float(emo.get("affect_stability") or 0.6)

    # More stable → less permeable. More influential relationship → more permeable.
    # bleed_scale in [_MIN_BLEED .. _MAX_BLEED]
    permeability = (1.0 - stability * 0.65) * (0.55 + 0.45 * influence)
    bleed_scale  = max(_MIN_BLEED, min(_MAX_BLEED, permeability * intensity))

    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return

    applied: list[str] = []
    for caught_emotion, base_amount in effects.items():
        delta = base_amount * bleed_scale
        if delta < 0.002:
            continue
        core[caught_emotion] = min(1.0, float(core.get(caught_emotion) or 0.0) + delta)
        applied.append(f"{caught_emotion}+{delta:.3f}")

    if not applied:
        return

    if isinstance(emo.get("core_signals"), dict):
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo

    log_private(
        f"[contagion] user={emotion_label}(i={intensity:.2f}) "
        f"scale={bleed_scale:.2f} → {', '.join(applied)}"
    )
