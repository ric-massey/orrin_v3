# reaper/lifespan.py
# Watchdog: triggers Reaper when total cycles (pulse) exceed a secret random limit
#
# Scope: this is a PER-PROCESS uptime cutoff — the pulse counter is in-memory
# and resets on every restart. The agent's persistent lifespan (days since
# birth, survives restarts) is owned by brain/cognition/mortality.py; that is
# the single source of truth for "when does Orrin die". The cycle range must be
# supplied by the caller (watchdogs.start_watchdogs) — there are deliberately
# no defaults here, so this limit can't silently diverge from the configured one.

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
import secrets

GetPulse = Callable[[], int]
OnViolation = Callable[[str], None]

@dataclass
class LifespanByCycles:
    """
    Picks a secret random cycle limit in [min_cycles, max_cycles].
    When total cycles (pulse) reach/exceed that limit, triggers Reaper.
    """
    get_pulse: GetPulse
    on_violation: OnViolation
    min_cycles: int
    max_cycles: int
    _limit: Optional[int] = None

    def _ensure_limit(self) -> None:
        if self._limit is None:
            span = self.max_cycles - self.min_cycles
            # inclusive range → add 1
            r = secrets.randbelow(span + 1)
            self._limit = self.min_cycles + r

    def step(self) -> None:
        self._ensure_limit()
        n = self.get_pulse()
        if n >= (self._limit or 0):
            self.on_violation(f"HARD:lifespan_reached cycles={n} limit={self._limit}")
            # one-shot; after triggering, no need to reset (we expect shutdown)
