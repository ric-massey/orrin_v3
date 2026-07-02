"""T2.2 — satiety-based tier-closure independent of the milestone gate
(brain/cognition/planning/goal_outcomes.mark_goal_completed).

A directional growth/core goal whose underlying need is SATED should close even
with unmet milestones (the run blocked this — "satiety-close blocked by objective
not met"). But an artifact/production goal must still produce its artifact, and a
satiety close must not fire the +1.0 production reward (no farming).

P1 (B2/C2 — effect-gated closure): the satiety bypass ALSO requires a durable,
novel EFFECT on the ledger for a non-artifact goal. "The drive quenched" is no
longer "I made something" — a goal that only ever read (recorded nothing) can no
longer satiety-close. The legacy satiety-only close is recoverable for A/B
ablation via ORRIN_REQUIRE_EFFECT_FOR_CLOSURE=0. Milestone completion remains an
independent, un-gated close path.
"""
import pytest

import brain.cognition.planning.goal_outcomes as go


@pytest.fixture
def _isolate(monkeypatch):
    """Neutralise mark_goal_completed's heavy tail so the milestone-gate decision
    can be asserted without touching real data files. Effect presence and milestone
    refresh are made deterministic here; individual tests override has_qualifying_effect."""
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
    # Milestone refresh reads the environment; neutralise so milestone state is
    # fully controlled by each test's goal dict (both the P1 pre-refusal refresh
    # and the legacy milestone-gate refresh resolve this same name at call time).
    monkeypatch.setattr("brain.cognition.planning.env_snapshot.apply_milestone_updates",
                        lambda *a, **k: None)
    # P1 default: no qualifying effect on the ledger unless a test says otherwise.
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: False)
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


def test_satiety_refused_without_effect(_isolate, monkeypatch):
    """P1: a non-artifact growth goal that recorded no effect can no longer
    satiety-close hollow — the drive being sated is not producing something. It
    stays open (to be re-aimed or disengaged by the watchdog), not marked done."""
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: False)
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] != "completed"


def test_satiety_closes_non_artifact_goal_with_effect(_isolate, monkeypatch):
    """With a durable, novel effect on the ledger, a directional growth goal may
    satiety-close even with unmet milestones — the need is met AND it produced."""
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: True)
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] == "completed"


def test_satiety_closes_when_all_milestones_met_without_effect(_isolate, monkeypatch):
    """Milestone completion is an independent, un-gated close path: all milestones
    met closes even with no ledger effect and satiety_close set."""
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: False)
    goal = _growth_goal()
    goal["milestones"] = [{"text": "a synthesis exists", "met": True}]
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] == "completed"


def test_ablation_flag_restores_legacy_satiety_close(_isolate, monkeypatch):
    """ORRIN_REQUIRE_EFFECT_FOR_CLOSURE=0 restores the legacy satiety-only close
    (no effect required) for A/B ablation."""
    monkeypatch.setenv("ORRIN_REQUIRE_EFFECT_FOR_CLOSURE", "0")
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: False)
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] == "completed"


def test_satiety_does_not_close_artifact_goal(_isolate, monkeypatch):
    """Production is still gated: an artifact goal can't satiety-close hollow,
    even with a ledger effect present (artifact gate is _is_artifact_gated)."""
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: True)
    goal = _artifact_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] != "completed"


def test_satiety_close_pays_no_production_reward(_isolate, monkeypatch):
    """A satiety close (effect present so it closes) fires no +1.0 production
    reward when nothing was grounded this cycle — satiety is not a reward farm."""
    rewards = _isolate
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: True)
    goal = _growth_goal()
    go.mark_goal_completed(goal, context={"affect_state": {"core_signals": {}}},
                           satiety_close=True)
    assert goal["status"] == "completed"
    # No grounding (no milestones met / no artifact / no cycle action) → no reward.
    assert not any(r.get("signal_type") == "reward_signal" for r in rewards)


def test_satiety_close_relaxes_spawning_drive(_isolate, monkeypatch):
    """The need being sated IS evidence — the affect loop relaxes the drive."""
    monkeypatch.setattr(go, "has_qualifying_effect", lambda *a, **k: True)
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
