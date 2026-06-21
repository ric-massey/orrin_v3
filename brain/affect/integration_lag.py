# brain/affect/integration_lag.py
#
# The knowing/feeling gap — when something significant happens, Orrin can
# understand it cognitively before he has fully felt it.
#
# This models the well-known human experience where you hear difficult news,
# understand what it means, say the right things — and only feel the weight
# of it hours later. The affect arrives in two waves.
#
# Mechanics:
#   When comprehension detects high-intensity input (intensity > 0.65):
#     - Apply 40% of the affective delta immediately (the immediate recognition)
#     - Queue the remaining 60% as a pending integration entry
#     - After 5-8 jittered cycles, apply the queued portion
#
#   In the interim, expression uses a "not fully landed yet" register —
#   Orrin knows what's being said but isn't fully inhabited by it yet.
#   This shows up as "I hear you" or "that's significant" rather than deep feeling.
#
# Storage: context["_pending_emotional_integration"]
#   A list of: {emotion, delta, cycles_left, event_summary}
#
# SCIENTIFIC BASIS:
#   Gross (1998) — "Antecedent- and response-focused emotion regulation." JPSP,
#   74(1), 224–237. Delayed affective processing: cognitive understanding precedes
#   the full somatic/experiential response, especially for aversive content.
#   Levenson (1994) — "Human emotion: A functional view." In Ekman & Davidson
#   (Eds.), The Nature of Emotion. Oxford University Press.
from __future__ import annotations

import random
from typing import Any, Dict, List

from brain.utils.log import log_private

_IMMEDIATE_FRACTION = 0.40   # portion applied right away
_DEFERRED_FRACTION  = 0.60   # portion that arrives later
_DEFERRED_MIN_CYCLES = 5
_DEFERRED_MAX_CYCLES = 8
_INTENSITY_THRESHOLD = 0.65  # minimum input intensity to trigger lag


# ── Per-cycle drain ───────────────────────────────────────────────────────────

def process_integration_queue(context: Dict[str, Any]) -> None:
    """
    Called once per cycle. Decrements counters and applies deferred emotional
    deltas when their time is up. Mutates context["affect_state"] in place.
    """
    queue: List[Dict] = context.get("_pending_emotional_integration") or []
    if not queue:
        return

    emo_state = context.get("affect_state") or {}
    core = dict(emo_state.get("core_signals") or emo_state)

    remaining = []
    for entry in queue:
        entry["cycles_left"] = max(0, int(entry.get("cycles_left") or 0) - 1)
        if entry["cycles_left"] <= 0:
            emotion = entry.get("emotion", "")
            delta   = float(entry.get("delta") or 0.0)
            if emotion and delta:
                core[emotion] = min(1.0, max(0.0, float(core.get(emotion) or 0.0) + delta))
                log_private(
                    f"[integration_lag] deferred {emotion}+{delta:.3f} arrived: "
                    f"'{entry.get('event_summary','')[:40]}'"
                )
        else:
            remaining.append(entry)

    if "core_signals" in emo_state:
        emo_state["core_signals"] = core
    else:
        emo_state.update(core)
    context["affect_state"]               = emo_state
    context["_pending_emotional_integration"] = remaining


def enqueue_integration_lag(
    emotion: str,
    total_delta: float,
    event_summary: str,
    context: Dict[str, Any],
) -> None:
    """
    Split total_delta: apply 40% now, queue 60% for 5-8 cycles later.
    Mutates context["affect_state"] and context["_pending_emotional_integration"].
    """
    emo_state = context.get("affect_state") or {}
    core = dict(emo_state.get("core_signals") or emo_state)

    immediate = round(total_delta * _IMMEDIATE_FRACTION, 4)
    deferred  = round(total_delta * _DEFERRED_FRACTION, 4)

    # Apply immediate portion
    if emotion and immediate:
        core[emotion] = min(1.0, max(0.0, float(core.get(emotion) or 0.0) + immediate))

    if "core_signals" in emo_state:
        emo_state["core_signals"] = core
    else:
        emo_state.update(core)
    context["affect_state"] = emo_state

    # Queue deferred portion
    if deferred:
        cycles_left = random.randint(_DEFERRED_MIN_CYCLES, _DEFERRED_MAX_CYCLES)
        entry = {
            "emotion":       emotion,
            "delta":         deferred,
            "cycles_left":   cycles_left,
            "event_summary": event_summary[:80],
        }
        queue = context.setdefault("_pending_emotional_integration", [])
        queue.append(entry)
        # Cap queue to prevent accumulation
        context["_pending_emotional_integration"] = queue[-10:]

    log_private(
        f"[integration_lag] split {emotion}: immediate={immediate:.3f} "
        f"deferred={deferred:.3f} in {cycles_left if deferred else 0} cycles"
    )


def has_pending_integration(context: Dict[str, Any]) -> bool:
    """True when there are unresolved deferred emotional deltas."""
    return bool(context.get("_pending_emotional_integration"))


def integration_voice_hint(context: Dict[str, Any]) -> str:
    """
    Returns a hint for the expression layer about the current integration state.
    "landed"     — nothing pending, full emotional access
    "processing" — deferred emotion is queued, cognition ahead of feeling
    """
    if has_pending_integration(context):
        return "processing"
    return "landed"


# ── Hook for comprehension layer ──────────────────────────────────────────────

def maybe_apply_integration_lag(
    emotion: str,
    intensity: float,
    event_summary: str,
    context: Dict[str, Any],
) -> bool:
    """
    Called from comprehension/user_input layer when a high-intensity emotional
    signal is detected. Returns True if lag was applied, False if intensity was
    below threshold (caller should apply the full delta directly instead).
    """
    if intensity < _INTENSITY_THRESHOLD:
        return False
    # The 'total_delta' here is the full emotional delta the caller would have applied.
    # We split it instead.
    enqueue_integration_lag(emotion, intensity, event_summary, context)
    return True
