# Tests for the AffectArbiter convergence layer (affect/arbiter.py).
from brain.control_signals.arbiter import submit_signal, commit_signals, STABILITY_BUDGET
from brain.control_signals.signal_buffer import drain_signal_queue
from brain.control_signals.setpoints import setpoint


def _ctx(**core):
    return {"affect_state": {"core_signals": dict(core)}}


def test_no_proposals_is_noop():
    ctx = _ctx(uncertainty=0.1)
    assert commit_signals(ctx) == {}
    assert "_emotion_queue" not in ctx["affect_state"]


def test_contradictory_deltas_net_out():
    ctx = _ctx(uncertainty=0.1)
    submit_signal(ctx, "uncertainty", +0.20, source="a")
    submit_signal(ctx, "uncertainty", -0.05, source="b")
    applied = commit_signals(ctx)
    # +0.20 and -0.05 net to +0.15 (weights default 1.0)
    assert abs(applied["uncertainty"] - 0.15) < 1e-6


def test_weight_scales_contribution():
    ctx = _ctx(motivation=0.5)
    submit_signal(ctx, "motivation", +0.10, weight=2.0, source="strong")
    submit_signal(ctx, "motivation", -0.10, weight=1.0, source="weak")
    applied = commit_signals(ctx)
    # 0.10*2 - 0.10*1 = +0.10
    assert abs(applied["motivation"] - 0.10) < 1e-6


def test_proposals_cleared_after_commit():
    ctx = _ctx(uncertainty=0.1)
    submit_signal(ctx, "uncertainty", 0.1, source="a")
    commit_signals(ctx)
    assert ctx.get("_affect_proposals") == []


def test_stability_budget_caps_runaway_cycle():
    # A flood of same-direction proposals must be scaled down to the budget.
    ctx = _ctx(threat_level=0.0)
    for _ in range(20):
        submit_signal(ctx, "threat_level", +0.10, source="flood")
    applied = commit_signals(ctx)
    # threat_level rests at 0.0; pushing up is "away from setpoint" → double cost.
    # raw net = 2.0, weighted cost = 4.0, scale = BUDGET/4.0 → applied = 2.0*scale.
    expected = 2.0 * (STABILITY_BUDGET / 4.0)
    assert abs(applied["threat_level"] - round(expected, 4)) < 1e-3
    assert applied["threat_level"] < 2.0  # definitely capped


def test_toward_setpoint_is_cheaper_than_away():
    # Same magnitude delta: moving toward setpoint should survive the budget more
    # readily than moving away. We verify the away-cost doubling via two ctxs.
    away = _ctx(threat_level=0.0)   # 0.0 == setpoint, +delta moves away
    toward = _ctx(threat_level=1.0) # 1.0 above setpoint(0.0), -delta moves toward
    for _ in range(20):
        submit_signal(away, "threat_level", +0.10, source="x")
        submit_signal(toward, "threat_level", -0.10, source="x")
    a = commit_signals(away)["threat_level"]
    t = commit_signals(toward)["threat_level"]
    # toward-setpoint correction is allowed to be ~2x larger in magnitude
    assert abs(t) > abs(a)


def test_committed_deltas_drain_through_buffer():
    ctx = _ctx(uncertainty=0.1)
    submit_signal(ctx, "uncertainty", +0.15, source="a")
    commit_signals(ctx)
    state = ctx["affect_state"]
    core = state["core_signals"]
    before = core["uncertainty"]
    # Drain the whole buffer; uncertainty should rise toward +0.15 total.
    for _ in range(6):
        drain_signal_queue(state, core)
    assert core["uncertainty"] > before


def test_setpoints_have_expected_resting_values():
    assert setpoint("threat_level") == 0.0
    assert setpoint("motivation") == 0.5
    assert setpoint("unknown_signal_xyz") == 0.0
