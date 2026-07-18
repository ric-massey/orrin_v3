# brain/symbolic/external_observer.py
#
# R10-11 — one outward causal edge.
#
# THE PROBLEM (Run 9 skeptic pass, item 13)
# After a full life the causal graph held 241 edges, 100 % interoceptive
# ("attend_goal → exploration_drive rises"). The world model contained no world,
# which makes the `world_knowledge` aspiration structurally unsatisfiable by the
# graph — the causal learner only ever watched Orrin's own signals react to
# Orrin's own actions.
#
# THE FIX
# Feed the same causal learner at least one EXTERNAL observable stream, so ≥1
# edge at death has a cause or effect that is not an internal signal/action. The
# most reliable such stream needs no network and is always present: the host's
# own load as a function of time of day. Both endpoints are world facts (not
# Orrin's affect/functions), so causal_graph tags the edge domain="world".
#
# Honest and cheap: this records a genuine co-occurrence Orrin can observe
# (wall-clock hour ↔ how busy the machine it runs on is), throttled so it banks
# evidence over a life rather than spamming one edge every cycle.
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional

from brain.utils.failure_counter import record_failure

# Bank one observation at most this often (wall-clock seconds). A life is hours
# long, so this still accumulates dozens of evidence points per hour-band while
# keeping evidence_count meaningful (cf. R10-10: a count should mean evidence).
_MIN_INTERVAL_S = 600.0
_last_obs_ts: float = 0.0


def _time_band(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _load_band(cpu_util: float) -> str:
    if cpu_util >= 0.66:
        return "busy"
    if cpu_util >= 0.33:
        return "moderate"
    return "quiet"


def observe_external_causality(vitals: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
    """Record one external world causal observation: time-of-day → host load.

    Returns the edge dict if an observation was banked, else None (throttled or
    no vitals). Fail-safe; never raises into the caller."""
    global _last_obs_ts
    now = time.time()
    if (now - _last_obs_ts) < _MIN_INTERVAL_S:
        return None
    try:
        cpu = None
        if isinstance(vitals, dict):
            cpu = vitals.get("cpu_util")
        if cpu is None:
            # Fall back to a direct sample so the stream works even when no
            # caller threads vitals through.
            try:
                import psutil  # type: ignore
                cpu = float(psutil.cpu_percent(interval=None)) / 100.0
            except Exception as _pe:
                record_failure("external_observer.cpu_sample", _pe)
                return None
        cpu = max(0.0, min(1.0, float(cpu)))
        hour = datetime.now().hour
        cause = f"time of day is {_time_band(hour)}"
        effect = f"host machine is {_load_band(cpu)}"
        from brain.symbolic.causal_graph import update_edge
        edge = update_edge(cause, effect, confirmed=True, source="external_stream")
        _last_obs_ts = now
        return edge
    except Exception as exc:
        record_failure("external_observer.observe_external_causality", exc)
        return None
