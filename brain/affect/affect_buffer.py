"""
emotion/emotion_buffer.py

Emotion changes queue into a short buffer and drain gradually over 2-4 cycles.

Replaces instant arithmetic writes (affect_state["confidence"] += 0.08) with
a queue that applies the same total delta over time — matching how emotional
responses to rewards and setbacks actually work in humans. A surprising success
doesn't snap confidence; it builds it over the next few minutes.

Interface:
    queue_affect_change(state, emotion, delta, ttl_cycles=3, source="")
    drain_affect_queue(state, core)   # called each update_affect_state cycle
"""
from __future__ import annotations

import random
from typing import Any, Dict, List

from brain.utils.log import log_activity

_QUEUE_KEY = "_emotion_queue"


def queue_affect_change(
    state: Dict[str, Any],
    emotion: str,
    delta: float,
    ttl_cycles: int = 3,
    source: str = "",
) -> None:
    """
    Enqueue an emotion delta to be drained gradually over ttl_cycles.
    TTL is jittered ±1 so not all buffered changes drain in lockstep.
    """
    if abs(delta) < 0.005:
        return

    ttl = max(2, min(5, ttl_cycles + random.randint(-1, 1)))
    per_cycle = round(delta / ttl, 4)

    queue: List[Dict] = state.setdefault(_QUEUE_KEY, [])
    queue.append({
        "emotion":     emotion,
        "per_cycle":   per_cycle,
        "cycles_left": ttl,
        "source":      source[:40],
    })


def drain_affect_queue(
    state: Dict[str, Any],
    core: Dict[str, float],
) -> None:
    """
    Apply one cycle's worth of buffered changes to core (in place).
    Exhausted entries are pruned; unknown emotion keys are logged and dropped.
    """
    queue: List[Dict] = state.get(_QUEUE_KEY)
    if not queue:
        return

    still_active: List[Dict] = []
    for item in queue:
        if not isinstance(item, dict):
            continue

        emotion    = item.get("emotion", "")
        per_cycle  = float(item.get("per_cycle") or 0)
        cycles_left = int(item.get("cycles_left") or 0)

        if cycles_left <= 0 or abs(per_cycle) < 0.001:
            continue

        if emotion in core:
            core[emotion] = max(0.0, min(1.0, float(core[emotion]) + per_cycle))
        else:
            log_activity(f"[emotion_buffer] dropped delta for unknown emotion '{emotion}' (per_cycle={per_cycle:+.3f})")

        item["cycles_left"] = cycles_left - 1
        if item["cycles_left"] > 0:
            still_active.append(item)

    state[_QUEUE_KEY] = still_active
