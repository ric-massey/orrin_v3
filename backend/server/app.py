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
import hmac
import os
import signal
import threading
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Optional

from pathlib import Path as _Path2

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import RESPONSE_CAP, demo_enabled, trusted_origins
from .demo import run_demo
from .hub import Hub

hub = Hub()

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


# ── Health / debug ───────────────────────────────────────────────────────────
@api.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"ok": True, "clients": hub.client_count, "cycle": hub.state.get("cycle")}


@api.get("/state")
async def state() -> JSONResponse:
    """Full current snapshot (handy for debugging / curl)."""
    return JSONResponse(hub.state)


# ── Cognitive Map: function catalog + source ─────────────────────────────────
from pathlib import Path as _Path  # noqa: E402

_REPO_ROOT = _Path(__file__).resolve().parents[2]
# _REPO_ROOT stays PROGRAM-relative (the /source repo-jail below must point at the
# shipped code, never the user's data). But the DATA root must honor ORRIN_DATA_DIR
# or the brain writes to the relocated dir while these read endpoints keep reading
# the stale brain/data — the UI then shows an empty/old mind (§13.2 split-brain).
# Consume the one resolver the brain uses; fall back to the same env logic if it
# can't be imported (e.g. brain/ not on sys.path).
try:
    from brain.paths import DATA_DIR as _DATA_DIR  # noqa: E402
except Exception:  # pragma: no cover - defensive
    _env_data = os.environ.get("ORRIN_DATA_DIR")
    _DATA_DIR = _Path(_env_data).resolve() if _env_data else _REPO_ROOT / "brain" / "data"

# /source serves the metric-info pages their cited source — only ever real
# source/text files. Restrict to these suffixes and forbid dotfiles so the
# repo-jail can't be used to read .env, .git/*, lockfiles, etc. (UI_AUDIT H1.)
_SOURCE_OK_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".css", ".txt", ".yml", ".yaml"}


@api.get("/catalog")
async def catalog() -> JSONResponse:
    """The map of Orrin's mind: functions → subsystem/file/line/summary, merged
    with live per-function decision stats (count / avg_reward)."""
    cat = hub.state.get("catalog") or {"functions": {}, "subsystems": {}}
    stats: Dict[str, Any] = {}
    try:
        import json as _json
        stats = _json.loads((_DATA_DIR / "decision_stats.json").read_text("utf-8"))
    except Exception:
        stats = {}
    fns = {}
    for name, info in (cat.get("functions") or {}).items():
        st = stats.get(name) or {}
        fns[name] = {
            **info,
            "count": int(st.get("count", 0) or 0),
            "avg_reward": round(float(st.get("avg_reward", 0.0) or 0.0), 3),
        }
    # Real learned transition edges (basal-ganglia function chains): the truthful
    # wiring of how his cognition actually moves from one function to the next.
    edges = []
    try:
        import json as _json
        chains = _json.loads((_DATA_DIR / "function_chains.json").read_text("utf-8"))
        for src, succ in (chains or {}).items():
            if src not in fns or not isinstance(succ, dict):
                continue
            for dst, meta in succ.items():
                if dst not in fns:
                    continue
                w = float(meta.get("bonus", 0.0)) if isinstance(meta, dict) else float(meta or 0.0)
                edges.append({"from": src, "to": dst, "weight": round(w, 3)})
    except Exception:
        edges = []
    return JSONResponse({"functions": fns, "subsystems": cat.get("subsystems") or {}, "edges": edges})


@api.get("/history")
async def history(n: int = 80) -> JSONResponse:
    """His recent activation history — what fired, when, the reward it earned, and
    whether it was an agentic action. Read from the cognition history log."""
    try:
        import json as _json
        h = _json.loads((_DATA_DIR / "cognition_history.json").read_text("utf-8"))
        if not isinstance(h, list):
            h = []
        out = []
        for e in h[-max(1, min(300, n)):]:
            if not isinstance(e, dict):
                continue
            try:
                rew = float(e.get("reward")) if e.get("reward") is not None else None
            except Exception:
                rew = None
            ag = e.get("is_agentic")
            out.append({
                "fn": e.get("choice"),
                "reward": rew,
                "agentic": str(ag).lower() in ("true", "1") if ag is not None else None,
                "ts": e.get("timestamp"),
                "lane": e.get("lane"),
            })
        return JSONResponse({"events": out})
    except Exception as e:
        return JSONResponse({"events": [], "error": str(e)})


@api.get("/goals")
async def goals_detail() -> JSONResponse:
    """Full detail of each goal — its meaning (spec), why it exists (serves), how it
    knows it's accomplished (milestones), the work (plan steps) and what happened
    (history) — for the clickable goal panel."""
    try:
        import json as _json
        raw = _json.loads((_DATA_DIR / "goals_mem.json").read_text("utf-8"))
        out: list = []
        seen: set = set()

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                if o.get("title") and o.get("status"):
                    gid = str(o.get("id") or o.get("title"))
                    if gid not in seen:
                        seen.add(gid)
                        spec = o.get("spec") if isinstance(o.get("spec"), dict) else {}
                        out.append({
                            "id": o.get("id"),
                            "title": o.get("title"),
                            "status": o.get("status"),
                            "tier": o.get("tier"),
                            "priority": o.get("priority"),
                            "kind": o.get("kind"),
                            "tags": o.get("tags") or [],
                            "serves": o.get("serves"),
                            "description": (spec or {}).get("description"),
                            "driven_by": (spec or {}).get("driven_by") or (spec or {}).get("driven"),
                            "milestones": o.get("milestones") or [],
                            "plan": o.get("plan") or [],
                            "history": o.get("history") or [],
                            "completed_timestamp": o.get("completed_timestamp"),
                            "created_at": o.get("created_at") or o.get("created_timestamp"),
                            "last_updated": o.get("last_updated"),
                            "raw": o,  # full record so the UI can show the bottom of the data
                        })
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(raw)
        return JSONResponse({"goals": out})
    except Exception as e:
        return JSONResponse({"goals": [], "error": str(e)})


@api.get("/goal_artifacts")
async def goal_artifacts(id: str = "") -> JSONResponse:
    """What he ACTUALLY produced for a goal: long-memory entries written during the
    goal's execution window and/or about its topic — each with its provenance
    (event_type = where it came from, timestamp). Lets the UI show exactly what he
    did, not just the templated plan."""
    import json as _json
    import re as _re
    from datetime import datetime as _dt

    def _epoch(v: Any):
        if v is None:
            return None
        try:
            if isinstance(v, (int, float)):
                return float(v)
            return _dt.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    try:
        goals_raw = _json.loads((_DATA_DIR / "goals_mem.json").read_text("utf-8"))
        target: Dict[str, Any] = {}

        def find(o: Any) -> None:
            nonlocal target
            if isinstance(o, dict):
                if o.get("title") and str(o.get("id") or o.get("title")) == id:
                    target = o
                for v in o.values():
                    find(v)
            elif isinstance(o, list):
                for v in o:
                    find(v)

        find(goals_raw)
        if not target:
            return JSONResponse({"artifacts": [], "error": "goal not found"})

        starts = [_epoch(s.get("generated_at")) for s in (target.get("plan") or []) if isinstance(s, dict)]
        starts = [x for x in starts if x] + [x for x in [_epoch(target.get("created_at")), _epoch(target.get("created_timestamp"))] if x]
        win_lo = min(starts) if starts else None
        win_hi = _epoch(target.get("completed_timestamp")) or _epoch(target.get("last_updated"))

        title = str(target.get("title", "")).lower()
        for junk in ("understand", "more deeply", "find out:", "learn about", "leave a note", "stability:"):
            title = title.replace(junk, "")
        kws = [w for w in _re.findall(r"[a-z]{4,}", title) if w not in ("about", "with", "from", "what", "that", "this")]

        lm = _json.loads((_DATA_DIR / "long_memory.json").read_text("utf-8"))
        arts = []
        for e in lm:
            if not isinstance(e, dict):
                continue
            ts = _epoch(e.get("timestamp"))
            content = str(e.get("content") or "")
            in_window = bool(win_lo and win_hi and ts and win_lo - 30 <= ts <= win_hi + 30)
            on_topic = bool(kws) and any(k in content.lower() for k in kws)
            if in_window or on_topic:
                arts.append({
                    "id": e.get("id"),
                    "ts": e.get("timestamp"),
                    "event_type": e.get("event_type"),
                    "content": content[:1500],
                    "importance": e.get("importance"),
                    "on_topic": on_topic,
                    "in_window": in_window,
                })
        arts.sort(key=lambda a: str(a.get("ts") or ""), reverse=True)
        return JSONResponse({"artifacts": arts[:30], "topic_keywords": kws,
                             "window": {"from": win_lo, "to": win_hi}})
    except Exception as e:
        return JSONResponse({"artifacts": [], "error": str(e)})


@api.get("/source")
async def source(file: str = "", start: int = 1, end: int = 0) -> JSONResponse:
    """Return a read-only slice of a repo source file (for the metric info pages)."""
    try:
        target = (_REPO_ROOT / file).resolve()
        rel = target.relative_to(_REPO_ROOT)  # repo-jail
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
        return JSONResponse({"error": str(e), "file": file}, status_code=400)


@api.get("/code")
async def code(fn: str = "") -> JSONResponse:
    """Return the real source of a cognitive function (read-only)."""
    cat = hub.state.get("catalog") or {}
    info = (cat.get("functions") or {}).get(fn)
    if not info:
        return JSONResponse({"error": "unknown function", "fn": fn}, status_code=404)
    rel = str(info.get("file") or "")
    try:
        target = (_REPO_ROOT / rel).resolve()
        # Safety: only serve files inside the repo.
        target.relative_to(_REPO_ROOT)
        lines = target.read_text("utf-8", errors="replace").splitlines()
        lo = max(1, int(info.get("lineno", 1)))
        hi = min(len(lines), int(info.get("endline", lo)))
        src = "\n".join(lines[lo - 1 : hi])
        if len(src) > 60_000:
            src = src[:60_000] + "\n… (truncated)"
        return JSONResponse({"fn": fn, "file": rel, "lineno": lo, "endline": hi, "source": src})
    except Exception as e:
        return JSONResponse({"error": str(e), "fn": fn}, status_code=500)


# ── Consciousness stream: the actual stream the panel is named for (Fix 4) ───
@api.get("/consciousness")
async def consciousness(n: int = 60) -> JSONResponse:
    """Tail of the persisted conscious stream — the rolling list of conscious
    moments {content, source, salience, ts} written by global_workspace."""
    try:
        import json as _json
        data = _json.loads((_DATA_DIR / "conscious_stream.json").read_text("utf-8"))
        if not isinstance(data, list):
            data = []
        out = [m for m in data[-max(1, min(200, n)):] if isinstance(m, dict)]
        return JSONResponse({"moments": out, "total": len(data)})
    except Exception as e:
        return JSONResponse({"moments": [], "total": 0, "error": str(e)})


# ── Memory store browsing: the store, not the stream (Fix 8) ─────────────────
_MEMORY_STORES = {
    "long": "long_memory.json",
    "working": "working_memory.json",
    "knowledge": "knowledge_graph.json",
    "semantic": "semantic_facts.json",
}


@api.get("/memory")
async def memory_store(store: str = "long", q: str = "", n: int = 50, offset: int = 0,
                      order: str = "recency") -> JSONResponse:
    """Paged browse of a REAL memory store file — what he actually remembers, as
    opposed to the live op ring the WS streams. `order=recency` (default, newest
    first) or `order=importance` (by importance/salience) powers the Memory
    Explorer's Recent vs Important lenses (§9.5)."""
    import json as _json
    fname = _MEMORY_STORES.get((store or "").lower())
    if not fname:
        return JSONResponse({"entries": [], "total": 0,
                             "error": f"unknown store; one of {sorted(_MEMORY_STORES)}"}, status_code=400)
    try:
        raw = _json.loads((_DATA_DIR / fname).read_text("utf-8"))
        # knowledge_graph.json is {entities, relations, meta} — browse the entities.
        if isinstance(raw, dict):
            ents = raw.get("entities")
            if isinstance(ents, dict):
                raw = [{"id": k, **v} if isinstance(v, dict) else {"id": k, "content": str(v)}
                       for k, v in ents.items()]
            elif isinstance(ents, list):
                raw = ents
            else:
                raw = []
        if not isinstance(raw, list):
            raw = []
        total = len(raw)
        entries = [e for e in raw if isinstance(e, dict)]
        needle = (q or "").strip().lower()
        if needle:
            entries = [e for e in entries if needle in _json.dumps(e, ensure_ascii=False).lower()]
        matched = len(entries)
        if (order or "").lower() == "importance":
            def _imp(e: Dict[str, Any]) -> float:
                for k in ("importance", "salience", "weight", "score"):
                    v = e.get(k)
                    if isinstance(v, (int, float)):
                        return float(v)
                return 0.0
            entries = sorted(entries, key=_imp, reverse=True)
        else:
            entries = list(reversed(entries))  # recency: newest-first (stores append)
        lo = max(0, int(offset))
        hi = lo + max(1, min(200, int(n)))
        page = []
        for e in entries[lo:hi]:
            slim = dict(e)
            c = slim.get("content")
            if isinstance(c, str) and len(c) > 2000:
                slim["content"] = c[:2000] + "…"
            page.append(slim)
        return JSONResponse({"entries": page, "total": total, "matched": matched,
                             "store": store, "offset": lo})
    except FileNotFoundError:
        return JSONResponse({"entries": [], "total": 0, "matched": 0, "store": store, "offset": 0})
    except Exception as e:
        return JSONResponse({"entries": [], "total": 0, "error": str(e)})


@api.get("/memory_counts")
async def memory_counts() -> JSONResponse:
    """True store sizes for the Inspector's chips (live-op counts are NOT sizes)."""
    import json as _json
    out: Dict[str, int] = {}
    for key, fname in _MEMORY_STORES.items():
        try:
            raw = _json.loads((_DATA_DIR / fname).read_text("utf-8"))
            if isinstance(raw, dict):
                ents = raw.get("entities")
                out[key] = len(ents) if isinstance(ents, (list, dict)) else 0
            else:
                out[key] = len(raw) if isinstance(raw, list) else 0
        except Exception:
            out[key] = 0
    return JSONResponse({"counts": out})


# ── Chat history: the canonical conversation log (Fix 10.4) ──────────────────
@api.get("/chat")
async def chat_history(n: int = 100) -> JSONResponse:
    """Tail of brain/data/chat_log.json so a new browser/device can show the real
    shared conversation history instead of an empty localStorage one."""
    try:
        import json as _json
        data = _json.loads((_DATA_DIR / "chat_log.json").read_text("utf-8"))
        if not isinstance(data, list):
            data = []
        out = [m for m in data[-max(1, min(500, n)):] if isinstance(m, dict)]
        return JSONResponse({"messages": out, "total": len(data)})
    except Exception as e:
        return JSONResponse({"messages": [], "total": 0, "error": str(e)})


# ── New information surfaces (UI_FIXES §new-surfaces) ───────────────────────
# Thin read-only endpoints over brain/data JSON the dashboard never showed.
# Every box reads real files; numbers are computed server-side so the L0 row
# polls ONE endpoint (/vitals) on one timer instead of eleven.

# Files that exist but fail to JSON-parse (corruption) are tracked here so the
# UI can distinguish "data file unreadable" from "nothing yet" instead of both
# rendering as an empty panel (UI_AUDIT L6). Surfaced as a /vitals "Data" chip.
_DATA_PARSE_ERRORS: Dict[str, str] = {}


def _read_json(fname: str, default: Any) -> Any:
    import json as _json
    try:
        text = (_DATA_DIR / fname).read_text("utf-8")
    except FileNotFoundError:
        _DATA_PARSE_ERRORS.pop(fname, None)  # missing ≠ corrupt
        return default
    except Exception:
        return default
    try:
        d = _json.loads(text)
        _DATA_PARSE_ERRORS.pop(fname, None)  # parsed OK — clear any prior error
        return d if isinstance(d, type(default)) else default
    except Exception as e:
        _DATA_PARSE_ERRORS[fname] = str(e)[:160]
        return default


def _read_jsonl_tail(fname: str, n: int) -> list:
    import json as _json
    try:
        lines = (_DATA_DIR / fname).read_text("utf-8").splitlines()
        out = []
        for ln in lines[-max(1, n):]:
            try:
                out.append(_json.loads(ln))
            except Exception:
                continue
        return out
    except Exception:
        return []


@api.get("/benchmarks")
async def benchmarks(samples: int = 0) -> JSONResponse:
    """B1–B5 from benchmark_results.json — the headline 'is he actually working'
    answer, previously visible only by reading the file. Renders fail/not_run
    states first-class. ?samples=N also tails benchmark_samples.jsonl (L3/L4)."""
    res = _read_json("benchmark_results.json", {})
    out: Dict[str, Any] = {"evaluated_at": res.get("evaluated_at"),
                           "sample_count": res.get("sample_count"),
                           "benchmarks": {k: v for k, v in res.items()
                                          if k.startswith("B") and isinstance(v, dict)}}
    if samples:
        out["samples"] = _read_jsonl_tail("benchmark_samples.jsonl", min(200, samples))
    return JSONResponse(out)


@api.get("/outcomes")
async def outcomes() -> JSONResponse:
    """Daily goal-closure metrics (outcome_metrics.json) — the closure-remediation
    story: does the goal population stay bounded, and HOW do goals close."""
    hist = _read_json("outcome_metrics.json", [])
    return JSONResponse({"history": hist[-90:], "latest": (hist[-1] if hist else None)})


@api.get("/innerweather")
async def innerweather() -> JSONResponse:
    """Felt time + mood + mortality (temporal_state / mood_state / lifespan) —
    the strongest personhood data in brain/data, fully hidden until now."""
    t = dict(_read_json("temporal_state.json", {}))
    t.pop("density_buffer", None)  # internal ring, large and meaningless to render
    return JSONResponse({
        "temporal": t,
        "mood": _read_json("mood_state.json", {}),
        "lifespan": _read_json("lifespan.json", {}),
    })


@api.get("/symbolic")
async def symbolic(n: int = 12, q: str = "") -> JSONResponse:
    """The symbolic mind: no-LLM reasoning ratio, learned rules, causal edges,
    per-domain rule coverage. Honesty caveat handled CLIENT-side too, but flagged
    here: when llm_calls == 0 the ratio is trivially 1.0 (LLM-off run)."""
    import json as _json
    prog = _read_json("symbolic_progress.json", [])
    latest = prog[-1] if prog else {}
    rules = [r for r in _read_json("symbolic_rules.json", []) if isinstance(r, dict)]
    needle = (q or "").strip().lower()
    if needle:
        rules = [r for r in rules if needle in _json.dumps(r, ensure_ascii=False).lower()]
    rules_sorted = sorted(rules, key=lambda r: (r.get("hits") or 0, r.get("confidence") or 0), reverse=True)
    edges = [e for e in _read_json("causal_graph.json", []) if isinstance(e, dict)]
    edges_sorted = sorted(edges, key=lambda e: e.get("causal_score") or e.get("strength") or 0, reverse=True)
    cap = max(1, min(60, n))
    return JSONResponse({
        "progress": latest,
        "history": prog[-30:],
        "llm_off": bool(latest) and not latest.get("llm_calls"),
        "rules_total": len(_read_json("symbolic_rules.json", [])),
        "rules": rules_sorted[:cap],
        "causal_total": len(edges),
        "causal": edges_sorted[:cap],
        "domains": _read_json("world_model_stats.json", {}),
    })


@api.get("/predictions")
async def predictions(n: int = 30) -> JSONResponse:
    """Active-inference surface: recent predictions vs outcomes, per-domain
    accuracy, and the Brier score (calibration_state) — a single defensible
    'how well-calibrated is he' number nothing displayed."""
    preds = [p for p in _read_json("predictions.json", []) if isinstance(p, dict)]
    return JSONResponse({
        "calibration": _read_json("calibration_state.json", {}),
        "domains": _read_json("prediction_domain_stats.json", {}),
        # Phase 1.3: felt-vs-behaved agreement per domain — how much his
        # introspection has earned the right to be believed.
        "introspection_trust": _read_json("introspection_trust.json", {}),
        "recent": preds[-max(1, min(100, n)):],
        "total": len(preds),
    })


@api.get("/drives")
async def drives() -> JSONResponse:
    """Drives & body: motivation drives, energy mode, body sense, and the live
    interoceptive cost model (expected vs last cost per function = 'strain')."""
    io = _read_json("interoceptive_model.json", {})
    io_rows = sorted(
        ({"fn": k, **v} for k, v in io.items() if isinstance(v, dict)),
        key=lambda r: r.get("ema") or 0, reverse=True,
    )
    return JSONResponse({
        "drives": (_read_json("motivation_state.json", {}) or {}).get("drives") or {},
        "energy": _read_json("energy_mode.json", {}),
        "body": _read_json("body_sense.json", {}),
        "interoception": io_rows[:20],
    })


@api.get("/learning")
async def learning(n: int = 15) -> JSONResponse:
    """How he learns which thoughts pay off: per-function decision stats (count /
    avg_reward), bandit suppressions, and the recent reward trace."""
    ds = _read_json("decision_stats.json", {})
    rows = sorted(
        ({"fn": k, "count": int(v.get("count") or 0), "avg_reward": round(float(v.get("avg_reward") or 0), 3)}
         for k, v in ds.items() if isinstance(v, dict)),
        key=lambda r: r["count"], reverse=True,
    )
    bandit = _read_json("bandit_state.json", {})
    return JSONResponse({
        "functions": rows[:max(1, min(50, n))],
        "suppressed": bandit.get("suppressed") or {},
        "reward_trace": _read_json("reward_trace.json", [])[-40:],
    })


@api.get("/tensions")
async def tensions(n: int = 20) -> JSONResponse:
    """What he's wrestling with: active tensions, rumination loops, and the
    second-order volition timeline (what he wants to WANT — stance · desire ·
    statement, dated)."""
    return JSONResponse({
        "tensions": _read_json("tensions.json", [])[-max(1, min(50, n)):],
        "rumination": _read_json("rumination_loops.json", [])[-max(1, min(50, n)):],
        "volition": _read_json("second_order_volition.json", [])[-max(1, min(50, n)):],
    })


@api.get("/health")
async def health_box(n: int = 10) -> JSONResponse:
    """The ops view: health_state + per-site failure counts (failures.jsonl, the
    record_failure ledger) + recent incidents — 'what is quietly broken' without
    tailing four log files."""
    fails = _read_jsonl_tail("failures.jsonl", 2000)
    by_site: Dict[str, Dict[str, Any]] = {}
    for f in fails:
        site = str(f.get("site") or "?")
        rec = by_site.setdefault(site, {"site": site, "count": 0, "last_error": "", "last_ts": ""})
        rec["count"] += 1
        rec["last_error"] = str(f.get("error") or "")[:200]
        rec["last_ts"] = str(f.get("ts") or "")
    top_failing = sorted(by_site.values(), key=lambda r: r["count"], reverse=True)
    return JSONResponse({
        "health": _read_json("health_state.json", {}),
        "failing_sites": top_failing[:max(1, min(50, n))],
        "failure_lines": len(fails),
        "incidents": [
            {k: (str(v)[:300] if k == "trace" else v) for k, v in i.items()}
            for i in _read_jsonl_tail("incidents.jsonl", max(1, min(30, n))) if isinstance(i, dict)
        ],
    })


@api.get("/self")
async def self_box(n: int = 20) -> JSONResponse:
    """Who he is and how it revises (box ⑦): the self-model's identity / values /
    traits / knowledge domains, the dated belief-confidence revisions, formed
    opinions, and the autobiography. private_thoughts / final_thoughts stay
    excluded by design (see ui_fixes.md §Deliberate exclusions)."""
    sm = dict(_read_json("self_model.json", {}))
    sm.pop("latent_identity_vector", None)  # internal embedding, meaningless to render
    revisions: List[Dict[str, Any]] = []
    for dom, rec in (_read_json("self_belief_revisions.json", {}) or {}).items():
        if not isinstance(rec, dict):
            continue
        for ev in rec.get("events") or []:
            if isinstance(ev, dict):
                revisions.append({"domain": dom, "confidence": rec.get("confidence"), **ev})
    revisions.sort(key=lambda r: str(r.get("timestamp") or ""))
    cap = max(1, min(100, n))
    opinions = [o for o in _read_json("opinions.json", []) if isinstance(o, dict)]
    return JSONResponse({
        "model": sm,
        "revisions": revisions[-cap:],
        "opinions": opinions[-cap:],
        "autobiography": _read_json("autobiography.json", {}),
    })


@api.get("/people")
async def people() -> JSONResponse:
    """Who he knows (box ⑧): person models from relationships.json + the known-
    persons registry. His internal peer observers live in the same file — they
    are returned as a DISTINCT `peers` group, never mixed in with people."""
    persons: List[Dict[str, Any]] = []
    peers: List[Dict[str, Any]] = []
    for name, rec in (_read_json("relationships.json", {}) or {}).items():
        if not isinstance(rec, dict):
            continue
        row = {"name": name, **{k: v for k, v in rec.items() if k != "interaction_history"}}
        hist = rec.get("interaction_history")
        row["interactions"] = len(hist) if isinstance(hist, list) else 0
        (peers if rec.get("type") == "peer" else persons).append(row)
    known = [{"id": pid, **rec}
             for pid, rec in (_read_json("known_persons.json", {}) or {}).items()
             if isinstance(rec, dict)]
    return JSONResponse({"people": persons, "peers": peers, "known": known})


@api.get("/dreams")
async def dreams(n: int = 12) -> JSONResponse:
    """What he consolidates while idle: dream_log sweeps + symbolic dream
    insights. Honesty note: consolidation/recombination are often EMPTY strings
    on a fresh run — the client must render 'slept, nothing consolidated'
    rather than blank cards."""
    cap = max(1, min(50, n))
    dl = [d for d in _read_json("dream_log.json", []) if isinstance(d, dict)]
    sd = [d for d in _read_json("symbolic_dream_log.json", []) if isinstance(d, dict)]
    return JSONResponse({"dreams": dl[-cap:], "symbolic": sd[-cap:], "total": len(dl)})


@api.get("/language")
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
            return (_DATA_DIR / "language" / fname).stat().st_size
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


@api.get("/verdicts")
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


@api.get("/forgetting")
async def forgetting(n: int = 30) -> JSONResponse:
    """The forgetting ledger (decayed/pruned/retired per sweep) — memory staying
    bounded is only believable when you can watch him forget (pairs with B1)."""
    log = [f for f in _read_json("forgetting_log.json", []) if isinstance(f, dict)]
    return JSONResponse({"sweeps": log[-max(1, min(100, n)):], "total": len(log)})


@api.get("/lifecycle")
async def lifecycle() -> JSONResponse:
    """Tell death / interrupted (crash-or-stall) / alive apart (§10.5), so the UI can
    route to the Death Screen, a 'restarting' note, or normal viewing on launch."""
    try:
        from brain.utils.lifecycle import status as _status
        return JSONResponse(_status())
    except Exception as e:
        return JSONResponse({"state": "alive", "error": str(e)})


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
        out["final_thoughts"] = _json.loads((_DATA_DIR / "final_thoughts.json").read_text("utf-8"))
    except Exception:
        out["final_thoughts"] = []
    try:
        out["private_thoughts"] = (_DATA_DIR / "private_thoughts.txt").read_text("utf-8")[-20000:]
    except Exception:
        out["private_thoughts"] = ""
    out["autobiography"] = _read_json("autobiography.json", {})
    try:
        out["conscious_stream"] = _json.loads((_DATA_DIR / "conscious_stream.json").read_text("utf-8"))
    except Exception:
        out["conscious_stream"] = []
    try:
        from brain.cognition.mortality import life_status as _ls2
        out["life"] = _ls2()
    except Exception:
        pass
    return JSONResponse(out)


@api.get("/boot")
async def boot() -> JSONResponse:
    """The boot sequence (§9.7): ordered, truthful startup milestones + a `ready` flag.
    The wake-up screen polls this and dissolves into Cognition once ready. A warm
    reopen (brain already up) returns ready immediately."""
    try:
        from brain.utils.boot_events import snapshot as _boot_snapshot
        return JSONResponse(_boot_snapshot())
    except Exception as e:
        return JSONResponse({"events": [], "ready": True, "error": str(e)})


@api.get("/egress")
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
        raw = _json.loads((_DATA_DIR / "goals_mem.json").read_text("utf-8"))

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
        du = _psutil.disk_usage(str(_DATA_DIR))
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
        raw = _json.loads((_DATA_DIR / "goals_mem.json").read_text("utf-8"))
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
    events = events[: max(1, min(500, int(limit)))]
    summary: Dict[str, int] = {}
    for e in events:
        summary[e["type"]] = summary.get(e["type"], 0) + 1
    return JSONResponse({"events": events, "summary": summary, "since": since, "now": now})


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
    if _DATA_PARSE_ERRORS:
        n = len(_DATA_PARSE_ERRORS)
        chip("data", "Data", f"{n} corrupt", "err",
             "unreadable: " + ", ".join(sorted(_DATA_PARSE_ERRORS)[:6]))

    return JSONResponse({"chips": chips, "ts": time.time()})


# ── Optional read-token guard (UI_FIXES new-surfaces security note) ──────────
# Every read endpoint is unauthenticated by default (localhost dev). The new
# surfaces raise the stakes (/memory, /chat, /consciousness are his memory,
# conversations, and stream of awareness) — so when ORRIN_READ_TOKEN is set,
# all reads require the X-Orrin-Read-Token header; loopback stays open so
# localhost dev is zero-config, exactly like _authorize_control. When unset,
# behavior is unchanged — the tunnel URL is then the only secret.
_READ_TOKEN = os.environ.get("ORRIN_READ_TOKEN", "").strip()


def _authorize_read(request: Request) -> None:
    if not _READ_TOKEN:
        return
    client_host = (request.client.host if request.client else "") or ""
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return
    supplied = (request.headers.get("X-Orrin-Read-Token") or "").strip()
    if not hmac.compare_digest(supplied, _READ_TOKEN):
        raise HTTPException(status_code=403, detail="invalid or missing read token")


# Mount the read API twice: bare paths (back-compat) and under /api (the proxied
# prefix that makes remote/tunnel REST work — Fix 5).
from fastapi import Depends as _Depends  # noqa: E402

app.include_router(api, dependencies=[_Depends(_authorize_read)])
app.include_router(api, prefix="/api", dependencies=[_Depends(_authorize_read)])


# ── Control: stop Orrin from the UI ──────────────────────────────────────────
_CONTROL_TOKEN = os.environ.get("ORRIN_CONTROL_TOKEN", "").strip()
_INGEST_TOKEN = os.environ.get("ORRIN_INGEST_TOKEN", "").strip()
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _reject_untrusted_origin(request: Request) -> None:
    """Reject browser requests carrying an Origin we don't trust (UI_AUDIT H2/H3).

    The shutdown / ingest / agent endpoints are side-effecting "simple requests"
    that CORS does NOT stop (no preflight, the side effect fires server-side even
    though the browser can't read the response). So a hostile page on evil.com
    could otherwise POST to 127.0.0.1 and shut Orrin down or inject input. We
    distinguish the real UI from a hostile page by the Origin header: the UI's
    own origin is allowlisted; a foreign Origin is rejected; native clients (the
    in-process producer, curl) send no Origin and pass through.
    """
    origin = (request.headers.get("origin") or "").strip()
    if origin and origin not in set(trusted_origins()):
        raise HTTPException(status_code=403, detail="untrusted origin")


def _authorize_control(request: Request) -> None:
    """Guard /api/control/* — destructive, so it must not be triggerable by any
    network caller (UI_AUDIT H3). Layered:
      • reject any untrusted browser Origin (blocks cross-site CSRF even from a
        loopback-reaching page — UI_AUDIT H2);
      • ORRIN_CONTROL_TOKEN set → require matching X-Orrin-Control-Token header;
      • not set → allow loopback clients only (localhost dev), reject the rest
        with guidance to configure a token for remote use.
    """
    _reject_untrusted_origin(request)
    if _CONTROL_TOKEN:
        supplied = (request.headers.get("X-Orrin-Control-Token") or "").strip()
        if not hmac.compare_digest(supplied, _CONTROL_TOKEN):
            raise HTTPException(status_code=403, detail="invalid or missing control token")
        return
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="control endpoint is localhost-only; set ORRIN_CONTROL_TOKEN to allow remote control",
        )


# A "stop Orrin" handler the orchestrator (main.py) registers. When present, the
# Stop button halts ONLY cognition (loop + daemons) and leaves the UI/window up,
# so you can keep viewing his frozen mind. Absent (e.g. standalone `backend/main.py`),
# Stop falls back to a full-process SIGINT, preserving the old behavior.
_stop_handler: "Optional[Callable[[], None]]" = None


def set_stop_handler(fn: "Callable[[], None]") -> None:
    global _stop_handler
    _stop_handler = fn


def _authorize_ingest(request: Request) -> None:
    """Guard /ingest — the producer entry point (UI_AUDIT H3). Reject hostile
    browser Origins (a page should never spoof the brain's telemetry), and when
    ORRIN_INGEST_TOKEN is set require the matching header so a remote-exposed
    backend only accepts frames from the real cognitive loop. Unset → loopback
    dev is zero-config; the in-process producer sends no Origin and passes."""
    _reject_untrusted_origin(request)
    if _INGEST_TOKEN:
        supplied = (request.headers.get("X-Orrin-Ingest-Token") or "").strip()
        if not hmac.compare_digest(supplied, _INGEST_TOKEN):
            raise HTTPException(status_code=403, detail="invalid or missing ingest token")


@app.post("/api/control/shutdown")
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
    _authorize_control(request)
    await hub.broadcast({"type": "delta", "frame": hub.merge(
        {"logs": [{"level": "warn", "source": "control", "message": "stop requested from UI"}]}
    )})

    if _stop_handler is not None:
        threading.Timer(0.2, _safe_stop).start()
        return {"ok": True, "stopping": True, "scope": "cognition"}

    def _trigger() -> None:
        # Default SIGINT handler raises KeyboardInterrupt in the main thread,
        # which both the embedded launcher and standalone uvicorn.run() handle.
        with contextlib.suppress(Exception):
            os.kill(os.getpid(), signal.SIGINT)

    threading.Timer(0.4, _trigger).start()
    return {"ok": True, "stopping": True, "scope": "process"}


def _safe_stop() -> None:
    """Invoke the registered stop handler, swallowing any error."""
    with contextlib.suppress(Exception):
        if _stop_handler is not None:
            _stop_handler()


# A "reset Orrin" handler the orchestrator (main.py) registers — wipes his state to a
# newborn and re-launches the process. Absent (standalone backend) → reset is
# unavailable rather than a no-op, so the UI can report honestly.
_reset_handler: "Optional[Callable[[], None]]" = None


def set_reset_handler(fn: "Callable[[], None]") -> None:
    global _reset_handler
    _reset_handler = fn


def _safe_reset() -> None:
    with contextlib.suppress(Exception):
        if _reset_handler is not None:
            _reset_handler()


# A "restart Orrin" handler (stop + re-launch, NO wipe) the orchestrator registers —
# used after a Mind Restore swaps his state on disk so the new mind loads clean.
_restart_handler: "Optional[Callable[[], None]]" = None


def set_restart_handler(fn: "Callable[[], None]") -> None:
    global _restart_handler
    _restart_handler = fn


def _safe_restart() -> None:
    with contextlib.suppress(Exception):
        if _restart_handler is not None:
            _restart_handler()


# ── Mind export / import (§9.6) ──────────────────────────────────────────────
@app.get("/api/mind/export")
async def mind_export(request: Request):
    """Stream the full mind as one portable archive (both state trees, atomically).
    Guarded like every control surface."""
    _authorize_control(request)
    from fastapi import Response as _Response
    from brain.utils import mind_archive as _ma
    data = _ma.export_bytes()
    return _Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_ma.export_filename()}"'},
    )


@app.post("/api/mind/import")
async def mind_import(request: Request) -> Dict[str, Any]:
    """Restore a mind from a raw archive (request body = the .orrindmind bytes). The
    current mind is snapshotted FIRST; a bad/foreign/newer archive is refused and the
    running mind is left untouched. On success Orrin restarts so the new state loads."""
    _authorize_control(request)
    from brain.utils import mind_archive as _ma
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty body — send the archive bytes")
    try:
        result = _ma.import_archive(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if _restart_handler is not None:
        threading.Timer(0.4, _safe_restart).start()
        result["restarting"] = True
    return result


# ── Diagnostics export (§10.7) ───────────────────────────────────────────────
@app.get("/api/diagnostics")
async def diagnostics_export(request: Request):
    """Stream an opt-in diagnostics bundle: recent operational logs + the boot/death/
    crash state tag (§10.5) and schema version — NEVER memory content or private
    thoughts (the module enforces an allowlist). Owner-only, guarded like every control
    surface; no silent telemetry — the user chooses to send it."""
    _authorize_control(request)
    from fastapi import Response as _Response
    from brain.utils import diagnostics as _diag
    data = _diag.export_bytes()
    return _Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_diag.export_filename()}"'},
    )


# ── Auto-update (§10.7 / I7) ─────────────────────────────────────────────────
@app.get("/api/update")
async def update_check(request: Request, force: bool = False) -> Dict[str, Any]:
    """Is a newer Orrin published? Opt-in (pref `auto_update_check`) unless `force=1` (an
    explicit 'Check now'). Reports only — never downloads or swaps. Owner-guarded since it
    reaches the network."""
    _authorize_control(request)
    from brain.utils import updater
    return updater.check_for_update(force=bool(force))


@app.post("/api/update/prepare")
async def update_prepare(request: Request) -> Dict[str, Any]:
    """Export the mind to a keepsake BEFORE any update is applied (§10.7) — so even a
    failed update/migration leaves a restorable copy. Returns the backup path + the state
    schema version the new build must understand. The actual binary swap is the platform
    installer's job (Sparkle/Squirrel/zsync), handed off via graceful shutdown."""
    _authorize_control(request)
    from brain.utils import updater
    return updater.prepare_update()


# ── Settings: API keys (kept in the OS keychain) ─────────────────────────────
# The one small WRITE surface Part 4 introduces. Guarded exactly like /api/control/*
# (untrusted Origin rejected; loopback-only unless a control token is configured), so
# a hostile page can't read which keys exist or change them. Values are never
# returned — only booleans — and never logged.
@app.get("/api/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    _authorize_control(request)
    from brain.utils import secrets as _secrets
    from brain.utils import prefs as _prefs
    cfg = _secrets.configured()
    try:
        from brain.cognition.mortality import lifespan_rolled as _rolled
        rolled = _rolled()
    except Exception:
        rolled = False
    # Pluggable LLM providers (Part 11): the menu + the current selection, so Settings
    # can render the single-select. Never exposes a key value — only which are set.
    try:
        from brain.utils import llm_providers as _providers
        _prov_catalog = _providers.catalog()
        _selected = _providers.selected_id()
    except Exception:
        _prov_catalog, _selected = [], "openai"
    try:
        from version import current_version as _ver
        _version = _ver()
    except Exception:
        _version = ""
    return {
        "configured": cfg,
        "symbolic_only": not cfg.get("openai", False),
        "prefs": _prefs.all_prefs(),
        "lifespan_rolled": rolled,
        "version": _version,
        "llm": {
            "providers": _prov_catalog,
            "selected": _selected,
        },
    }


@app.post("/api/settings")
async def update_settings(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Store/clear API keys in the OS keychain. Body keys (all optional):
    `openai_api_key`, `serper_api_key` — an empty string clears that key. Saving the
    OpenAI key re-inits the cached client so it takes effect without a restart."""
    _authorize_control(request)
    from brain.utils import secrets as _secrets

    payload = payload or {}
    changed: list[str] = []
    needs_reinit = False

    # API keys (any provider) — `<name>_api_key`; an empty string clears it.
    for _name in _secrets.ENV_VARS:
        _field = f"{_name}_api_key"
        if _field in payload:
            _secrets.set_key(_name, payload.get(_field))
            changed.append(_name)
            if _name != "serper":  # serper is read per-call from env; needs no re-init
                needs_reinit = True

    # Non-secret toggles + LLM provider selection → config.json.
    from brain.utils import prefs as _prefs
    incoming_prefs = payload.get("prefs")
    if isinstance(incoming_prefs, dict):
        for k, v in incoming_prefs.items():
            if k in _prefs.DEFAULTS:
                _prefs.set(k, bool(v) if isinstance(_prefs.DEFAULTS[k], bool) else v)
                changed.append(f"pref:{k}")
                if k in ("llm_provider", "llm_model", "llm_base_url"):
                    needs_reinit = True

    if needs_reinit:
        # A new key / provider / model takes effect without a restart: drop the cached
        # provider (Part 11) and flip the master LLM switch on when a real provider is
        # now selected, so the tool becomes reachable (llm_gate).
        with contextlib.suppress(Exception):
            from brain.utils.generate_response import reinit_client
            reinit_client()
        with contextlib.suppress(Exception):
            from brain.utils import llm_providers as _providers
            from brain.utils.json_utils import load_json as _lj, save_json as _sj
            from paths import MODEL_CONFIG_FILE as _mcf
            _mc = _lj(_mcf, default_type=dict) or {}
            _mc["llm_enabled"] = _providers.selected_id() != "none"
            _sj(_mcf, _mc)

    cfg = _secrets.configured()
    return {
        "ok": True,
        "changed": changed,
        "configured": cfg,
        "symbolic_only": not cfg.get("openai", False),
        "prefs": _prefs.all_prefs(),
    }


@app.post("/api/llm/test")
async def llm_test(request: Request) -> Dict[str, Any]:
    """Test connection (§11.1): a cheap round-trip with the currently-selected provider
    so the user can confirm a key/endpoint/model works before relying on it."""
    _authorize_control(request)
    from brain.utils import llm_providers as _providers
    provider = _providers.resolve()
    if provider is None:
        return {"ok": False, "message": "No provider selected (symbolic-only)."}
    if not provider.is_configured():
        return {"ok": False, "message": "This provider isn't configured yet (add a key or endpoint)."}
    ok, message = provider.test_connection()
    return {"ok": bool(ok), "message": message, "provider": provider.id, "model": provider.model}


@app.post("/api/control/reset")
async def control_reset(request: Request) -> Dict[str, Any]:
    """Wipe Orrin to a newborn and re-launch. Destructive — same guard as shutdown,
    and the UI gates it behind an explicit confirm. The actual wipe/reseed/restart is
    the orchestrator's job (main.py registered the handler); fires on a short delay so
    this response reaches the UI first."""
    _authorize_control(request)
    if _reset_handler is None:
        raise HTTPException(status_code=503, detail="reset is unavailable in this run mode")
    await hub.broadcast({"type": "delta", "frame": hub.merge(
        {"logs": [{"level": "warn", "source": "control", "message": "reset requested from UI — Orrin is becoming a newborn"}]}
    )})
    threading.Timer(0.3, _safe_reset).start()
    return {"ok": True, "resetting": True}


# ── Producer ingest ──────────────────────────────────────────────────────────
@app.post("/ingest")
async def ingest(frame: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Producer entry point used by TelemetryBridge. Merge + broadcast a delta."""
    _authorize_ingest(request)
    delta = hub.merge(frame or {})
    await hub.broadcast({"type": "delta", "frame": delta})
    return {"ok": True}


# ── Input pipeline: Face → core loop → Face ──────────────────────────────────
@app.post("/api/agent/input")
async def agent_input(body: Dict[str, Any], request: Request) -> Any:
    """The Face submits a user message; queued for the core loop, surfaced on the Brain stream."""
    _reject_untrusted_origin(request)
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


@app.get("/api/agent/inputs")
async def agent_inputs(request: Request) -> Dict[str, Any]:
    """Drain and return all pending Face inputs (used by the core loop)."""
    _reject_untrusted_origin(request)
    items = list(hub.inputs)
    hub.inputs.clear()
    return {"inputs": items}


@app.post("/api/agent/respond")
async def agent_respond(body: Dict[str, Any], request: Request) -> Any:
    """The core loop delivers its reply for a given input id; the Face polls for it."""
    _reject_untrusted_origin(request)
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


@app.get("/api/agent/response/{rid}")
async def agent_response(rid: str, request: Request) -> Dict[str, Any]:
    """One-shot fetch of the agent's reply for an input id (consumed on read)."""
    _reject_untrusted_origin(request)
    r = hub.responses.pop(rid, None)
    return {"reply": r["reply"] if r else None}


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
    if _READ_TOKEN:
        client_host = (ws.client.host if ws.client else "") or ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            supplied = (ws.query_params.get("token") or "").strip()
            if not hmac.compare_digest(supplied, _READ_TOKEN):
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
