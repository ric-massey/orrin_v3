"""Control routes that drive Orrin's lifecycle: stop / reset / restore.

Split out of app.py (Phase 4C). Owner-only — each handler self-authorizes via
auth.authorize_control and mounts directly on the app. The actual stop/reset/
restart is the orchestrator's job (main.py registers handlers); these reach that
registry through the lifecycle module's has_*/safe_* accessors so the runtime-
rebound handlers are always seen current.
"""
from __future__ import annotations

import contextlib
import os
import signal
import threading
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from .. import lifecycle
from ..auth import authorize_control
from ..state import hub

router = APIRouter()


@router.post("/api/control/shutdown")
async def control_shutdown(request: Request) -> Dict[str, Any]:
    """
    Stop Orrin from the UI.

    When the orchestrator registered a stop handler (the normal `python main.py`
    run), the Stop button halts ONLY cognition — the loop and its daemons — and
    leaves the UI/window running so you can keep viewing his (now-frozen) mind.
    Quitting the app is a separate action: close the window.

    Without a handler (standalone `backend/main.py`), there's nothing but the
    server to stop, so it falls back to a full-process SIGINT (the old behavior).

    The action fires on a short delay so this HTTP response reaches the UI first.
    """
    authorize_control(request)
    await hub.broadcast({"type": "delta", "frame": hub.merge(
        {"logs": [{"level": "warn", "source": "control", "message": "stop requested from UI"}]}
    )})

    if lifecycle.has_stop_handler():
        threading.Timer(0.2, lifecycle.safe_stop).start()
        return {"ok": True, "stopping": True, "scope": "cognition"}

    def _trigger() -> None:
        # Default SIGINT handler raises KeyboardInterrupt in the main thread,
        # which both the embedded launcher and standalone uvicorn.run() handle.
        with contextlib.suppress(Exception):
            os.kill(os.getpid(), signal.SIGINT)

    threading.Timer(0.4, _trigger).start()
    return {"ok": True, "stopping": True, "scope": "process"}


@router.post("/api/mind/import")
async def mind_import(request: Request) -> Dict[str, Any]:
    """Restore a mind from a raw archive (request body = the .orrindmind bytes). The
    current mind is snapshotted FIRST; a bad/foreign/newer archive is refused and the
    running mind is left untouched. On success Orrin restarts so the new state loads."""
    authorize_control(request)
    from brain.utils import mind_archive as _ma
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty body — send the archive bytes")
    try:
        result = _ma.import_archive(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if lifecycle.has_restart_handler():
        threading.Timer(0.4, lifecycle.safe_restart).start()
        result["restarting"] = True
    return result


@router.post("/api/control/reset")
async def control_reset(request: Request) -> Dict[str, Any]:
    """Wipe Orrin to a newborn and re-launch. Destructive — same guard as shutdown,
    and the UI gates it behind an explicit confirm. The actual wipe/reseed/restart is
    the orchestrator's job (main.py registered the handler); fires on a short delay so
    this response reaches the UI first."""
    authorize_control(request)
    if not lifecycle.has_reset_handler():
        raise HTTPException(status_code=503, detail="reset is unavailable in this run mode")
    await hub.broadcast({"type": "delta", "frame": hub.merge(
        {"logs": [{"level": "warn", "source": "control", "message": "reset requested from UI — Orrin is becoming a newborn"}]}
    )})
    threading.Timer(0.3, lifecycle.safe_reset).start()
    return {"ok": True, "resetting": True}
