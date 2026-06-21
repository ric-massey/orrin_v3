"""Diagnostics / export / Life Capsule control routes.

Split out of app.py (Phase 4C). These are owner-only control surfaces, not read
endpoints — each handler self-authorizes via auth.authorize_control, so the
router is mounted directly on the app (NOT under the read-token-guarded api
router). Brain modules are imported lazily inside the handlers, exactly as in
app.py, so importing this module stays cheap.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Response

from ..auth import authorize_control

router = APIRouter()


# ── Mind export (§9.6) ───────────────────────────────────────────────────────
@router.get("/api/mind/export")
async def mind_export(request: Request):
    """Stream the full mind as one portable archive (both state trees, atomically).
    Guarded like every control surface."""
    authorize_control(request)
    from brain.utils import mind_archive as _ma
    data = _ma.export_bytes()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_ma.export_filename()}"'},
    )


# ── Diagnostics export (§10.7) ───────────────────────────────────────────────
@router.get("/api/diagnostics")
async def diagnostics_export(request: Request):
    """Stream an opt-in diagnostics bundle: recent operational logs + the boot/death/
    crash state tag (§10.5) and schema version — NEVER memory content or private
    thoughts (the module enforces an allowlist). Owner-only, guarded like every control
    surface; no silent telemetry — the user chooses to send it."""
    authorize_control(request)
    from brain.utils import diagnostics as _diag
    data = _diag.export_bytes()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_diag.export_filename()}"'},
    )


# ── Life Capsule (the evidence export — Part IX) ─────────────────────────────
@router.get("/api/life/capsules")
async def life_capsules(request: Request) -> Dict[str, Any]:
    """Catalog of sealed Life Capsules (newest first). Owner-only like every control
    surface."""
    authorize_control(request)
    from brain.evidence import life_capsule as _lc
    return {"capsules": _lc.list_capsules()}


@router.get("/api/life/capsule/summary")
async def life_capsule_summary(request: Request, run: str = "latest") -> Dict[str, Any]:
    """The inline-renderable summary for one capsule (executive summary + key metrics +
    claims) — for rendering in the Capsule panel without downloading the whole zip."""
    authorize_control(request)
    from brain.evidence import life_capsule as _lc
    summary = _lc.read_capsule_summary(run)
    if summary is None:
        raise HTTPException(status_code=404, detail="no capsule found")
    return summary


@router.post("/api/life/capsule/build")
async def life_capsule_build(request: Request) -> Dict[str, Any]:
    """Build a capsule from the current data on demand (reason=manual). Read-only over
    Orrin's state; returns the new capsule's catalog entry."""
    authorize_control(request)
    from brain.evidence import life_capsule as _lc
    path = _lc.build_life_capsule("manual")
    return {"ok": True, "file": path.name, "size_bytes": path.stat().st_size}


@router.get("/api/life/capsule")
async def life_capsule_download(request: Request, run: str = "latest"):
    """Stream a sealed `.orrinlife.zip` (the evidence export). Owner-only."""
    authorize_control(request)
    from brain.evidence import life_capsule as _lc
    path = _lc.capsule_path(run)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="no capsule found")
    return Response(
        content=path.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )
