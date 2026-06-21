# reaper/heartbeatdetector.py
# Detects heartbeat (pulse) irregularities: too fast, too slow (stale)

from __future__ import annotations
from brain.core.runtime_log import get_logger
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional
from collections import deque
import time

# METRICS: heartbeat gauges/histogram
try:
    from observability.metrics import (
        hb_avg_period_ms, hb_fast_streak, hb_slow_streak, hb_interval_ms
    )
except Exception:
    hb_avg_period_ms = hb_fast_streak = hb_slow_streak = hb_interval_ms = None  # type: ignore
_log = get_logger(__name__)

PulseProvider = Callable[[], int]

@dataclass
class HeartbeatDetector:
    get_pulse: PulseProvider
    on_violation: Callable[[str], None]
    min_period_ms: float = 5.0
    max_period_ms: float = 10_000.0
    # Boot grace: before the first real pulse interval is recorded, the "average"
    # is just the raw age since boot (see _avg_period_ms fallback). A cold start's
    # first pulse does heavy init (loading multi-MB state files, warming caches, the
    # first LLM call) and can legitimately take far longer than the steady-state
    # slow cap — that is boot latency, not a stalled heartbeat. Until at least one
    # genuine interval exists we judge "too slow" against this generous threshold
    # instead of max_period_ms. (Polling is 100 Hz with sustain=10, so without this
    # the detector tripped within ~100 ms of boot-age crossing 10 s and killed the
    # process before cycle 1 ever completed.)
    boot_grace_ms: float = 120_000.0
    sustain_checks_fast: int = 100
    sustain_checks_slow: int = 10
    window: int = 64

    _last_pulse: Optional[int] = None
    _last_ts: Optional[float] = None
    _intervals_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=256))
    _fast_streak: int = 0
    _slow_streak: int = 0

    def step(self) -> None:
        now = time.monotonic()
        pulse = self.get_pulse()

        if self._last_pulse is None:
            self._last_pulse = pulse
            self._last_ts = now
            return

        if pulse != self._last_pulse:
            dt_ms = (now - self._last_ts) * 1000.0
            self._intervals_ms.append(dt_ms)
            # metrics: observe interval
            if hb_interval_ms is not None:
                try: hb_interval_ms.observe(dt_ms)
                except Exception:
                    _log.warning("silent except")
            self._last_ts = now
            self._last_pulse = pulse

        # If nothing has changed yet, treat as "stale" (slow) using age
        last_ts = self._last_ts if self._last_ts is not None else now
        age_ms = (now - last_ts) * 1000.0
        avg_ms = self._avg_period_ms(age_ms)

        # metrics: export avg & streaks after we compute them
        # Update streaks
        if avg_ms < self.min_period_ms:
            self._fast_streak += 1
        else:
            self._fast_streak = 0

        # Pre-first-pulse, avg_ms == raw boot age; judge it against the lenient
        # boot grace so cold-start init isn't mistaken for a stalled heartbeat.
        _slow_cap = self.max_period_ms if self._intervals_ms else self.boot_grace_ms
        if avg_ms > _slow_cap:
            self._slow_streak += 1
        else:
            self._slow_streak = 0

        if hb_avg_period_ms is not None:
            try:
                hb_avg_period_ms.set(avg_ms)
                hb_fast_streak.set(self._fast_streak)
                hb_slow_streak.set(self._slow_streak)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        if self._fast_streak >= self.sustain_checks_fast:
            self.on_violation(f"HARD:pulse_too_fast avg_ms={avg_ms:.2f}")
        if self._slow_streak >= self.sustain_checks_slow:
            self.on_violation(f"HARD:pulse_too_slow avg_ms={avg_ms:.2f}")

    def _avg_period_ms(self, fallback_ms: float) -> float:
        if not self._intervals_ms:
            return fallback_ms
        n = min(len(self._intervals_ms), self.window)
        tail = list(self._intervals_ms)[-n:]
        return sum(tail) / max(1, len(tail))
