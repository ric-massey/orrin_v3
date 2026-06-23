"""Source-inspection routes: read-only, repo-jailed views of source files.

Split out of app.py (Phase 4C). `/source` serves a slice of any repo source file
(for the metric info pages); `/code` serves the real source of a registered
cognitive function (resolved via the shared telemetry hub's catalog). Both are
jailed to the repo root (`server_state._REPO_ROOT`) and mounted on the read API
router by app.py.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from brain.utils.failure_counter import record_failure

from .. import state as server_state

router = APIRouter()

# Source-file allow-list (H1 defense-in-depth): only these suffixes can be read
# through the repo jail, so it can't be turned into a secret reader (.env, keys…).
_SOURCE_OK_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".css", ".txt", ".yml", ".yaml"}


@router.get("/source")
async def source(file: str = "", start: int = 1, end: int = 0) -> JSONResponse:
    """Return a read-only slice of a repo source file (for the metric info pages)."""
    try:
        target = (server_state._REPO_ROOT / file).resolve()
        rel = target.relative_to(server_state._REPO_ROOT)  # repo-jail
        # Defense-in-depth (H1): forbid dotfiles/dotdirs and non-source types so
        # the jail can't be turned into a secret reader (.env, .git/*, …).
        if any(part.startswith(".") for part in rel.parts):
            return JSONResponse({"error": "forbidden path", "file": file}, status_code=403)
        if target.suffix.lower() not in _SOURCE_OK_SUFFIXES:
            return JSONResponse({"error": "unsupported file type", "file": file}, status_code=403)
        lines = target.read_text("utf-8", errors="replace").splitlines()
        lo = max(1, int(start))
        hi = min(len(lines), int(end) if end else len(lines))
        src = "\n".join(lines[lo - 1 : hi])
        if len(src) > 80_000:
            src = src[:80_000] + "\n… (truncated)"
        return JSONResponse({"file": file, "start": lo, "end": hi, "source": src})
    except Exception as e:
        record_failure("routers.source.file", e)
        return JSONResponse({"error": str(e), "file": file}, status_code=400)


@router.get("/code")
async def code(fn: str = "") -> JSONResponse:
    """Return the real source of a cognitive function (read-only)."""
    cat = server_state.hub.state.get("catalog") or {}
    info = (cat.get("functions") or {}).get(fn)
    if not info:
        return JSONResponse({"error": "unknown function", "fn": fn}, status_code=404)
    rel = str(info.get("file") or "")
    try:
        target = (server_state._REPO_ROOT / rel).resolve()
        # Safety: only serve files inside the repo.
        target.relative_to(server_state._REPO_ROOT)
        lines = target.read_text("utf-8", errors="replace").splitlines()
        lo = max(1, int(info.get("lineno", 1)))
        hi = min(len(lines), int(info.get("endline", lo)))
        src = "\n".join(lines[lo - 1 : hi])
        if len(src) > 60_000:
            src = src[:60_000] + "\n… (truncated)"
        return JSONResponse({"fn": fn, "file": rel, "lineno": lo, "endline": hi, "source": src})
    except Exception as e:
        record_failure("routers.source.code", e)
        return JSONResponse({"error": str(e), "fn": fn}, status_code=500)
