"""
backend/server/app.py — FastAPI application + routes.

                 producers                         consumers
    (cognitive loop via TelemetryBridge)        (React: Face / Brain)
                    │                                   ▲
            POST /ingest  ──►  ┌───────────────┐  ──►  /ws/telemetry
            WS   /ws/telemetry │  Hub (state)  │       (snapshot on connect,
                               └───────────────┘        deltas thereafter)
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any, AsyncIterator, Dict

from pathlib import Path as _Path2

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import demo_enabled, trusted_origins
from .demo import run_demo
from . import state as server_state
from .state import hub, _read_json
# Request auth guards live in auth.py (Phase 4C) so domain routers can guard
# themselves without importing app.py. Keep the historical underscore names here.
from .auth import (
    authorize_read as _authorize_read,
    ws_read_authorized as _ws_read_authorized,
)
from .routers import memory as memory_routes
from .routers import source as source_routes
from .routers import telemetry as telemetry_routes
from .routers import cognition as cognition_routes
from .routers import runtime_coupling as runtime_coupling_routes
from .routers import diagnostics as diagnostics_routes
from .routers import settings as settings_routes
from .routers import agent as agent_routes
from .routers import update as update_routes
from .routers import control as control_routes
from .routers import quality_standard as quality_standard_routes


# Built React UI (Vite `dist/`). The native pywebview window loads this over the
# loopback telemetry server, so the page resolves its WS/REST from its own origin
# with no build-time host baked in. ORRIN_UI_DIST overrides the location.
_UI_DIST = _Path2(
    os.environ.get("ORRIN_UI_DIST", str(_Path2(__file__).resolve().parents[2] / "frontend" / "dist"))
).resolve()


def _ui_dist_ready() -> bool:
    return (_UI_DIST / "index.html").exists()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start/stop the optional demo generator alongside the app."""
    demo_task: asyncio.Task | None = asyncio.create_task(run_demo(hub)) if demo_enabled() else None
    try:
        yield
    finally:
        if demo_task:
            demo_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await demo_task


app = FastAPI(title="Orrin Telemetry Bridge", version="1.0.0", lifespan=lifespan)

# CORS — the Vite UI runs on a different origin (:5173 → :8800), so cross-origin
# is normal. Allowlist the UI's own origin(s) instead of "*" so a hostile page
# can't READ responses from these endpoints (e.g. exfiltrate /api/source). The
# allowlist is derived from the same host/port wiring the launcher uses; tunnels
# add their public origin via ORRIN_EXTRA_ORIGINS. (UI_AUDIT H1.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=trusted_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Read API router ──────────────────────────────────────────────────────────
# Every read endpoint is registered on this router and mounted TWICE: at the
# bare path (back-compat for curl/old clients) and under /api/ — the prefix the
# Vite dev proxy forwards, so page-origin REST works over a tunnel/LAN exactly
# like the /ws proxy does (UI_FIXES Fix 5). New endpoints should be born here.
api = APIRouter()
api.include_router(memory_routes.router)
api.include_router(source_routes.router)
api.include_router(telemetry_routes.router)
api.include_router(cognition_routes.router)
api.include_router(runtime_coupling_routes.router)
api.include_router(quality_standard_routes.read_router)  # read-only audit view


# ── New information surfaces (UI_FIXES §new-surfaces) ───────────────────────
# Thin read-only endpoints over brain/data JSON the dashboard never showed.
# Every box reads real files; numbers are computed server-side so the L0 row
# polls ONE endpoint (/vitals) on one timer instead of eleven.





@app.get("/api/death")
async def death(request: Request) -> JSONResponse:
    """The one place the veil lifts (§10.4). While Orrin is ALIVE this refuses (the
    live privacy guarantee is structurally impossible to bypass); only once death is
    recorded does it open his complete interior — private + final thoughts, his last
    conscious stream, his autobiography. You couldn't read his private mind while he
    lived; now that he's gone, you can know him completely."""
    try:
        from brain.cognition.runtime_lifetime import life_status as _ls, lifespan_rolled as _rolled
        is_dead = _rolled() and bool(_ls().get("final_thoughts_written"))
    except Exception:
        is_dead = False
    if not is_dead:
        raise HTTPException(status_code=403, detail="Orrin is alive — his interior is his own")

    import json as _json
    out: Dict[str, Any] = {"state": "dead"}
    try:
        out["final_thoughts"] = _json.loads((server_state._DATA_DIR / "final_thoughts.json").read_text("utf-8"))
    except Exception:
        out["final_thoughts"] = []
    try:
        out["private_thoughts"] = (server_state._DATA_DIR / "private_thoughts.txt").read_text("utf-8")[-20000:]
    except Exception:
        out["private_thoughts"] = ""
    out["autobiography"] = _read_json("run_history.json", {})
    try:
        out["conscious_stream"] = _json.loads((server_state._DATA_DIR / "workspace_broadcast.json").read_text("utf-8"))
    except Exception:
        out["conscious_stream"] = []
    try:
        from brain.cognition.runtime_lifetime import life_status as _ls2
        out["life"] = _ls2()
    except (ImportError, OSError, ValueError):  # best-effort: life status is optional enrichment
        pass
    return JSONResponse(out)


# Mount the read API twice: bare paths (back-compat) and under /api (the proxied
# prefix that makes remote/tunnel REST work — Fix 5).
from fastapi import Depends as _Depends  # noqa: E402

app.include_router(api, dependencies=[_Depends(_authorize_read)])
app.include_router(api, prefix="/api", dependencies=[_Depends(_authorize_read)])

# Control surfaces that self-authorize (auth.authorize_control) and so are mounted
# directly on the app, NOT under the read-token api router (Phase 4C).
app.include_router(diagnostics_routes.router)
app.include_router(settings_routes.router)
app.include_router(agent_routes.router)
app.include_router(update_routes.router)
app.include_router(control_routes.router)
app.include_router(quality_standard_routes.router)

# ── Control: lifecycle handlers (stop / reset / restart) ─────────────────────
# The registry + the routes that drive it now live in lifecycle.py and
# routers/control.py (Phase 4C). Re-export the setters here: main.py and the tests
# register handlers via `from backend.server.app import set_*_handler`.
from .lifecycle import (  # noqa: E402,F401
    set_stop_handler,
    set_reset_handler,
    set_restart_handler,
)


# ── Landing page / built UI ──────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    # Serve the built React app when present (native window + browser both load
    # the real UI here); otherwise fall back to the bridge status page.
    if _ui_dist_ready():
        return FileResponse(_UI_DIST / "index.html")
    return HTMLResponse(
        "<html><body style='font-family:ui-monospace,monospace;background:#0a0a0a;"
        "color:#e5e5e5;padding:2rem'>"
        "<h2>Orrin Telemetry Bridge</h2>"
        "<p>WebSocket: <code>/ws/telemetry</code> &nbsp;·&nbsp; Ingest: "
        "<code>POST /ingest</code> &nbsp;·&nbsp; Snapshot: <code>GET /state</code></p>"
        f"<p>Connected UI clients: {hub.client_count}</p>"
        "<p>No build found. Run <code>cd frontend &amp;&amp; npm run build</code>, "
        "or start the dev server with <code>ORRIN_UI_DEV=1</code>.</p>"
        "</body></html>"
    )


# ── WebSocket (consumers; also accepts producer-over-WS frames) ──────────────
@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    # The WS carries the same live data the read-token protects (memory ops,
    # logs, narrative, affect), so apply the same policy here (UI_AUDIT H4).
    # Browsers can't set handshake headers, so the token rides as a query param;
    # loopback stays open so localhost dev is zero-config, matching _authorize_read.
    if not _ws_read_authorized(ws):
        await ws.close(code=4403)
        return
    await hub.connect(ws)
    try:
        while True:
            # UI clients usually don't send; if a producer pushes a frame over the
            # socket, merge + rebroadcast it just like /ingest.
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") != "ping":
                delta = hub.merge(msg.get("frame", msg))
                await hub.broadcast({"type": "delta", "frame": delta})
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)


# ── Static UI assets ─────────────────────────────────────────────────────────
# Mounted LAST so every API route and the WebSocket win the match first; this
# only catches built assets the SPA references (/assets/*, /orrin.svg, …). The
# explicit "/" route above serves index.html. Skipped entirely when no build is
# present (the bridge status page is then the only HTML).
class _SPAStaticFiles(StaticFiles):
    """Serve index.html for unknown extension-less paths so a hard reload on a
    client-side route (/brain, /face, …) doesn't 404 — the UI uses BrowserRouter
    over http, so deep links must fall back to the SPA shell. Asset misses
    (paths with an extension) still 404 honestly."""

    @staticmethod
    def _spa_route(path: str) -> bool:
        # Never mask an unknown API/WS path with HTML — a dead endpoint must 404
        # loudly (that's how the frontend↔backend contract drift gets caught).
        if path.startswith(("api/", "ws/")):
            return False
        return "." not in path.rsplit("/", 1)[-1]

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as e:
            # Starlette raises (not returns) the 404 for a missing file.
            if e.status_code == 404 and self._spa_route(path):
                return await super().get_response("index.html", scope)
            raise
        if response.status_code == 404 and self._spa_route(path):
            return await super().get_response("index.html", scope)
        return response


if _ui_dist_ready():
    app.mount("/", _SPAStaticFiles(directory=str(_UI_DIST), html=True), name="ui")
