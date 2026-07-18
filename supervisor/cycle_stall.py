# supervisor/cycle_stall.py
# Watchdog: the cognitive loop's production_loop cycle stamp must keep advancing.

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)

GetCycle = Callable[[], int]
OnViolation = Callable[[str], None]

# A cycle is ~3.3 s; 900 s of zero advance while the process lives is a dead
# cognitive loop, not a slow one. Kept generous so a legitimately heavy pause
# (host guard pausing heavy cycles, model loads) can never false-trip.
DEFAULT_MAX_STALL_S = 900.0
# The watchdog thread steps at ~100 Hz; the provider reads a file tail, so the
# guard rate-limits its own sampling.
DEFAULT_POLL_INTERVAL_S = 5.0


@dataclass
class CycleStallGuard:
    """Cycle-stall tripwire (Run 8 §0 owed item).

    The Run 8 crash killed the brain thread mid-cycle 4418 while surviving
    threads kept feeding the pulse-based heartbeat — the dead cognitive loop sat
    unnoticed for 6.5 h. This guard keys on the `production_loop.jsonl` cycle
    stamp, the only counter proven crash-accurate at that seam (the heartbeat
    lagged 18 cycles, block-buffered stdout ~160). If the stamp stops advancing
    for `max_stall_s` while the process lives, Supervisor triggers and the
    process restarts cleanly instead of running headless-brained.

    Provider contract: return the latest stamped cycle, or a negative value for
    "no stamp available" (fresh boot, empty file). The guard arms only after the
    first valid stamp is observed; any CHANGE of the stamp (including the reset
    to low values at a new life) counts as progress. One-shot: after a trip it
    stays quiet until the stamp moves again.
    """
    get_cycle: GetCycle
    on_violation: OnViolation
    max_stall_s: float = DEFAULT_MAX_STALL_S
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S

    _last_cycle: Optional[int] = None
    _last_change_ts: float = 0.0
    _last_poll_ts: float = 0.0
    _tripped: bool = False

    def step(self) -> None:
        now = time.monotonic()
        if now - self._last_poll_ts < self.poll_interval_s:
            return
        self._last_poll_ts = now
        try:
            cycle = int(self.get_cycle())
        except Exception as _e:
            _log.warning("silent except: %s", _e)
            return
        if cycle < 0:
            return  # not armed: no stamp yet
        if self._last_cycle is None or cycle != self._last_cycle:
            self._last_cycle = cycle
            self._last_change_ts = now
            self._tripped = False
            return
        stalled_s = now - self._last_change_ts
        if stalled_s >= self.max_stall_s and not self._tripped:
            self._tripped = True
            self.on_violation(
                f"HARD:cycle_stall production_loop cycle={cycle} "
                f"unchanged for {stalled_s:.0f}s (limit {self.max_stall_s:.0f}s)"
            )
