# brain/utils/appraisal_events.py
#
# B2 (F1, Run 13): the structured-event queue appraisal reads instead of his own
# working-memory text. Producers (goal_io._on_event for daemon goal outcomes, the
# effect ledger for credited work) queue {kind, outcome, agency, about, goal,
# certainty, novelty, repeated}; control_signals.appraisal.appraise_structured
# drains them each signal update. Agency comes from the record, not from pronouns:
# a world failure ("no URLs to fetch") is circumstance.
from __future__ import annotations

import re
import threading
from collections import deque
from typing import Any, Dict, List

_events: "deque[Dict[str, Any]]" = deque(maxlen=64)
_lock = threading.Lock()

# A daemon failure whose last_error names the world, not his own act.
_WORLD_FAILURE_RE = re.compile(
    r"no urls|no results|found nothing|fetch|http|timeout|timed out|connection|"
    r"dns|404|403|rate.?limit|unreachable|offline|telemetry|did not recur",
    re.IGNORECASE)


def failure_agency(last_error: str) -> str:
    return "circumstance" if _WORLD_FAILURE_RE.search(str(last_error or "")) else "self"


def queue_appraisal_event(event: Dict[str, Any]) -> None:
    if isinstance(event, dict) and event.get("outcome") in ("help", "block"):
        with _lock:
            _events.append(dict(event))


def drain_appraisal_events() -> List[Dict[str, Any]]:
    with _lock:
        out = list(_events)
        _events.clear()
    return out
