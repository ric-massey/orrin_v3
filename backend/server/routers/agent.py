"""Agent I/O routes: the Face ⇄ core-loop message pipeline + producer ingest.

Split out of app.py (Phase 4C). These guard themselves (auth.authorize_ingest /
reject_untrusted_origin) and operate on the shared telemetry hub, so they mount
directly on the app rather than under the read-token api router.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth import authorize_ingest, reject_untrusted_origin
from ..config import RESPONSE_CAP
from ..state import hub

router = APIRouter()


@router.post("/ingest")
async def ingest(frame: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Producer entry point used by TelemetryBridge. Merge + broadcast a delta."""
    authorize_ingest(request)
    delta = hub.merge(frame or {})
    await hub.broadcast({"type": "delta", "frame": delta})
    return {"ok": True}


# ── Input pipeline: Face → core loop → Face ──────────────────────────────────
@router.post("/api/agent/input")
async def agent_input(body: Dict[str, Any], request: Request) -> Any:
    """The Face submits a user message; queued for the core loop, surfaced on the Brain stream."""
    reject_untrusted_origin(request)
    message = str((body or {}).get("message", "")).strip()
    if not message:
        return JSONResponse({"ok": False, "error": "empty message"}, status_code=400)
    item = {
        "id": uuid.uuid4().hex[:12],
        "message": message,
        "ts": time.time(),
        "meta": (body or {}).get("meta") or {},
    }
    hub.inputs.append(item)
    delta = hub.merge({
        "logs": [{"level": "info", "source": "face", "message": f"user → {message[:140]}"}],
        "memory": [{"op": "write", "store": "inbox", "key": item["id"], "summary": message[:140]}],
    })
    await hub.broadcast({"type": "delta", "frame": delta})
    return {"ok": True, "id": item["id"]}


@router.get("/api/agent/inputs")
async def agent_inputs(request: Request) -> Dict[str, Any]:
    """Drain and return all pending Face inputs (used by the core loop)."""
    reject_untrusted_origin(request)
    items = list(hub.inputs)
    hub.inputs.clear()
    return {"inputs": items}


@router.post("/api/agent/respond")
async def agent_respond(body: Dict[str, Any], request: Request) -> Any:
    """The core loop delivers its reply for a given input id; the Face polls for it."""
    reject_untrusted_origin(request)
    rid = str((body or {}).get("id", "")).strip()
    reply = str((body or {}).get("reply", ""))
    if not rid:
        return JSONResponse({"ok": False, "error": "missing id"}, status_code=400)
    hub.responses[rid] = {"reply": reply, "ts": time.time()}
    hub.responses.move_to_end(rid)
    while len(hub.responses) > RESPONSE_CAP:
        hub.responses.popitem(last=False)  # evict oldest
    delta = hub.merge({"logs": [{"level": "info", "source": "agent", "message": f"reply → {reply[:140]}"}]})
    await hub.broadcast({"type": "delta", "frame": delta})
    return {"ok": True}


@router.get("/api/agent/response/{rid}")
async def agent_response(rid: str, request: Request) -> Dict[str, Any]:
    """One-shot fetch of the agent's reply for an input id (consumed on read)."""
    reject_untrusted_origin(request)
    r = hub.responses.pop(rid, None)
    return {"reply": r["reply"] if r else None}
