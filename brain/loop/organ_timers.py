# brain/loop/organ_timers.py
#
# RUN4_FIX_PLAN §B2 — timer-protect the consolidation organs (interim, until
# the SL1–SL5 sleep-restoration plan).
#
# The integrative organs (world-model audit, symbolic prediction/rule firing,
# symbolic consolidation / crystallization / concepts) are ignition-gated: they
# only run when the deliberation gate happens to select them. Under an ignition
# monopoly (2026-07-03: social_presence won 84% of ignitions) they went dark by
# hour 3, while the 3-hour dream timer never missed (5/5) — because the dream has
# its OWN timer, not an ignition gate. This module copies that dream cadence
# pattern: each organ has a last-ran timestamp and a timer fallback. If ignition
# hasn't run an organ within _ORGAN_INTERVAL_S, one runs in a protected slot
# (finalize), so consolidation survives even a jammed ignition diet.
#
# B1 fixes the monopoly at the root; this is the belt-and-suspenders safety net.
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from brain.core.runtime_log import get_logger
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

# Registered cognition-function name → its last run time (ignition OR timer).
# Seeded at import so the first fallback fires ~one interval after boot, not
# immediately (boot already runs a warm cycle).
_PROTECTED_ORGANS = (
    "audit_map_territory",          # world-model / map-territory audit
    "run_symbolic_prediction_cycle",  # rule firing / prediction
    "run_symbolic_consolidation",   # symbolic concepts / crystallization
)

_ORGAN_INTERVAL_S = 75 * 60   # 75 min — inside the plan's 60–90 min band
_lock = threading.Lock()
_last_ran: Dict[str, float] = {name: time.time() for name in _PROTECTED_ORGANS}


def mark_ran(name: str) -> None:
    """Record that an organ ran (called from the cognition dispatch chokepoint so
    an ignition-driven run resets its timer, exactly like a dream resets its own)."""
    if name in _last_ran:
        with _lock:
            _last_ran[name] = time.time()


def due_organs(now: float | None = None) -> List[str]:
    """Organs whose last run (ignition or timer) is older than the interval."""
    now = time.time() if now is None else now
    with _lock:
        return [name for name, ts in _last_ran.items()
                if (now - ts) >= _ORGAN_INTERVAL_S]


def run_due_organs(context: Dict[str, Any] | None = None, *, limit: int = 1) -> List[str]:
    """Run up to `limit` overdue organs in this protected slot (default 1 so a
    backlog spreads across cycles rather than bursting). Each is invoked through
    its registered cognition function; failures are recorded, never raised. Marks
    each attempted organ ran (success or not) so a persistently-failing organ
    doesn't retry every cycle. Returns the organ names run this slot."""
    due = due_organs()
    if not due:
        return []
    try:
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
    except Exception as _e:
        record_failure("organ_timers.registry", _e)
        return []
    ran: List[str] = []
    for name in due[:max(1, int(limit))]:
        meta = COGNITIVE_FUNCTIONS.get(name)
        fn = meta.get("function") if isinstance(meta, dict) else meta
        mark_ran(name)   # stamp before running: a crash must not cause a retry storm
        if not callable(fn):
            continue
        try:
            fn(context) if context is not None else fn()
            ran.append(name)
            log_activity(f"[organ_timers] ran '{name}' via timer fallback "
                         f"(ignition hadn't in {_ORGAN_INTERVAL_S // 60} min)")
        except TypeError:
            # Some organs take no context — retry arg-less.
            try:
                fn()
                ran.append(name)
                log_activity(f"[organ_timers] ran '{name}' via timer fallback (no-arg)")
            except Exception as _e:
                record_failure(f"organ_timers.run.{name}", _e)
        except Exception as _e:
            record_failure(f"organ_timers.run.{name}", _e)
    return ran


def reset_for_tests(now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _lock:
        for name in _PROTECTED_ORGANS:
            _last_ran[name] = now
