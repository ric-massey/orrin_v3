"""
utils/boot_events.py — the truthful boot sequence (§9.7).

main.py emits a milestone as each subsystem actually comes up; the wake-up screen
reads them via GET /api/boot and shows them resolving in real order. The checklist
reflects *real* readiness, so a stall on "Loading memory…" is a genuine signal, never
theatre. A single in-process buffer (writer = main.py, reader = the server thread).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

_LOCK = threading.Lock()
_EVENTS: List[Dict[str, Any]] = []
_READY = False
_NEWBORN = False  # True when this boot seeded a fresh mind (drives First Wake §9.2)


def emit(step: str, ok: bool = True, note: str = "") -> None:
    """Record one boot milestone (truthfully — call it AFTER the subsystem is up, or
    with ok=False if it failed)."""
    with _LOCK:
        _EVENTS.append({"step": str(step), "ok": bool(ok), "note": str(note), "ts": time.time()})


def mark_ready() -> None:
    """Cognition is live — the wake screen can dissolve into the Cognition view."""
    global _READY
    with _LOCK:
        _READY = True


def set_newborn(value: bool) -> None:
    global _NEWBORN
    with _LOCK:
        _NEWBORN = bool(value)


def snapshot() -> Dict[str, Any]:
    with _LOCK:
        return {"events": list(_EVENTS), "ready": _READY, "newborn": _NEWBORN}
