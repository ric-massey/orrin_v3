# utils/sys_events.py
# Tiny in-process event bus for fast wakeups

from __future__ import annotations
from brain.core.runtime_log import get_logger
import time, queue
from typing import Optional, Dict, List
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_EVENTS: List[Dict] = []
_EVTQ: "queue.SimpleQueue[Dict]" = queue.SimpleQueue()

def record_event(e: Dict) -> None:
    e = dict(e); e["ts"] = time.time()
    _EVENTS.append(e)
    if len(_EVENTS) > 500:
        _EVENTS.pop(0)
    try:
        _EVTQ.put_nowait(e)
    except Exception as _e:
        record_failure("sys_events.record_event", _e)

def recent_events(n: int = 100) -> List[Dict]:
    return list(_EVENTS[-n:])

def wait_event(timeout: float = 0.3) -> Optional[Dict]:
    try:
        return _EVTQ.get(timeout=timeout)
    except Exception:
        return None
