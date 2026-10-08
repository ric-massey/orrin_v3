# brain/utils/clock.py
#
# B12 / CT-A (CONTINUOUS_TIME_DESIGN_2026-10-04 §2): one clock for time that
# means TIME. Orrin's decays, drains and staleness counted cycles, so their
# meaning moved with cadence (a 2 s cycle aged things twice as fast as a 4 s
# one). The loop ticks this clock once per cycle; time-denominated state then
# advances by the seconds that passed, expressed through a shim in
# mean-cycle-equivalents (cycles_to_s / cycle_equivalents) so behaviour is
# unchanged at Run 12's mean awake cycle and constants keep their names.
#
# Monotonic time does not advance while the host is suspended; the suspension
# itself is credited to the lifespan by runtime_lifetime.detect_suspension,
# which runs beside tick(). Counters of EVENTS (failures, rounds, repeats) are
# not time and stay counts.
from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, Optional

MEAN_CYCLE_S = 4.0     # Run 12's mean awake cycle — the cycles→seconds shim
_MAX_DT_S = 120.0      # a longer gap is a stall, not lived time: never one giant step

_lock = threading.Lock()
_last_mono: Optional[float] = None
_last_dt: float = MEAN_CYCLE_S


def now() -> float:
    return time.monotonic()


def tick(context: Optional[Dict[str, Any]] = None, *, mono: Optional[float] = None) -> float:
    """Advance the cycle clock; returns this cycle's dt in seconds and stamps it
    on context["_dt_s"]. The first tick of a process returns MEAN_CYCLE_S."""
    global _last_mono, _last_dt
    m = now() if mono is None else float(mono)
    with _lock:
        dt = MEAN_CYCLE_S if _last_mono is None else max(0.0, min(_MAX_DT_S, m - _last_mono))
        _last_mono, _last_dt = m, dt
    if isinstance(context, dict):
        context["_dt_s"] = dt
    return dt


def last_dt() -> float:
    """Seconds the most recent cycle took (MEAN_CYCLE_S before the first tick)."""
    return _last_dt


def cycles_to_s(n: float) -> float:
    return float(n) * MEAN_CYCLE_S


def cycle_equivalents(dt: Optional[float] = None) -> float:
    """dt (default: the last cycle's) in mean-cycle units — the step a counter
    that used to advance 1 per cycle should advance now."""
    return (last_dt() if dt is None else float(dt)) / MEAN_CYCLE_S


def decay(x: float, dt: float, half_life_s: float) -> float:
    """Leaky integration in seconds: x·0.5^(dt/half_life)."""
    if half_life_s <= 0:
        return 0.0
    return float(x) * math.pow(0.5, max(0.0, float(dt)) / float(half_life_s))


def reset() -> None:
    """Forget the last tick (tests; a fresh process starts here too)."""
    global _last_mono, _last_dt
    with _lock:
        _last_mono, _last_dt = None, MEAN_CYCLE_S
