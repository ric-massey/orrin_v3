# brain/events.py
# Minimal event recording and wait/notify queue.
from __future__ import annotations
from brain.core.runtime_log import get_logger
import hashlib, json, time, queue
_log = get_logger(__name__)

_EVENTS: list[dict] = []
_EVTQ: "queue.SimpleQueue[dict]" = queue.SimpleQueue()

# Idempotency guard (BEHAVIOR_FIX_PLAN Phase 4 / audit §9-10): drop an event
# identical (type + payload hash) to one emitted within the dedup window —
# duplicated self-model writes, mode-change double-fires, and repeated
# oscillation alerts all share this one fix.
_DEDUP_WINDOW_S = 10.0
_recent_hashes: dict[str, float] = {}


def _event_hash(e: dict) -> str:
    payload = {k: v for k, v in e.items() if k != "ts"}
    try:
        blob = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        blob = repr(sorted(payload.items(), key=lambda kv: str(kv[0])))
    return hashlib.sha256(blob.encode()).hexdigest()


def record_event(e: dict) -> None:
    e = dict(e); e["ts"] = time.time()
    h = _event_hash(e)
    last = _recent_hashes.get(h)
    if last is not None and (e["ts"] - last) < _DEDUP_WINDOW_S:
        return  # identical event within the window — drop the duplicate
    if len(_recent_hashes) > 500:
        _cut = e["ts"] - _DEDUP_WINDOW_S
        for k in [k for k, t in _recent_hashes.items() if t < _cut]:
            del _recent_hashes[k]
    _recent_hashes[h] = e["ts"]
    _EVENTS.append(e)
    if len(_EVENTS) > 500: _EVENTS.pop(0)
    try: _EVTQ.put_nowait(e)
    except Exception:
        _log.warning("silent except")

def recent_events(n: int = 100) -> list[dict]:
    return list(_EVENTS[-n:])

def wait_event(timeout: float = 0.3) -> dict | None:
    try: return _EVTQ.get(timeout=timeout)
    except Exception: return None
