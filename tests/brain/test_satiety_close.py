"""T2.2 — satiety-based tier-closure independent of the milestone gate
(brain/cognition/planning/goal_outcomes.mark_goal_completed).

A directional growth/core goal whose underlying need is SATED should close even
with unmet milestones (the run blocked this — "satiety-close blocked by objective
not met"). But an artifact/production goal must still produce its artifact, and a
satiety close must not fire the +1.0 production reward (no farming).
"""
import pytest

import brain.cognition.planning.goal_outcomes as go


@pytest.fixture
def _isolate(monkeypatch):
    """Neutralise mark_goal_completed's heavy tail so the milestone-gate decision
    can be asserted without touching real data files."""
    rewards = []
    monkeypatch.setattr(go, "load_json", lambda *a, **k: [])
    monkeypatch.setattr(go, "save_json", lambda *a, **k: None)
    monkeypatch.setattr(go, "load_goals", lambda *a, **k: [])
    monkeypatch.setattr(go, "save_goals", lambda *a, **k: None)
    monkeypatch.setattr(go, "update_working_memory", lambda *a, **k: None)
    monkeypatch.setattr(go, "_revise_weak_area_beliefs", lambda *a, **k: None)
    monkeypatch.setattr(go, "release_reward_signal",
                        lambda **k: rewards.append(k))
    monkeypatch.setattr("brain.cognition.intrinsic_goals.generate_intrinsic_goals",
                        lambda *a, **k: [])
    return rewards


def _growth_goal():
    return {"id": "g1", "title": "understand birds more deeply", "tier": "core",
            "status": "in_progress",
            "milestones": [{"text": "a synthesis exists", "met": False}]}


def _artifact_goal():
    return {"id": "a1", "title": "write a synthesis", "tier": "core",
            "status": "in_progress", "requires_artifact": True,
            "spec": {"requires_artifact": True},
            "milestones": [{"text": "the doc exists", "met": False}]}


def test_satiety_closes_non_artifact_goal_with_unmet_milestones(_isolate):
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] == "completed"


def test_satiety_does_not_close_artifact_goal(_isolate):
    """Production is still gated: an artifact goal can't satiety-close hollow."""
    goal = _artifact_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] != "completed"


def test_satiety_close_pays_no_production_reward(_isolate):
    rewards = _isolate
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    # No grounding (no milestones met / no artifact) → no +1.0 production reward.
    assert not any(r.get("signal_type") == "reward_signal" for r in rewards)


def test_satiety_close_relaxes_spawning_drive(_isolate):
    """The need being sated IS evidence — the affect loop relaxes the drive."""
    goal = _growth_goal()
    goal["driven_by"] = "world_knowledge"
    ctx = {"affect_state": {"core_signals": {"exploration_drive": 0.8}}}
    go.mark_goal_completed(goal, context=ctx, satiety_close=True)
    assert goal.get("satisfied_need") == "exploration_drive"
    props = ctx.get("_affect_proposals") or []
    assert any(p["target"] == "exploration_drive" and p["delta"] < 0 for p in props)


def test_normal_close_still_refuses_unmet_milestones(_isolate):
    """Without satiety_close, the hollow-completion guard is unchanged."""
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}})
    assert goal["status"] != "completed"
