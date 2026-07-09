# Run-5 meter bugs (RUN6_FIX_PLAN_2026-07-08 §4): the §8 gate can't be trusted
# while its meters lie. S3 read 0 satiety closures in Run 5 while 7 real
# satiety closes happened (the pursuit-path close never told outcome_metrics),
# and 91 % of habituation.json survived the "clean" reset (it sat in SOFT_KEEP).
import brain.cognition.planning.goal_closure as gc
import brain.cognition.planning.goal_satiety as gs
import brain.cognition.planning.outcome_metrics as om

import reset_orrin


def test_satiety_close_records_outcome_metric(monkeypatch):
    """The pursuit-path satiety close (goal_closure._maybe_close_on_tier) must
    increment outcome_metrics.satiety_closures — S3's source of truth."""
    monkeypatch.setattr(gs, "is_sated", lambda goal, context: (True, "novelty exhausted"))
    monkeypatch.setattr(
        gc, "_finalize_goal_completion",
        lambda goal, title, context, reason="": goal.__setitem__("status", "completed"),
    )
    before = int(om._session.get("satiety_closures", 0))
    goal = {"id": "g-sat", "title": "understand emergence", "tier": "growth",
            "status": "in_progress", "milestones": [{"text": "x", "met": True}]}
    out = gc._maybe_close_on_tier(goal, "understand emergence", "next step", 1, {})
    assert out is not None and out.get("closed")
    assert int(om._session.get("satiety_closures", 0)) == before + 1


def test_blocked_satiety_close_records_nothing(monkeypatch):
    """A hollow close (mark_goal_completed refused) must not bump the counter."""
    monkeypatch.setattr(gs, "is_sated", lambda goal, context: (True, "novelty exhausted"))
    monkeypatch.setattr(gc, "_finalize_goal_completion",
                        lambda goal, title, context, reason="": None)   # close blocked
    before = int(om._session.get("satiety_closures", 0))
    goal = {"id": "g-sat2", "title": "understand emergence", "tier": "growth",
            "status": "in_progress", "milestones": [{"text": "x", "met": True}]}
    assert gc._maybe_close_on_tier(goal, "understand emergence", "next step", 1, {}) is None
    assert int(om._session.get("satiety_closures", 0)) == before


def test_reset_clears_habituation():
    """habituation.json is per-life satiety state, not learning — a plain reset
    must clear it (91 % survived the Run-5 'clean' reset from SOFT_KEEP)."""
    assert "habituation.json" not in reset_orrin.SOFT_KEEP
    assert "habituation.json" not in reset_orrin.ALWAYS_KEEP
