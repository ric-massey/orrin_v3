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
import signal
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from pathlib import Path as _Path2

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import demo_enabled, trusted_origins
from .demo import run_demo
from . import state as server_state
from .state import hub, _read_json, _read_jsonl_tail, _float_or_none, _belief_churn
# Request auth guards live in auth.py (Phase 4C) so domain routers can guard
# themselves without importing app.py. Keep the historical underscore names here.
from .auth import (
    authorize_read as _authorize_read,
    authorize_control as _authorize_control,
    ws_read_authorized as _ws_read_authorized,
)
from .routers import memory as memory_routes
from .routers import source as source_routes
from .routers import diagnostics as diagnostics_routes
from .routers import settings as settings_routes
from .routers import agent as agent_routes


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


@api.get("/catalog")
async def catalog() -> JSONResponse:
    """The map of Orrin's mind: functions → subsystem/file/line/summary, merged
    with live per-function decision stats (count / avg_reward)."""
    cat = hub.state.get("catalog") or {"functions": {}, "subsystems": {}}
    stats: Dict[str, Any] = {}
    try:
        import json as _json
        stats = _json.loads((server_state._DATA_DIR / "decision_stats.json").read_text("utf-8"))
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
        chains = _json.loads((server_state._DATA_DIR / "function_chains.json").read_text("utf-8"))
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
        h = _json.loads((server_state._DATA_DIR / "cognition_history.json").read_text("utf-8"))
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
        raw = _json.loads((server_state._DATA_DIR / "goals_mem.json").read_text("utf-8"))
        from goal_io import summarize_goal_tree
        active_id = None
        for item in (hub.state.get("goals") or []):
            if isinstance(item, dict) and item.get("active"):
                active_id = item.get("id")
                break
        out = summarize_goal_tree(raw, committed_id=active_id)
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
        goals_raw = _json.loads((server_state._DATA_DIR / "goals_mem.json").read_text("utf-8"))
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

        lm = _json.loads((server_state._DATA_DIR / "long_memory.json").read_text("utf-8"))
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


# ── Consciousness stream: the actual stream the panel is named for (Fix 4) ───
@api.get("/consciousness")
async def consciousness(n: int = 60) -> JSONResponse:
    """Tail of the persisted conscious stream — the rolling list of conscious
    moments {content, source, salience, ts} written by global_workspace."""
    try:
        import json as _json
        data = _json.loads((server_state._DATA_DIR / "conscious_stream.json").read_text("utf-8"))
        if not isinstance(data, list):
            data = []
        out = [m for m in data[-max(1, min(200, n)):] if isinstance(m, dict)]
        return JSONResponse({"moments": out, "total": len(data)})
    except Exception as e:
        return JSONResponse({"moments": [], "total": 0, "error": str(e)})




# ── Chat history: the canonical conversation log (Fix 10.4) ──────────────────
@api.get("/chat")
async def chat_history(n: int = 100) -> JSONResponse:
    """Tail of brain/data/chat_log.json so a new browser/device can show the real
    shared conversation history instead of an empty localStorage one."""
    try:
        import json as _json
        data = _json.loads((server_state._DATA_DIR / "chat_log.json").read_text("utf-8"))
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
    resolved = sorted(
        [p for p in preds if p.get("resolved") or p.get("status") == "evaluated"],
        key=lambda p: str(p.get("checked_ts") or p.get("created_ts") or ""),
    )

    def _brier(p: Dict[str, Any]) -> Optional[float]:
        conf = _float_or_none(p.get("confidence"))
        if conf is None:
            return None
        if p.get("correct") is True or p.get("outcome") == "correct":
            truth = 1.0
        elif p.get("correct") is False or p.get("outcome") == "incorrect" or str(p.get("outcome") or "").startswith("mismatch"):
            truth = 0.0
        else:
            return None
        return (conf - truth) ** 2

    calibration_trend: list[Dict[str, Any]] = []
    brier_window: list[float] = []
    for p in resolved[-160:]:
        b = _brier(p)
        if b is None:
            continue
        brier_window.append(b)
        window = brier_window[-25:]
        calibration_trend.append({
            "timestamp": p.get("checked_ts") or p.get("created_ts"),
            "brier": round(sum(window) / len(window), 4),
            "n": len(window),
        })
    if len(calibration_trend) > 40:
        step = max(1, len(calibration_trend) // 40)
        calibration_trend = calibration_trend[::step][-40:]

    explore_fns = {
        "seek_novelty", "look_outward", "look_around", "search_own_files",
        "research_topic", "wikipedia_search", "fetch_wikipedia", "fetch_and_read",
        "read_rss", "generate_intrinsic_goals", "generate_concepts_from_memories",
    }
    choices: list[Dict[str, Any]] = []
    for ev in _read_jsonl_tail("trace.jsonl", 800):
        if not isinstance(ev, dict):
            continue
        chosen = ev.get("chosen")
        if not isinstance(chosen, str) or not chosen.startswith("FN:"):
            continue
        fn = chosen[3:]
        choices.append({"fn": fn, "explore": fn in explore_fns, "ts": ev.get("ts")})
    recent_choices = choices[-80:]
    explore_count = sum(1 for c in recent_choices if c["explore"])
    novelty_trend: list[Dict[str, Any]] = []
    if recent_choices:
        bucket = max(1, len(recent_choices) // 20)
        for i in range(0, len(recent_choices), bucket):
            chunk = recent_choices[i:i + bucket]
            novelty_trend.append({
                "timestamp": chunk[-1].get("ts"),
                "exploration_ratio": round(sum(1 for c in chunk if c["explore"]) / len(chunk), 3),
                "n": len(chunk),
            })
    return JSONResponse({
        "calibration": _read_json("calibration_state.json", {}),
        "calibration_trend": calibration_trend,
        "exploration": {
            "explore": explore_count,
            "exploit": len(recent_choices) - explore_count,
            "ratio": round(explore_count / len(recent_choices), 3) if recent_choices else None,
            "trend": novelty_trend[-40:],
        },
        "domains": _read_json("prediction_domain_stats.json", {}),
        # Phase 1.3: felt-vs-behaved agreement per domain — how much his
        # introspection has earned the right to be believed.
        "introspection_trust": _read_json("introspection_trust.json", {}),
        "recent": preds[-max(1, min(100, n)):],
        "total": len(preds),
    })


@api.get("/behavior-changes")
async def behavior_changes(n: int = 40) -> JSONResponse:
    """The behavior-change log: each time the adaptation engine rewrites how Orrin
    acts (suppress an over-used function, force action, inject novelty), it records
    a structured before → after → because diff. This is the dashboard's answer to
    'is he actually learning?' — it shows policy CHANGES and their causes, not just
    standing counts. Most-recent first."""
    rows = [r for r in _read_json("behavior_changes.json", []) if isinstance(r, dict)]
    cap = max(1, min(200, n))
    by_pattern: Dict[str, int] = {}
    for r in rows:
        p = str(r.get("pattern") or "unknown")
        by_pattern[p] = by_pattern.get(p, 0) + 1
    return JSONResponse({
        "changes": list(reversed(rows))[:cap],
        "total": len(rows),
        "by_pattern": by_pattern,
    })


@api.get("/belief-revisions")
async def belief_revisions(n: int = 80) -> JSONResponse:
    """Unified belief-revision feed (UI plan §5.2): self-belief confidence moves,
    opinion updates, and symbolic-rule revisions in one chronological stream.
    Rows are newest-first and carry old→new confidence when the source log makes
    that reconstructable, plus evidence counts and churn counters per belief class."""
    rows: list[Dict[str, Any]] = []

    self_revs = _read_json("self_belief_revisions.json", {})
    if isinstance(self_revs, dict):
        for dom, rec in self_revs.items():
            if not isinstance(rec, dict):
                continue
            events = [ev for ev in rec.get("events") or [] if isinstance(ev, dict)]
            for ev in events:
                new_conf = _float_or_none(ev.get("new_confidence") or rec.get("confidence"))
                delta = _float_or_none(ev.get("delta"))
                old_conf = (new_conf - delta) if new_conf is not None and delta is not None else None
                rows.append({
                    "kind": "self",
                    "timestamp": ev.get("timestamp"),
                    "subject": str(rec.get("domain") or dom),
                    "summary": ev.get("goal") or ev.get("reflection") or ev.get("source"),
                    "old_confidence": old_conf,
                    "new_confidence": new_conf,
                    "confidence_delta": delta,
                    "evidence_count": int(ev.get("evidence_count") or len(events) or 0),
                    "source": ev.get("source") or "self_belief_revisions",
                })
    elif isinstance(self_revs, list):
        for ev in [e for e in self_revs if isinstance(e, dict)]:
            rows.append({
                "kind": "self",
                "timestamp": ev.get("timestamp"),
                "subject": str(ev.get("domain") or ev.get("source") or "self-belief"),
                "summary": ev.get("reflection") or ev.get("goal") or ev.get("status"),
                "old_confidence": _float_or_none(ev.get("old_confidence")),
                "new_confidence": _float_or_none(ev.get("new_confidence") or ev.get("confidence")),
                "confidence_delta": _float_or_none(ev.get("delta")),
                "evidence_count": int(ev.get("evidence_count") or 0),
                "source": ev.get("source") or "self_belief_revisions",
            })

    opinions = [o for o in _read_json("opinions.json", []) if isinstance(o, dict)]
    for o in opinions:
        rows.append({
            "kind": "opinion",
            "timestamp": o.get("updated_at") or o.get("formed_at"),
            "subject": str(o.get("topic") or o.get("id") or "opinion"),
            "summary": o.get("view"),
            "old_confidence": None,
            "new_confidence": _float_or_none(o.get("confidence")),
            "confidence_delta": None,
            "evidence_count": int(o.get("evidence_count") or len(o.get("evidence") or []) or 0),
            "source": o.get("formation_method") or "opinions",
        })

    rules_by_id = {
        str(r.get("id")): r
        for r in _read_json("symbolic_rules.json", [])
        if isinstance(r, dict) and r.get("id")
    }
    rule_revs = [r for r in _read_json("rule_revisions.json", []) if isinstance(r, dict)]
    prior_by_rule: Dict[str, float] = {}
    for rev in sorted(rule_revs, key=lambda r: str(r.get("timestamp") or "")):
        rule_id = str(rev.get("rule_id") or "")
        new_conf = _float_or_none(rev.get("confidence"))
        old_conf = prior_by_rule.get(rule_id)
        delta = (new_conf - old_conf) if new_conf is not None and old_conf is not None else None
        rule = rules_by_id.get(rule_id, {})
        evidence = rule.get("evidence_ids")
        rows.append({
            "kind": "symbolic_rule",
            "timestamp": rev.get("timestamp"),
            "subject": rule_id or "symbolic rule",
            "summary": rev.get("rule_conclusion") or rule.get("conclusion"),
            "old_confidence": old_conf,
            "new_confidence": new_conf,
            "confidence_delta": delta,
            "evidence_count": int(len(evidence) if isinstance(evidence, list) else (rule.get("hits") or 0)),
            "source": rev.get("query") or rule.get("source") or "rule_revisions",
            "status": rev.get("status"),
        })
        if new_conf is not None and rule_id:
            prior_by_rule[rule_id] = new_conf

    rows.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
    cap = max(1, min(300, n))
    return JSONResponse({
        "revisions": rows[:cap],
        "total": len(rows),
        "churn": _belief_churn(rows),
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
    avg_reward), bandit suppressions, the recent reward trace, top goal progress,
    and the current function-rut readout."""
    ds = _read_json("decision_stats.json", {})
    rows = sorted(
        ({"fn": k, "count": int(v.get("count") or 0), "avg_reward": round(float(v.get("avg_reward") or 0), 3)}
         for k, v in ds.items() if isinstance(v, dict)),
        key=lambda r: r["count"], reverse=True,
    )
    bandit = _read_json("bandit_state.json", {})

    goals_seen: set[str] = set()
    goal_rows: list[Dict[str, Any]] = []

    def _add_goal(o: Any) -> None:
        if not isinstance(o, dict) or not o.get("title"):
            return
        gid = str(o.get("id") or o.get("title"))
        if gid in goals_seen:
            return
        goals_seen.add(gid)
        milestones = [m for m in (o.get("milestones") or []) if isinstance(m, dict)]
        plan = [p for p in (o.get("plan") or []) if isinstance(p, dict)]
        met = sum(1 for m in milestones if m.get("met"))
        done = sum(1 for p in plan if "complet" in str(p.get("status") or "").lower())
        total = len(milestones) or len(plan)
        progressed = met if milestones else done
        progress = round(progressed / total, 3) if total else None
        status = str(o.get("status") or "unknown")
        goal_rows.append({
            "id": o.get("id"),
            "title": o.get("title"),
            "status": status,
            "tier": o.get("tier"),
            "priority": o.get("priority"),
            "milestones_met": met,
            "milestones_total": len(milestones),
            "steps_done": done,
            "steps_total": len(plan),
            "progress": progress,
            "last_updated": o.get("last_updated") or o.get("completed_timestamp") or o.get("created_at"),
        })

    def _walk_goals(o: Any) -> None:
        if isinstance(o, dict):
            _add_goal(o)
            for v in o.values():
                _walk_goals(v)
        elif isinstance(o, list):
            for v in o:
                _walk_goals(v)

    goals_mem = _read_json("goals_mem.json", {})
    if not goals_mem:
        goals_mem = _read_json("goals_mem.json", [])
    comp_goals = _read_json("comp_goals.json", [])
    if not comp_goals:
        comp_goals = _read_json("comp_goals.json", {})
    _walk_goals(goals_mem)
    _walk_goals(comp_goals)

    def _goal_sort_key(g: Dict[str, Any]) -> tuple:
        status = str(g.get("status") or "").lower()
        active_rank = 0 if "active" in status or "progress" in status else 1
        # Surface objectives that have a real milestone/step bar above ones with no
        # trackable progress, so the top cards aren't blank (UI plan §5.5 polish).
        measurable_rank = 0 if g.get("progress") is not None else 1
        try:
            pri = -float(g.get("priority") or 0)
        except Exception:
            pri = 0.0
        return (active_rank, measurable_rank, pri, str(g.get("last_updated") or ""))

    top_goals = sorted(
        [g for g in goal_rows if str(g.get("tier") or "").lower() != "housekeeping"],
        key=_goal_sort_key,
        reverse=False,
    )[:8]

    cog = _read_json("cognition_state.json", {})
    recent_picks = [str(p) for p in (cog.get("recent_picks") or []) if p]
    window = recent_picks[-8:]
    counts: Dict[str, int] = {}
    for fn in window:
        counts[fn] = counts.get(fn, 0) + 1
    top_fn, top_count = ("", 0)
    if counts:
        top_fn, top_count = max(counts.items(), key=lambda kv: kv[1])
    last_fn = str(cog.get("last_cognition_choice") or (recent_picks[-1] if recent_picks else ""))
    consecutive = 0
    for fn in reversed(recent_picks):
        if fn == last_fn:
            consecutive += 1
        else:
            break
    rut_score = round(top_count / len(window), 3) if window else 0.0
    return JSONResponse({
        "functions": rows[:max(1, min(50, n))],
        "suppressed": bandit.get("suppressed") or {},
        "reward_trace": _read_json("reward_trace.json", [])[-40:],
        "goal_progress": {
            "goals": top_goals,
            "total": len(goal_rows),
            "milestones_met": sum(int(g.get("milestones_met") or 0) for g in goal_rows),
            "milestones_total": sum(int(g.get("milestones_total") or 0) for g in goal_rows),
        },
        "rut": {
            "function": top_fn,
            "score": rut_score,
            "top_count": top_count,
            "window": len(window),
            "threshold": 0.75,
            "consecutive_function": last_fn,
            "consecutive": int(cog.get("repeat_count") or consecutive),
            "recent": recent_picks[-20:],
        },
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


@api.get("/permissions")
async def permissions() -> JSONResponse:
    """OS capability grant-state for the Trust screen (§10.6): per-capability whether
    Orrin's body can see your screen / control apps / notify you, with a deep-link to
    the right System Settings pane. Non-prompting; honest about what's off."""
    try:
        from brain.utils.os_permissions import status as _perm_status
        return JSONResponse(_perm_status())
    except Exception as e:
        return JSONResponse({"platform": "", "capabilities": [], "error": str(e)})


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


# ── Control: stop Orrin from the UI ──────────────────────────────────────────
# A "stop Orrin" handler the orchestrator (main.py) registers. When present, the
# Stop button halts ONLY cognition (loop + daemons) and leaves the UI/window up,
# so you can keep viewing his frozen mind. Absent (e.g. standalone `backend/main.py`),
# Stop falls back to a full-process SIGINT, preserving the old behavior.
_stop_handler: "Optional[Callable[[], None]]" = None


def set_stop_handler(fn: "Callable[[], None]") -> None:
    global _stop_handler
    _stop_handler = fn


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
