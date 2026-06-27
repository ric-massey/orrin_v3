# Phase 2 of GOALS_MASTER_PLAN_2026-06-23 — the deficit→goal recruiter.
#
# Covers, matching the plan:
#   • build_survival_goal — survival tier, driven_by = the homeostatic signal,
#     first plan step = the alert's suggested_fn, recruit_aid stamped, priority floor.
#   • recruit_survival_goal — submits via context["proposed_goals"] (the intrinsic
#     path) and is REFRACTORY: it won't recruit the same alert id while one is open.
#   • tier1_health_check — a deficit ignored past RECRUIT_AFTER_CYCLES escalates
#     into a recruited goal (and not before); warnings get their own neglect counter.
#   • executive priority floor — 'survival' outranks 'growth'/'core' in step allocation.
from typing import Any, Dict

import brain.runtime_coupling.setpoint_regulation as spr
import brain.cognition.planning.survival_goals as sg
import brain.cognition.planning.executive as ex
from brain.loop.reflect import tier1_health_check


def _alert(severity: str = "critical", aid: str = "resource_deficit_critical") -> Dict[str, Any]:
    return {
        "id": aid,
        "severity": severity,
        "description": "resource deficit critical — rest needed",
        "tags": ["resource_deficit"],
        "suggested_fn": "rest",
    }


def _state(severity: str = "critical") -> Dict[str, Any]:
    return {"health_score": 0.9, "alerts": [_alert(severity)]}


# ── build_survival_goal ────────────────────────────────────────────────────────

def test_build_survival_goal_shape():
    g = sg.build_survival_goal(_alert())
    assert g["tier"] == sg.SURVIVAL_TIER
    assert g["driven_by"] == "resource_deficit"        # the homeostatic signal (tag)
    assert g["recruit_aid"] == "resource_deficit_critical"
    assert g["priority"] == sg.SURVIVAL_PRIORITY
    assert g["kind"] == "generic"                       # routes through the intrinsic sync path
    # first plan step IS the alert's suggested_fn
    assert g["plan"][0]["step"] == "rest"
    assert g["next_action"] == "rest"
    assert g["milestones"] and g["milestones"][0]["met"] is False


def test_signal_derived_from_id_when_no_tag():
    a = _alert()
    a["tags"] = []
    g = sg.build_survival_goal(a)
    assert g["driven_by"] == "resource_deficit"        # '_critical' suffix stripped


def test_missing_suggested_fn_falls_back_to_rest():
    a = _alert()
    a.pop("suggested_fn")
    g = sg.build_survival_goal(a)
    assert g["plan"][0]["step"] == "rest"


# ── recruit_survival_goal (submission + refractory dedup) ───────────────────────

def test_recruit_appends_to_proposed_goals(monkeypatch):
    # isolate from the on-disk store so dedup only sees this cycle's proposals
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [])
    ctx: Dict[str, Any] = {}
    g = sg.recruit_survival_goal(_alert(), ctx)
    assert g is not None
    assert ctx["proposed_goals"] == [g]
    assert g["source"] == "survival_recruit"


def test_recruit_is_refractory_within_cycle(monkeypatch):
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [])
    ctx: Dict[str, Any] = {}
    first = sg.recruit_survival_goal(_alert(), ctx)
    second = sg.recruit_survival_goal(_alert(), ctx)   # same aid, already queued
    assert first is not None and second is None
    assert len(ctx["proposed_goals"]) == 1


def test_recruit_refractory_against_open_store_goal(monkeypatch):
    # an open goal carrying this recruit_aid already exists in the store → skip
    open_goal = {"recruit_aid": "resource_deficit_critical", "status": "in_progress"}
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [open_goal])
    ctx: Dict[str, Any] = {}
    assert sg.recruit_survival_goal(_alert(), ctx) is None
    assert ctx.get("proposed_goals", []) == []


def test_recruit_again_once_store_goal_is_terminal(monkeypatch):
    done_goal = {"recruit_aid": "resource_deficit_critical", "status": "completed"}
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [done_goal])
    ctx: Dict[str, Any] = {}
    assert sg.recruit_survival_goal(_alert(), ctx) is not None   # terminal → re-recruitable


# ── tier1_health_check integration: neglect → recruitment ──────────────────────

def test_chronic_deficit_recruits_after_threshold(monkeypatch):
    monkeypatch.setattr(spr, "get_state", _state)
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [])
    ctx: Dict[str, Any] = {}
    # Run cycles up to (but not at) the threshold — no recruitment yet.
    for _ in range(sg.RECRUIT_AFTER_CYCLES - 1):
        tier1_health_check(ctx)
    assert not ctx.get("proposed_goals")
    # The cycle that crosses the threshold recruits exactly one goal.
    tier1_health_check(ctx)
    proposed = ctx.get("proposed_goals") or []
    assert len(proposed) == 1
    assert proposed[0]["tier"] == "survival"
    # Further cycles don't pile on duplicates (refractory).
    tier1_health_check(ctx)
    assert len(ctx["proposed_goals"]) == 1


def test_warning_severity_also_recruits(monkeypatch):
    monkeypatch.setattr(spr, "get_state", lambda: _state("warning"))
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [])
    ctx: Dict[str, Any] = {}
    for _ in range(sg.RECRUIT_AFTER_CYCLES):
        tier1_health_check(ctx)
    assert len(ctx.get("proposed_goals") or []) == 1


# ── executive survival priority floor ──────────────────────────────────────────

def test_survival_tier_outranks_growth_and_core():
    def _g(gid, tier):
        return {"id": gid, "title": gid, "status": "in_progress", "tier": tier,
                "plan": [{"step": f"{gid}-1", "status": "pending"}]}
    q = [_g("grow", "growth"), _g("surv", "survival"), _g("core", "core")]
    alloc = {g["id"]: n for g, n in ex._allocate_steps(q, rr=0, budget=99)}
    assert alloc["surv"] == 4          # survival weight is the highest
    assert alloc["surv"] > alloc["core"] and alloc["surv"] > alloc["grow"]
