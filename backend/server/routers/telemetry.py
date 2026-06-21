"""Read-only telemetry/projection routes (the api read router).

Split out of app.py (Phase 4C). These are GET projections over Orrin's persisted
state files — what the Face & Brain UI renders. They are mounted on the read `api`
router by app.py (so they inherit the optional read-token guard) and use the shared
read helpers in state.py. Routes are moved here in cohesive domain batches.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import state as server_state
from ..state import _read_json, _read_jsonl_tail

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


# ── Benchmarks / outcomes / symbolic mind ───────────────────────────────────
@router.get("/benchmarks")
async def benchmarks(samples: int = 0) -> JSONResponse:
    """B1–B5 from benchmark_results.json — the headline 'is he actually working'
    answer, previously visible only by reading the file. Renders fail/not_run
    states first-class. ?samples=N also tails benchmark_samples.jsonl (L3/L4)."""
    res = _read_json("benchmark_results.json", {})
    out: dict = {"evaluated_at": res.get("evaluated_at"),
                 "sample_count": res.get("sample_count"),
                 "benchmarks": {k: v for k, v in res.items()
                                if k.startswith("B") and isinstance(v, dict)}}
    if samples:
        out["samples"] = _read_jsonl_tail("benchmark_samples.jsonl", min(200, samples))
    return JSONResponse(out)


@router.get("/outcomes")
async def outcomes() -> JSONResponse:
    """Daily goal-closure metrics (outcome_metrics.json) — the closure-remediation
    story: does the goal population stay bounded, and HOW do goals close."""
    hist = _read_json("outcome_metrics.json", [])
    return JSONResponse({"history": hist[-90:], "latest": (hist[-1] if hist else None)})


@router.get("/innerweather")
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


@router.get("/symbolic")
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


# ── Introspection: tensions / health / self / people ────────────────────────
@router.get("/tensions")
async def tensions(n: int = 20) -> JSONResponse:
    """What he's wrestling with: active tensions, rumination loops, and the
    second-order volition timeline (what he wants to WANT — stance · desire ·
    statement, dated)."""
    return JSONResponse({
        "tensions": _read_json("tensions.json", [])[-max(1, min(50, n)):],
        "rumination": _read_json("rumination_loops.json", [])[-max(1, min(50, n)):],
        "volition": _read_json("second_order_volition.json", [])[-max(1, min(50, n)):],
    })


@router.get("/health")
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


@router.get("/self")
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


@router.get("/people")
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
