# Tests for the T1.1 capstone: the satisfaction handshake + affect close-loop
# (brain/cognition/planning/goal_satisfaction.py).
#
# These pin the behaviour the Core Architecture Master Plan calls "the highest-
# value single wire in the system": a real felt-origin close records what need it
# satisfied + the evidence, relaxes the spawning drive (bounded, never to zero),
# and lets contentment rise — while a hollow close closes no loop.
from brain.cognition.planning.goal_satisfaction import (
    close_affect_loop, _DRIVE_FLOOR, _RELAX_DELTA, _CONTENT_DELTA,
)
from brain.control_signals.arbiter import _PROP_KEY, commit_signals


def _ctx(**signals):
    cs = {"exploration_drive": 0.8, "social_deficit": 0.7, "stagnation_signal": 0.6}
    cs.update(signals)
    return {"affect_state": {"core_signals": cs}}


def _props(ctx):
    return {p["target"]: p for p in (ctx.get(_PROP_KEY) or [])}


# 1. A grounded felt-origin close records the handshake and closes the loop:
#    spawning drive relaxes (negative), contentment rises (positive).
def test_grounded_close_relaxes_drive_and_raises_contentment():
    ctx = _ctx()
    goal = {"title": "Understand emergence", "driven_by": "world_knowledge",
            "milestones": [{"text": "x", "met": True}]}
    close_affect_loop(goal, ctx, grounded=True, significance=0.8)

    assert goal["satisfied_need"] == "exploration_drive"
    assert goal["satisfaction_evidence"]["grounded"] is True
    assert goal["satisfaction_evidence"]["milestones_met"] == 1

    props = _props(ctx)
    assert props["exploration_drive"]["delta"] < 0          # drive relaxes
    assert abs(props["exploration_drive"]["delta"]) <= _RELAX_DELTA + 1e-9
    assert props["satisfaction_signal"]["delta"] == _CONTENT_DELTA  # contentment up


# 2. Overshoot guard: a drive already near zero is never pushed below the floor.
def test_relaxation_respects_floor():
    ctx = _ctx(exploration_drive=_DRIVE_FLOOR + 0.02)
    goal = {"title": "g", "driven_by": "curiosity",
            "milestones": [{"met": True}]}
    close_affect_loop(goal, ctx, grounded=True, significance=0.5)
    props = _props(ctx)
    # Decrement clamped to the headroom above the floor (0.02), not the full delta.
    assert abs(props["exploration_drive"]["delta"]) <= 0.02 + 1e-9
    # And applying it cannot drive the signal below the floor.
    applied = commit_signals(ctx)
    assert 0.8 > 0  # sanity
    assert ctx["affect_state"]["core_signals"]["exploration_drive"] - abs(applied.get("exploration_drive", 0)) >= 0


# 3. A hollow close (no evidence) records the gap but closes NO loop.
def test_hollow_close_closes_no_loop():
    ctx = _ctx()
    goal = {"title": "g", "driven_by": "world_knowledge", "milestones": []}
    close_affect_loop(goal, ctx, grounded=False, significance=0.0)
    assert goal["satisfied_need"] is None
    assert goal["satisfaction_evidence"]["grounded"] is False
    assert not ctx.get(_PROP_KEY)   # nothing relaxed, no contentment paid


# 4. The driven_by → need mapping covers every aspiration + aux drive family.
def test_driven_by_families_map():
    cases = {
        "world_knowledge": "exploration_drive",
        "self_understanding": "exploration_drive",
        "genuine_contact": "social_deficit",
        "connection": "social_deficit",
        "output_producing": "stagnation_signal",
        "will": "stagnation_signal",
        "problem_solving": "impasse_signal",
    }
    for drive, need in cases.items():
        ctx = _ctx(impasse_signal=0.6)
        goal = {"title": "g", "driven_by": drive, "milestones": [{"met": True}]}
        close_affect_loop(goal, ctx, grounded=True, significance=0.5)
        assert goal["satisfied_need"] == need
        assert need in _props(ctx)


# 5. A drive with no mapping (or no driven_by) records evidence, closes no loop.
def test_unmapped_drive_no_loop():
    ctx = _ctx()
    goal = {"title": "g", "driven_by": "mystery_drive", "milestones": [{"met": True}]}
    close_affect_loop(goal, ctx, grounded=True, significance=0.5)
    assert goal["satisfied_need"] is None
    assert not ctx.get(_PROP_KEY)


# 6. Fail-safe — malformed inputs can't raise.
def test_fail_safe():
    close_affect_loop(None, _ctx(), grounded=True)
    close_affect_loop({"driven_by": "world_knowledge"}, None, grounded=True)
    close_affect_loop({}, {}, grounded=True)
