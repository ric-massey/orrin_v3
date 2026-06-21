"""Auto-update control routes (§10.7 / I7).

Split out of app.py (Phase 4C). Owner-only — both handlers self-authorize via
auth.authorize_control (they reach the network / touch state) and mount directly
on the app. The actual binary swap is the platform installer's job; these only
report and prepare a pre-update keepsake.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from ..auth import authorize_control

router = APIRouter()


@router.get("/api/update")
async def update_check(request: Request, force: bool = False) -> Dict[str, Any]:
    """Is a newer Orrin published? Opt-in (pref `auto_update_check`) unless `force=1` (an
    explicit 'Check now'). Reports only — never downloads or swaps. Owner-guarded since it
    reaches the network."""
    authorize_control(request)
    from brain.utils import updater
    return updater.check_for_update(force=bool(force))


@router.post("/api/update/prepare")
async def update_prepare(request: Request) -> Dict[str, Any]:
    """Export the mind to a keepsake BEFORE any update is applied (§10.7) — so even a
    failed update/migration leaves a restorable copy. Returns the backup path + the state
    schema version the new build must understand. The actual binary swap is the platform
    installer's job (Sparkle/Squirrel/zsync), handed off via graceful shutdown."""
    authorize_control(request)
    from brain.utils import updater
    return updater.prepare_update()
