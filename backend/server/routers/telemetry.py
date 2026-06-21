"""Read-only telemetry/projection routes (the api read router).

Split out of app.py (Phase 4C). These are GET projections over Orrin's persisted
state files — what the Face & Brain UI renders. They are mounted on the read `api`
router by app.py (so they inherit the optional read-token guard) and use the shared
read helpers in state.py. Routes are moved here in cohesive domain batches.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import state as server_state
from ..state import _read_json

router = APIRouter()


# ── Consolidation / language / monitor ledgers ──────────────────────────────
@router.get("/dreams")
async def dreams(n: int = 12) -> JSONResponse:
    """What he consolidates while idle: dream_log sweeps + symbolic dream
    insights. Honesty note: consolidation/recombination are often EMPTY strings
    on a fresh run — the client must render 'slept, nothing consolidated'
    rather than blank cards."""
    cap = max(1, min(50, n))
    dl = [d for d in _read_json("dream_log.json", []) if isinstance(d, dict)]
    sd = [d for d in _read_json("symbolic_dream_log.json", []) if isinstance(d, dict)]
    return JSONResponse({"dreams": dl[-cap:], "symbolic": sd[-cap:], "total": len(dl)})


@router.get("/language")
async def language(n: int = 12) -> JSONResponse:
    """The from-scratch language organ: phrase banks, learned phrases, recent
    speech (+ quality scores), books read, and the native LM artifact sizes."""
    vocab = _read_json("vocabulary.json", {})
    banks = {k: len(v) for k, v in vocab.items()
             if not str(k).startswith("_") and isinstance(v, (list, dict))}
    speech = [s for s in _read_json("speech_log.json", []) if isinstance(s, dict)]
    cap = max(1, min(50, n))
    recent = [{"ts": s.get("timestamp"), "reply": str(s.get("reply") or "")[:240],
               "quality": s.get("quality_score")} for s in speech[-cap:]]

    def _artifact_size(fname: str) -> Any:
        try:
            return (server_state._DATA_DIR / "language" / fname).stat().st_size
        except Exception:
            return None

    return JSONResponse({
        "phrase_banks": banks,
        "learned_phrases": len(_read_json("learned_phrases.json", {}) or {}),
        "speech_total": len(speech),
        "speech_recent": recent,
        "books_read": _read_json("language/book_reads.json", {}),
        "native_lm_bytes": _artifact_size("native_lm.pt"),
        "tokenizer_bytes": _artifact_size("tokenizer.json"),
    })


@router.get("/verdicts")
async def verdicts(n: int = 120) -> JSONResponse:
    """§20.1 dismissal-recalibration over time (Fix 4 step 5): the rolling
    honored/dismissed verdict ledger per breakthrough kind, plus the current
    learned per-kind bias — 'who watches the watcher', browsable."""
    log = [v for v in _read_json("monitor_verdicts.json", []) if isinstance(v, dict)]
    return JSONResponse({
        "verdicts": log[-max(1, min(300, n)):],
        "bias": _read_json("monitor_kind_bias.json", {}),
        "total": len(log),
    })


@router.get("/forgetting")
async def forgetting(n: int = 30) -> JSONResponse:
    """The forgetting ledger (decayed/pruned/retired per sweep) — memory staying
    bounded is only believable when you can watch him forget (pairs with B1)."""
    log = [f for f in _read_json("forgetting_log.json", []) if isinstance(f, dict)]
    return JSONResponse({"sweeps": log[-max(1, min(100, n)):], "total": len(log)})


# ── Lifecycle / boot / trust ledgers ────────────────────────────────────────
@router.get("/lifecycle")
async def lifecycle() -> JSONResponse:
    """Tell death / interrupted (crash-or-stall) / alive apart (§10.5), so the UI can
    route to the Death Screen, a 'restarting' note, or normal viewing on launch."""
    try:
        from brain.utils.lifecycle import status as _status
        return JSONResponse(_status())
    except Exception as e:
        return JSONResponse({"state": "alive", "error": str(e)})


@router.get("/boot")
async def boot() -> JSONResponse:
    """The boot sequence (§9.7): ordered, truthful startup milestones + a `ready` flag.
    The wake-up screen polls this and dissolves into Cognition once ready. A warm
    reopen (brain already up) returns ready immediately."""
    try:
        from brain.utils.boot_events import snapshot as _boot_snapshot
        return JSONResponse(_boot_snapshot())
    except Exception as e:
        return JSONResponse({"events": [], "ready": True, "error": str(e)})


@router.get("/egress")
async def egress(window_s: float = 86400.0) -> JSONResponse:
    """The egress ledger (§9.4): per-service rollup of outbound calls over the last
    window (default 24h) — counts/timestamps only, never a prompt or query. With no
    keys set, Orrin runs symbolic-only and this stays at zero, which is what lets the
    Trust screen say 'nothing leaves your machine.'"""
    try:
        from brain.utils.egress import summary as _egress_summary
        return JSONResponse(_egress_summary(window_s))
    except Exception as e:
        return JSONResponse({"services": {}, "total_requests": 0, "error": str(e)})


@router.get("/permissions")
async def permissions() -> JSONResponse:
    """OS capability grant-state for the Trust screen (§10.6): per-capability whether
    Orrin's body can see your screen / control apps / notify you, with a deep-link to
    the right System Settings pane. Non-prompting; honest about what's off."""
    try:
        from brain.utils.os_permissions import status as _perm_status
        return JSONResponse(_perm_status())
    except Exception as e:
        return JSONResponse({"platform": "", "capabilities": [], "error": str(e)})
