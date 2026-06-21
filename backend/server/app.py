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
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from pathlib import Path as _Path2

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
from .routers import diagnostics as diagnostics_routes
from .routers import settings as settings_routes
from .routers import agent as agent_routes
from .routers import update as update_routes
from .routers import control as control_routes


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
        from brain.cognition.mortality import life_status as _ls, lifespan_rolled as _rolled
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
    out["autobiography"] = _read_json("autobiography.json", {})
    try:
        out["conscious_stream"] = _json.loads((server_state._DATA_DIR / "conscious_stream.json").read_text("utf-8"))
    except Exception:
        out["conscious_stream"] = []
    try:
        from brain.cognition.mortality import life_status as _ls2
        out["life"] = _ls2()
    except Exception:
        pass
    return JSONResponse(out)


import collections as _collections  # noqa: E402

# Rolling (ts, cycle) samples so Thinking Rate is a real slope, not an instantaneous
# guess — and reads 0 once the cycle counter stops advancing (Stop).
_life_cycle_samples: "Any" = _collections.deque(maxlen=30)


def _thinking_rate_per_min(cycle: int) -> float:
    now = time.time()
    _life_cycle_samples.append((now, int(cycle)))
    pts = [(t, c) for (t, c) in _life_cycle_samples if t >= now - 120]
    if len(pts) >= 2:
        (t0, c0), (t1, c1) = pts[0], pts[-1]
        if t1 > t0:
            return max(0.0, (c1 - c0) / (t1 - t0) * 60.0)
    return 0.0


def _current_interests(limit: int = 6) -> List[str]:
    """Top active goal titles — 'what he cares about right now' (§9.10)."""
    import json as _json
    titles: List[str] = []
    seen: set = set()
    try:
        raw = _json.loads((server_state._DATA_DIR / "goals_mem.json").read_text("utf-8"))

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                title, status = o.get("title"), str(o.get("status") or "")
                if title and title not in seen and status.lower() in ("active", "in_progress", "pursuing", "open"):
                    seen.add(title)
                    titles.append(str(title))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(raw)
    except Exception:
        pass
    return titles[:limit]


@api.get("/life")
async def life() -> JSONResponse:
    """Life Support (§9.10): Orrin's vital signs — his headroom to think, his thinking
    rate, his age, and the life he *believes* he has left. Resources are framed about
    HIM (disk = his mind's room to grow, measured against his data dir). The true
    lifespan is never exposed — only the felt estimate (mortality keeps a private
    noise offset by design)."""
    readings: Dict[str, Any] = {}
    try:
        import psutil as _psutil
        vm = _psutil.virtual_memory()
        du = _psutil.disk_usage(str(server_state._DATA_DIR))
        readings["cpu"] = {
            "available_pct": round(100.0 - _psutil.cpu_percent(interval=None), 1),
            "load_pct": round(_psutil.cpu_percent(interval=None), 1),
        }
        readings["memory"] = {"available_bytes": int(vm.available), "total_bytes": int(vm.total)}
        readings["storage"] = {"free_bytes": int(du.free), "used_bytes": int(du.used), "total_bytes": int(du.total)}
    except Exception as e:
        readings["resources_error"] = str(e)

    # His mind's size against the user's disk ceiling (§10.3) — the framing Life
    # Support uses ("room left to grow his mind"), not the raw host disk.
    try:
        from brain.utils.resource_ceilings import usage as _ceil_usage
        readings["mind_disk"] = _ceil_usage()
    except Exception:
        pass

    # Resident memory against the user's memory ceiling (§10.3) — same framing. ratio 0
    # when psutil/RSS is unavailable, so the UI can show it as unmeasured rather than 0%.
    try:
        from brain.utils.resource_ceilings import memory_usage as _mem_usage
        readings["mind_memory"] = _mem_usage()
    except Exception:
        pass

    readings["thinking_rate_per_min"] = round(_thinking_rate_per_min(hub.state.get("cycle", 0)), 2)
    readings["cycle"] = hub.state.get("cycle", 0)

    try:
        from brain.cognition.mortality import life_status as _life_status
        readings["mortality"] = _life_status()  # felt-only; never the true lifespan
    except Exception as e:
        readings["mortality"] = {"error": str(e)}

    readings["interests"] = _current_interests()
    return JSONResponse(readings)


def _coerce_ts(obj: Dict[str, Any]) -> "Optional[float]":
    """Best-effort unix-seconds timestamp from an event dict (varied schemas)."""
    from datetime import datetime
    for k in ("ts", "timestamp", "created_at", "time", "date", "when"):
        v = obj.get(k)
        if isinstance(v, (int, float)):
            v = float(v)
            return v / 1000.0 if v > 1e12 else v
        if isinstance(v, str) and v:
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
    return None


@api.get("/activity")
async def activity(since: float = 0.0, limit: int = 200) -> JSONResponse:
    """While-you-were-away activity feed (§9.8): a merged, time-ordered view DERIVED
    from existing stores (goals, memories, dreams, belief revisions, egress) — no new
    write path. `since` is unix-seconds (the per-viewer 'last seen', held client-side);
    defaults to the last 24h."""
    import json as _json
    now = time.time()
    if since <= 0:
        since = now - 86400
    events: List[Dict[str, Any]] = []

    def add(kind: str, ts: "Optional[float]", label: str) -> None:
        if ts is None or ts < since:
            return
        events.append({"type": kind, "ts": ts, "label": str(label)[:200]})

    try:
        raw = _json.loads((server_state._DATA_DIR / "goals_mem.json").read_text("utf-8"))
        seen: set = set()

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                if o.get("title") and o.get("status"):
                    gid = str(o.get("id") or o.get("title"))
                    if gid not in seen:
                        seen.add(gid)
                        add("goal", _coerce_ts(o), f"Goal: {o.get('title')}")
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(raw)
    except Exception:
        pass

    for e in _read_json("long_memory.json", [])[-300:]:
        if isinstance(e, dict):
            add("memory", _coerce_ts(e), e.get("content") or e.get("summary") or "Formed a memory")
    for d in _read_json("dream_log.json", [])[-100:]:
        if isinstance(d, dict):
            add("dream", _coerce_ts(d), d.get("summary") or "Consolidated a dream")
    rev = _read_json("self_belief_revisions.json", {})
    if isinstance(rev, dict):
        for dom, lst in rev.items():
            if isinstance(lst, list):
                for r in lst[-20:]:
                    if isinstance(r, dict):
                        add("belief", _coerce_ts(r), f"Revised a belief about {dom}")
    try:
        from brain.utils.egress import events as _eg_events
        for r in _eg_events(since):
            svc = r.get("service")
            if svc == "serper":
                add("web", r.get("ts"), "Searched the web")
            elif svc == "web":
                add("web", r.get("ts"), "Visited a site")
            elif svc == "finetune":
                add("finetune", r.get("ts"), "Uploaded traces to fine-tune")
    except Exception:
        pass

    events.sort(key=lambda e: e["ts"], reverse=True)
    # Summary tallies the FULL window ("while you were away"), so count before
    # truncating the events list to `limit` — otherwise long absences undercount.
    summary: Dict[str, int] = {}
    for e in events:
        summary[e["type"]] = summary.get(e["type"], 0) + 1
    events = events[: max(1, min(500, int(limit)))]
    return JSONResponse({"events": events, "summary": summary, "since": since, "now": now})


@api.get("/affect")
async def affect() -> JSONResponse:
    """Ground-truth affect vector straight from affect_state.json (representation
    B), so panels can cross-check the transformed telemetry stream (C). Exposes
    the raw -1..1 valence, the full core_signals vector, and the brain's own
    homeostasis index — none of which the WS stream carries unmodified.
    SPLIT_CONSCIOUSNESS_TELEMETRY_AUDIT §7 rec #3."""
    a = _read_json("affect_state.json", {})
    if not isinstance(a, dict):
        a = {}
    core = a.get("core_signals") if isinstance(a.get("core_signals"), dict) else {}
    return JSONResponse({
        "valence": a.get("valence"),                 # raw -1..1 (no UI centering)
        "activation_level": a.get("activation_level"),
        "homeostasis": a.get("homeostasis"),         # the brain's own index
        "resource_deficit": a.get("resource_deficit"),
        "allostatic_load": a.get("allostatic_load"),
        "affect_stability": a.get("affect_stability"),
        "affect_quadrant": a.get("affect_quadrant"),
        "core_signals": core,                        # the full vector, raw
        "last_updated": a.get("last_updated"),
    })


@api.get("/vitals")
async def vitals() -> JSONResponse:
    """The L0 vital-signs aggregator: every chip computed server-side from one or
    two fields of one file each, so the row polls ONE url on ONE timer — and
    external monitors get a single 'how is Orrin?' answer."""
    chips: List[Dict[str, Any]] = []

    def chip(key: str, label: str, value: str, status: str, detail: str = "") -> None:
        chips.append({"key": key, "label": label, "value": value, "status": status, "detail": detail})

    # Health (health_state.json)
    h = _read_json("health_state.json", {})
    hs = str(h.get("status") or "unknown")
    chip("health", "Health", hs,
         "ok" if hs in ("healthy", "nominal", "ok") else "err" if hs in ("sick", "critical") else "warn",
         f"streak {h.get('streak', 0)} · sick {h.get('sick_streak', 0)}")

    # Benchmarks (benchmark_results.json)
    res = _read_json("benchmark_results.json", {})
    bms = {k: v for k, v in res.items() if k.startswith("B") and isinstance(v, dict)}
    if bms:
        passed = sum(1 for v in bms.values() if v.get("status") == "pass")
        ran = sum(1 for v in bms.values() if v.get("status") in ("pass", "fail"))
        chip("benchmarks", "Bench", f"{passed}/{len(bms)}",
             "ok" if passed == len(bms) else "warn" if passed >= ran and ran else "err",
             ", ".join(f"{k}:{v.get('status')}" for k, v in sorted(bms.items())))

    # Goals (outcome_metrics.json)
    om = _read_json("outcome_metrics.json", [])
    if om:
        o = om[-1]
        cr = float(o.get("completion_rate") or 0)
        ar = float(o.get("abandonment_rate") or 0)
        chip("goals", "Goals", f"{o.get('active_goals', '?')} active",
             "ok" if cr >= 0.5 and ar <= 0.3 else "warn",
             f"completion {round(cr * 100)}% · abandon {round(ar * 100)}%")

    # Symbolic (symbolic_progress.json) — suppress the meaningless 100% on LLM-off runs.
    sp = _read_json("symbolic_progress.json", [])
    if sp:
        s = sp[-1]
        if not s.get("llm_calls"):
            chip("symbolic", "Symbolic", "LLM off", "off",
                 f"{s.get('symbolic_hits', 0)} symbolic answers · ratio meaningless with 0 LLM calls")
        else:
            ratio = float(s.get("symbolic_ratio") or 0)
            chip("symbolic", "Symbolic", f"{round(ratio * 100)}%",
                 "ok" if ratio >= 0.5 else "warn", f"{s.get('rules_total', 0)} rules")

    # Surprise / calibration (calibration_state.json)
    cal = _read_json("calibration_state.json", {})
    if cal.get("n"):
        brier = float(cal.get("brier") or 0)
        chip("predictions", "Surprise", "low" if brier < 0.1 else "med" if brier < 0.25 else "high",
             "ok" if brier < 0.1 else "warn" if brier < 0.25 else "err",
             f"Brier {round(brier, 4)} over n={cal.get('n')}")

    # Energy (energy_mode.json)
    em = _read_json("energy_mode.json", {})
    if em:
        mode = str(em.get("mode") or "?")
        chip("drives", "Energy", mode, "ok" if mode in ("active", "rest") else "warn",
             f"level {em.get('level')}")

    # Learning trend (reward_trace.json + decision_stats.json)
    ds = _read_json("decision_stats.json", {})
    if ds:
        rs = [float(v.get("avg_reward") or 0) for v in ds.values() if isinstance(v, dict)]
        if rs:
            avg = sum(rs) / len(rs)
            chip("learning", "Learning", f"r̄ {round(avg, 2)}",
                 "ok" if avg >= 0.45 else "warn", f"{len(rs)} functions tracked")

    # Tensions (tensions.json + rumination_loops.json)
    tn = [t for t in _read_json("tensions.json", []) if isinstance(t, dict)]
    active_t = [t for t in tn if str(t.get("status") or "active") not in ("resolved", "closed")]
    if tn or active_t:
        worst = max((int(t.get("cycles_active") or 0) for t in active_t), default=0)
        chip("tensions", "Tensions", str(len(active_t)),
             "ok" if not active_t else "warn" if worst < 200 else "err",
             f"longest {worst} cycles active" if active_t else "none active")

    # Inner weather (temporal_state.json)
    ts = _read_json("temporal_state.json", {})
    if ts:
        chip("innerweather", "Felt time", str(ts.get("session_arc") or "—"), "ok",
             f"feels {ts.get('felt_duration_label', '?')} · {str(ts.get('time_texture', '')).replace('_', ' ')}")

    # Data integrity (L6): a file that exists but fails to parse reads as "empty"
    # everywhere else — surface it loudly here so corruption is visible, not silent.
    if server_state._DATA_PARSE_ERRORS:
        n = len(server_state._DATA_PARSE_ERRORS)
        chip("data", "Data", f"{n} corrupt", "err",
             "unreadable: " + ", ".join(sorted(server_state._DATA_PARSE_ERRORS)[:6]))

    return JSONResponse({"chips": chips, "ts": time.time()})


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
if _ui_dist_ready():
    app.mount("/", StaticFiles(directory=str(_UI_DIST), html=True), name="ui")
