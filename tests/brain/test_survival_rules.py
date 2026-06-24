# Phase 3 of GOALS_MASTER_PLAN_2026-06-23 — survival goals behave by survival rules.
#
#   1. NON-DISENGAGEABLE: _degrade_or_disengage never abandons a tier='survival'
#      goal (a non-survival goal in the same spot still disengages).
#   2. SATIETY-WITH-RETURN: a satisfied survival goal goes 'dormant' (not
#      'completed'), stamped with _satisfied_ts, and fires no achievement reward.
#   3. RE-FIRE INTERVAL: the recruiter won't re-recruit a dormant deficit inside
#      MIN_REFIRE_INTERVAL_S, but does once that interval has passed.
import time
from typing import Any, Dict

import brain.cognition.planning.goal_closure as gc
import brain.cognition.planning.survival_goals as sg


# ── 1. non-disengageable ───────────────────────────────────────────────────────

def test_survival_goal_is_not_disengaged(monkeypatch):
    monkeypatch.setattr(gc, "update_working_memory", lambda *a, **k: None)
    # _degraded=True forces the "already reduced → disengage" branch.
    goal = {"id": "s1", "title": "Restore: rest needed", "tier": "survival",
            "status": "in_progress", "_degraded": True}
    ctx: Dict[str, Any] = {"committed_goal": goal}
    result = gc._degrade_or_disengage(goal, ctx, goal["title"], reason="no progress")
    assert result is None                       # held, not disengaged
    assert goal["status"] == "in_progress"      # not marked failed/abandoned
    assert ctx["committed_goal"] is goal        # slot kept


def test_nonsurvival_goal_still_disengages(monkeypatch):
    monkeypatch.setattr(gc, "update_working_memory", lambda *a, **k: None)
    failed = {"called": False}

    def _fake_mark_failed(g, reason="", context=None):
        failed["called"] = True
        g["status"] = "failed"

    monkeypatch.setattr("brain.cognition.planning.goals.mark_goal_failed", _fake_mark_failed)
    goal = {"id": "g1", "title": "learn about birds", "tier": "growth",
            "status": "in_progress", "_degraded": True}
    ctx: Dict[str, Any] = {"committed_goal": goal}
    result = gc._degrade_or_disengage(goal, ctx, goal["title"], reason="no progress")
    assert result and result["status"] == "disengaged"
    assert failed["called"] is True
    assert ctx["committed_goal"] is None        # slot released (existing behaviour)


# ── 2. satiety-with-return → dormant ───────────────────────────────────────────

def test_satisfied_survival_goal_goes_dormant(monkeypatch):
    # no-op the persistence so the test doesn't touch the store
    monkeypatch.setattr("brain.cognition.planning.goal_arbiter.apply", lambda *a, **k: None)
    goal = {"id": "s2", "title": "Restore: rest needed", "tier": "survival",
            "status": "in_progress"}
    ctx: Dict[str, Any] = {"committed_goal": goal}
    gc._finalize_goal_completion(goal, goal["title"], ctx, reason="satiety:restored")
    assert goal["status"] == "dormant"          # NOT 'completed'
    assert goal.get("_satisfied_ts")            # timestamp stamped for re-fire
    assert ctx["committed_goal"] is None         # slot released


def test_nonsurvival_completion_unaffected(monkeypatch):
    # A normal goal must still take the completion path, not the dormant one.
    # mark_goal_completed gates on the objective; a goal with no met milestones is
    # refused (hollow), so status stays in_progress — proving we did NOT go dormant.
    monkeypatch.setattr("brain.cognition.planning.goal_arbiter.apply", lambda *a, **k: None)
    goal = {"id": "g2", "title": "make a synthesis", "tier": "core",
            "status": "in_progress", "milestones": [{"text": "x", "met": False}]}
    ctx: Dict[str, Any] = {"committed_goal": goal}
    gc._finalize_goal_completion(goal, goal["title"], ctx, reason="satiety:done")
    assert goal["status"] != "dormant"


# ── 3. re-fire interval (hunger returns) ───────────────────────────────────────

def _alert():
    return {"id": "resource_deficit_critical", "severity": "critical",
            "description": "resource deficit critical — rest needed",
            "tags": ["resource_deficit"], "suggested_fn": "rest"}


def test_dormant_deficit_does_not_refire_within_interval(monkeypatch):
    recent_dormant = {"recruit_aid": "resource_deficit_critical", "status": "dormant",
                      "_satisfied_ts": time.time() - 60}  # 1 min ago, < 30 min
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [recent_dormant])
    ctx: Dict[str, Any] = {}
    assert sg.recruit_survival_goal(_alert(), ctx) is None
    assert ctx.get("proposed_goals", []) == []


def test_dormant_deficit_refires_after_interval(monkeypatch):
    old_dormant = {"recruit_aid": "resource_deficit_critical", "status": "dormant",
                   "_satisfied_ts": time.time() - (sg.MIN_REFIRE_INTERVAL_S + 60)}
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [old_dormant])
    ctx: Dict[str, Any] = {}
    g = sg.recruit_survival_goal(_alert(), ctx)
    assert g is not None and g["tier"] == "survival"   # hunger returned → re-recruited
