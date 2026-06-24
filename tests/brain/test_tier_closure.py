# Phase 4 of GOALS_MASTER_PLAN_2026-06-23 — enable core-goal satiety closure.
#
# Deliberate/core goals should close on the underlying need being SATED, not only
# on plan-completion. That pathway (_maybe_close_on_tier → satiety) was gated off
# by ORRIN_TIER_CLOSURE; Phase 4 flips the default ON. These tests pin the flag
# default and the gating behaviour (closes when sated, holds when not, still
# disablable).
import brain.cognition.planning.goal_closure as gc


def _core_goal():
    return {"id": "c1", "title": "make a synthesis of birds", "tier": "core",
            "status": "in_progress",
            "milestones": [{"text": "a synthesis was produced", "met": False}]}


def test_tier_closure_default_is_on(monkeypatch):
    monkeypatch.delenv("ORRIN_TIER_CLOSURE", raising=False)
    assert gc._tier_closure_enabled() is True


def test_tier_closure_still_disablable(monkeypatch):
    monkeypatch.setenv("ORRIN_TIER_CLOSURE", "0")
    assert gc._tier_closure_enabled() is False
    # and with it off, _maybe_close_on_tier is a no-op regardless of satiety
    assert gc._maybe_close_on_tier(_core_goal(), "t", "step", 2, {}) is None


def test_sated_core_goal_closes_when_enabled(monkeypatch):
    monkeypatch.delenv("ORRIN_TIER_CLOSURE", raising=False)   # default on
    monkeypatch.setattr("brain.cognition.planning.env_snapshot.apply_milestone_updates",
                        lambda *a, **k: None)
    monkeypatch.setattr("brain.cognition.planning.goal_satiety.is_sated",
                        lambda g, c: (True, "info-gap closed"))

    def _fake_finalize(goal, title, context, reason=""):
        goal["status"] = "completed"           # stand in for the real close

    monkeypatch.setattr(gc, "_finalize_goal_completion", _fake_finalize)
    goal = _core_goal()
    result = gc._maybe_close_on_tier(goal, goal["title"], "next", remaining=2, context={})
    assert result is not None and result.get("closed") is True
    assert "satiety:" in result["reason"]


def test_unsated_core_goal_stays_open_when_enabled(monkeypatch):
    monkeypatch.delenv("ORRIN_TIER_CLOSURE", raising=False)   # default on
    monkeypatch.setattr("brain.cognition.planning.env_snapshot.apply_milestone_updates",
                        lambda *a, **k: None)
    monkeypatch.setattr("brain.cognition.planning.goal_satiety.is_sated",
                        lambda g, c: (False, ""))
    assert gc._maybe_close_on_tier(_core_goal(), "t", "next", 2, {}) is None
