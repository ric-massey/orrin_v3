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
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .config import RESPONSE_CAP, demo_enabled
from .demo import run_demo
from .hub import Hub

hub = Hub()


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

# Dev CORS — the Vite dev server runs on a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
_DATA_DIR = _REPO_ROOT / "brain" / "data"


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
        target.relative_to(_REPO_ROOT)  # repo-jail
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
async def memory_store(store: str = "long", q: str = "", n: int = 50, offset: int = 0) -> JSONResponse:
    """Paged, newest-first browse of a REAL memory store file — what he actually
    remembers, as opposed to the live op ring the WS streams (which is a sampled
    ticker of this session's reads/writes, not the store)."""
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
        entries = list(reversed(entries))  # newest-first (stores append)
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

def _read_json(fname: str, default: Any) -> Any:
    import json as _json
    try:
        d = _json.loads((_DATA_DIR / fname).read_text("utf-8"))
        return d if isinstance(d, type(default)) else default
    except Exception:
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
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _authorize_control(request: Request) -> None:
    """Guard /api/control/* — destructive, so it must not be triggerable by any
    network caller (UI_AUDIT H3). Two modes:
      • ORRIN_CONTROL_TOKEN set → require matching X-Orrin-Control-Token header.
      • not set → allow loopback clients only (localhost dev), reject the rest
        with guidance to configure a token for remote use.
    """
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


@app.post("/api/control/shutdown")
async def control_shutdown(request: Request) -> Dict[str, Any]:
    """
    Stop Orrin from the UI. The telemetry API runs inside the launcher process
    (embedded in a daemon thread), so raising SIGINT here drives the launcher's
    existing KeyboardInterrupt path — full graceful shutdown of the cognitive
    loop, daemons, WAL flush, and the Vite UI child tree (via stop_ui).

    The signal is fired on a short delay so this HTTP response reaches the UI
    before the process tears down.
    """
    _authorize_control(request)
    await hub.broadcast({"type": "delta", "frame": hub.merge(
        {"logs": [{"level": "warn", "source": "control", "message": "shutdown requested from UI"}]}
    )})

    def _trigger() -> None:
        # Default SIGINT handler raises KeyboardInterrupt in the main thread,
        # which both the embedded launcher and standalone uvicorn.run() handle.
        with contextlib.suppress(Exception):
            os.kill(os.getpid(), signal.SIGINT)

    threading.Timer(0.4, _trigger).start()
    return {"ok": True, "stopping": True}


# ── Producer ingest ──────────────────────────────────────────────────────────
@app.post("/ingest")
async def ingest(frame: Dict[str, Any]) -> Dict[str, Any]:
    """Producer entry point used by TelemetryBridge. Merge + broadcast a delta."""
    delta = hub.merge(frame or {})
    await hub.broadcast({"type": "delta", "frame": delta})
    return {"ok": True}


# ── Input pipeline: Face → core loop → Face ──────────────────────────────────
@app.post("/api/agent/input")
async def agent_input(body: Dict[str, Any]) -> Any:
    """The Face submits a user message; queued for the core loop, surfaced on the Brain stream."""
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
async def agent_inputs() -> Dict[str, Any]:
    """Drain and return all pending Face inputs (used by the core loop)."""
    items = list(hub.inputs)
    hub.inputs.clear()
    return {"inputs": items}


@app.post("/api/agent/respond")
async def agent_respond(body: Dict[str, Any]) -> Any:
    """The core loop delivers its reply for a given input id; the Face polls for it."""
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
async def agent_response(rid: str) -> Dict[str, Any]:
    """One-shot fetch of the agent's reply for an input id (consumed on read)."""
    r = hub.responses.pop(rid, None)
    return {"reply": r["reply"] if r else None}


# ── Landing page ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (
        "<html><body style='font-family:ui-monospace,monospace;background:#0a0a0a;"
        "color:#e5e5e5;padding:2rem'>"
        "<h2>Orrin Telemetry Bridge</h2>"
        "<p>WebSocket: <code>/ws/telemetry</code> &nbsp;·&nbsp; Ingest: "
        "<code>POST /ingest</code> &nbsp;·&nbsp; Snapshot: <code>GET /state</code></p>"
        f"<p>Connected UI clients: {hub.client_count}</p>"
        "<p>Start the UI with <code>cd frontend &amp;&amp; npm run dev</code>.</p>"
        "</body></html>"
    )


# ── WebSocket (consumers; also accepts producer-over-WS frames) ──────────────
@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
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
