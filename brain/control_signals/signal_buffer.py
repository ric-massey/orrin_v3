"""
emotion/emotion_buffer.py

Emotion changes queue into a short buffer and drain gradually over 2-4 cycles.

Replaces instant arithmetic writes (affect_state["confidence"] += 0.08) with
a queue that applies the same total delta over time — matching how emotional
responses to rewards and setbacks actually work in humans. A surprising success
doesn't snap confidence; it builds it over the next few minutes.

Interface:
    queue_signal_change(state, emotion, delta, ttl_cycles=3, source="")
    drain_signal_queue(state, core)   # called each update_signal_state cycle
"""
from __future__ import annotations

import random
from typing import Any, Dict, List

from brain.utils.clock import MEAN_CYCLE_S, cycles_to_s, last_dt
from brain.utils.log import log_activity

_QUEUE_KEY = "_emotion_queue"


def queue_signal_change(
    state: Dict[str, Any],
    emotion: str,
    delta: float,
    ttl_cycles: int = 3,
    source: str = "",
) -> None:
    """
    Enqueue an emotion delta to be drained gradually over ttl_cycles.
    TTL is jittered ±1 so not all buffered changes drain in lockstep.
    B12 (CT-A): the TTL is held in seconds (ttl × the mean cycle) and drains by
    elapsed time, so the curve is the same at any cadence.
    """
    if abs(delta) < 0.005:
        return

    ttl = max(2, min(5, ttl_cycles + random.randint(-1, 1)))
    span_s = cycles_to_s(ttl)

    queue: List[Dict] = state.setdefault(_QUEUE_KEY, [])
    queue.append({
        "emotion":     emotion,
        "per_s":       delta / span_s,
        "s_left":      span_s,
        "source":      source[:40],
    })


def drain_signal_queue(
    state: Dict[str, Any],
    core: Dict[str, float],
    dt: float | None = None,
) -> None:
    """
    Apply `dt` seconds' worth of buffered changes to core (in place); dt defaults
    to the last cycle's (brain/utils/clock). Exhausted entries are pruned;
    unknown emotion keys are logged and dropped.
    """
    queue: List[Dict] = state.get(_QUEUE_KEY)
    if not queue:
        return
    step = last_dt() if dt is None else max(0.0, float(dt))

    still_active: List[Dict] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        if "per_cycle" in item and "per_s" not in item:   # queued before B12
            item = {"emotion": item.get("emotion", ""),
                    "per_s": float(item.get("per_cycle") or 0) / MEAN_CYCLE_S,
                    "s_left": cycles_to_s(int(item.get("cycles_left") or 0)),
                    "source": item.get("source", "")}

        emotion = item.get("emotion", "")
        per_s   = float(item.get("per_s") or 0)
        s_left  = float(item.get("s_left") or 0)

        if s_left <= 0 or abs(per_s) * MEAN_CYCLE_S < 0.001:
            continue

        applied = min(step, s_left)
        if emotion in core:
            core[emotion] = max(0.0, min(1.0, float(core[emotion]) + per_s * applied))
        else:
            log_activity(f"[emotion_buffer] dropped delta for unknown emotion '{emotion}' (per_s={per_s:+.4f})")

        item["s_left"] = s_left - applied
        if item["s_left"] > 1e-9:
            still_active.append(item)

    state[_QUEUE_KEY] = still_active
