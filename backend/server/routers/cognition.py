"""Cognition-analysis read routes: prediction calibration, behavior change,
belief revision, drives, and learning.

Split out of app.py (Phase 4C). Read-only projections over Orrin's persisted
state, mounted on the read `api` router by app.py; they use the shared read
helpers in state.py.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..state import _belief_churn, _float_or_none, _read_json, _read_jsonl_tail

router = APIRouter()


@router.get("/predictions")
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


@router.get("/behavior-changes")
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


@router.get("/belief-revisions")
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


@router.get("/demands")
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


@router.get("/learning")
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
