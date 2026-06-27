# supervisor/trend.py
# Shared time-series helpers for the resource watchdogs.
#
# Both HostResourceGuard (host_resources.py) and MemoryHealthGuard (memory.py)
# sample (timestamp, value) points into bounded deques and ask the same three
# questions of them: drop stale points, is the window wide enough to judge yet,
# and what is the least-squares slope. These were byte-identical @staticmethods
# duplicated across both files (structure audit §8 "duplicate helper
# implementations"); consolidated here as plain functions so the trend math lives
# in one place. Kept inside `supervisor` per the audit's guidance that numeric trend
# helpers belong with the guards that use them.
from __future__ import annotations

from typing import Deque, Optional, Tuple

# A bounded series of (timestamp_seconds, value) samples.
Samples = Deque[Tuple[float, float]]


def trim(dq: Samples, cutoff: float) -> None:
    """Drop samples older than `cutoff` (a timestamp) from the left."""
    while dq and dq[0][0] < cutoff:
        dq.popleft()


def window_ok(dq: Samples, need_s: float) -> bool:
    """True once the deque spans ~`need_s` seconds (5% slack against sampling
    jitter) and holds at least two points."""
    if len(dq) < 2:
        return False
    span = dq[-1][0] - dq[0][0]
    return span >= need_s * 0.95


def slope(dq: Samples) -> Optional[float]:
    """Least-squares slope d(value)/d(time) over the (t, v) samples, or None when
    there are fewer than two points or the times are degenerate."""
    n = len(dq)
    if n < 2:
        return None
    sx = sy = sxx = sxy = 0.0
    for t, v in dq:
        sx += t; sy += v
        sxx += t * t; sxy += t * v
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        return None
    return (n * sxy - sx * sy) / denom
