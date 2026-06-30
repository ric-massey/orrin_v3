"""Quality-standard evolution review queue + audit + ratify routes (P6).

Two surfaces with different trust levels:

* ``read_router`` — the read-only audit view (queue + applied/rejected history with
  provenance). Mounted under the read-token ``api`` router, so the Learning page can
  poll it. Inspection only; it can change nothing.
* ``router`` — the HUMAN ratify actions (approve / reject / restore), the ONLY path
  that may loosen the golden set. Self-authorizes via auth.authorize_control and is
  mounted directly on the app. The control auth IS the human-in-the-loop guarantee:
  cognition has no control token and no import path to this component (design §4.3 #4,
  enforced by an import-guard test). Brain modules are imported lazily in handlers.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ..auth import authorize_control

# Read-only (mounted under the read-token api router — no per-handler auth needed).
read_router = APIRouter()
# Mutating control surface (self-authorizes per handler).
router = APIRouter()


@read_router.get("/quality-standard/review")
async def quality_standard_review() -> Dict[str, Any]:
    """The human-ratify queue + applied/rejected audit trail with provenance (read-only)."""
    from brain.cognition.quality_standard import audit as _audit
    return _audit.summary()


def _candidate_id(body: Any) -> str:
    cid = str((body or {}).get("id") or "")
    if not cid:
        raise HTTPException(status_code=400, detail="missing candidate id")
    return cid


@router.post("/api/quality-standard/approve")
async def quality_standard_approve(request: Request) -> Dict[str, Any]:
    """Apply a human-ratified change (the only path that loosens the bar). Re-runs the
    regression as the gate; refuses on red. Returns (applied, message)."""
    authorize_control(request)
    cid = _candidate_id(await request.json())
    from brain.cognition.quality_standard import ratify as _ratify
    applied, message = _ratify.approve(cid, reviewer="ui")
    return {"applied": applied, "message": message}


@router.post("/api/quality-standard/reject")
async def quality_standard_reject(request: Request) -> Dict[str, Any]:
    authorize_control(request)
    body = await request.json()
    cid = _candidate_id(body)
    from brain.cognition.quality_standard import ratify as _ratify
    row = _ratify.reject(cid, reviewer="ui", reason=str((body or {}).get("reason") or ""))
    return {"ok": row is not None}


@router.post("/api/quality-standard/restore")
async def quality_standard_restore(request: Request) -> Dict[str, Any]:
    """Reverse an applied removal from its logged provenance (reversibility, §5)."""
    authorize_control(request)
    cid = _candidate_id(await request.json())
    from brain.cognition.quality_standard import ratify as _ratify
    ok, message = _ratify.restore(cid, reviewer="ui")
    return {"ok": ok, "message": message}
