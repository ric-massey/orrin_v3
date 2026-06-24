# Phase 1 of GOALS_MASTER_PLAN_2026-06-23 — wire the acute survival preempt.
#
# Two halves, matching the plan:
#   (a) the producer/consumer KEY is reconciled: tier1_health_check now writes
#       context["_setpoint_critical"] (the key goal_closure._survival_critical
#       reads), where before tier1 wrote a *different* key (_tier1_critical) and
#       the preempt read a key nothing set — producer and consumer passed in the
#       night.
#   (b) the preempt has HYSTERESIS: a critical must hold for >=2 consecutive
#       cycles before it seizes the goal slot, and one clean cycle clears the
#       streak — so a vital signal dithering at the threshold can't ping-pong the
#       committed goal every cycle.
#
# The integration assertion is the plan's exit criterion: a critical alert
# preempts pursue_committed_goal with reason="survival_preempt", and the
# committed goal is NOT mutated (the yield is transient/resumable, not a failure).
import copy
from typing import Any, Dict

import brain.embodiment.setpoint_regulation as spr
import brain.cognition.planning.goal_closure as gc
import brain.cognition.planning.goal_execution as gex
from brain.loop.reflect import tier1_health_check


def _critical_state() -> Dict[str, Any]:
    return {
        "health_score": 0.9,  # health path NOT tripped; isolate the setpoint key
        "alerts": [
            {
                "id": "resource_deficit_critical",
                "severity": "critical",
                "description": "resource deficit critical — rest needed",
                "tags": ["resource_deficit"],
                "suggested_fn": "rest",
            }
        ],
    }


def _clean_state() -> Dict[str, Any]:
    return {"health_score": 1.0, "alerts": []}


# ── (a) the wire: tier1_health_check writes the key the preempt consumer reads ──

def test_tier1_sets_setpoint_critical_key(monkeypatch):
    monkeypatch.setattr(spr, "get_state", _critical_state)
    ctx: Dict[str, Any] = {}
    tier1_health_check(ctx)
    assert ctx["_setpoint_critical"] is True
    # reason stashed so the preempt can name why it yielded
    assert ctx["_setpoint_critical_reason"] == "resource_deficit_critical"


def test_tier1_clears_setpoint_critical_when_resolved(monkeypatch):
    # context persists across cycles; a critical that clears must un-set the key,
    # else the preempt would latch on forever.
    monkeypatch.setattr(spr, "get_state", _critical_state)
    ctx: Dict[str, Any] = {}
    tier1_health_check(ctx)
    assert ctx["_setpoint_critical"] is True

    monkeypatch.setattr(spr, "get_state", _clean_state)
    tier1_health_check(ctx)
    assert ctx["_setpoint_critical"] is False
    assert "_setpoint_critical_reason" not in ctx


# ── (b) hysteresis in _survival_critical ───────────────────────────────────────

def test_hysteresis_requires_two_consecutive_cycles():
    ctx = {"_setpoint_critical": True, "_setpoint_critical_reason": "rd_crit"}
    # cycle 1: critical seen for the first time → no preempt yet (streak 0→1)
    crit, why = gc._survival_critical(ctx)
    assert crit is False and ctx["_survival_crit_streak"] == 1
    # cycle 2: still critical → preempt fires (streak 1→2)
    crit, why = gc._survival_critical(ctx)
    assert crit is True and why == "rd_crit" and ctx["_survival_crit_streak"] == 2


def test_one_clean_cycle_clears_the_streak():
    ctx = {"_setpoint_critical": True}
    gc._survival_critical(ctx)            # streak 1
    gc._survival_critical(ctx)            # streak 2 → preempting
    ctx["_setpoint_critical"] = False     # one clean cycle
    crit, _ = gc._survival_critical(ctx)
    assert crit is False and ctx["_survival_crit_streak"] == 0
    # back to critical: must build the streak from scratch again (no instant re-fire)
    ctx["_setpoint_critical"] = True
    crit, _ = gc._survival_critical(ctx)
    assert crit is False and ctx["_survival_crit_streak"] == 1


# ── integration: reflect → pursue yields, goal untouched ───────────────────────

def test_critical_alert_preempts_pursuit_without_mutating_goal(monkeypatch):
    monkeypatch.setattr(spr, "get_state", _critical_state)
    monkeypatch.setenv("ORRIN_SURVIVAL_PREEMPT", "1")
    # avoid the pursue cooldown short-circuit
    monkeypatch.setattr(gex, "_last_pursuit_ts", 0.0)

    goal = {
        "id": "g-build-thing",
        "title": "build the thing",
        "status": "in_progress",
        "tier": "growth",
        "plan": [{"step": "step 1", "status": "pending"}],
    }
    ctx: Dict[str, Any] = {"committed_goal": goal}
    tier1_health_check(ctx)                       # writes _setpoint_critical
    ctx["_survival_crit_streak"] = 1              # prior cycle was already critical

    goal_before = copy.deepcopy(goal)
    result = gex.pursue_committed_goal(ctx)

    assert result["skipped"] is True
    assert result["reason"] == "survival_preempt"
    assert result["detail"] == "resource_deficit_critical"
    # transient/resumable: the committed goal is left exactly as it was
    assert ctx["committed_goal"] == goal_before
