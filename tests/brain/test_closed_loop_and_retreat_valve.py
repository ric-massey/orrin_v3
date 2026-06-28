"""R2 + R3 from SIGNAL_TO_ACTION_AUDIT_2026-06-18.md:

  B / R2 — break a "closed loop running open" (survival preempt holding while a
           corrective is armed) → goal_closure._closed_loop_break.
  A / R3 — the threat-retreat release valve actually discharges the electing
           signal → consolidation_cycle._submit_retreat_discharge.
"""
import os
import time

import brain.cognition.planning.goal_closure as gc
import brain.cognition.idle_consolidation.consolidation_cycle as cc


# ── B / R2 — closed-loop break ──────────────────────────────────────────────

def test_break_does_not_fire_without_armed_corrective():
    ctx = {}
    # No _force_action_next → never a closed loop, streak stays cleared.
    for _ in range(gc._PREEMPT_OPEN_THRESHOLD + 5):
        assert gc._closed_loop_break(ctx, "resource_deficit>0.85") is False
    assert ctx.get("_preempt_open_streak", 0) == 0


def test_break_fires_after_threshold_when_armed():
    ctx = {"_force_action_next": True}
    # The window-1 cycles before the threshold must keep yielding (return False)…
    for i in range(gc._PREEMPT_OPEN_THRESHOLD - 1):
        assert gc._closed_loop_break(ctx, "resource_deficit>0.85") is False
        assert ctx["_preempt_open_streak"] == i + 1
    # …and the Nth fires the break, resets the streak, and arms a cooldown.
    assert gc._closed_loop_break(ctx, "resource_deficit>0.85") is True
    assert ctx["_preempt_open_streak"] == 0
    assert ctx["_preempt_break_cooldown_until"] > time.time()


def test_break_respects_cooldown():
    ctx = {"_force_action_next": True}
    for _ in range(gc._PREEMPT_OPEN_THRESHOLD):
        gc._closed_loop_break(ctx, "x")
    # Immediately after a break we are in cooldown: even armed + many cycles, no break.
    for _ in range(gc._PREEMPT_OPEN_THRESHOLD + 2):
        assert gc._closed_loop_break(ctx, "x") is False
    # Once the cooldown lapses it can break again.
    ctx["_preempt_break_cooldown_until"] = time.time() - 1
    for _ in range(gc._PREEMPT_OPEN_THRESHOLD - 1):
        assert gc._closed_loop_break(ctx, "x") is False
    assert gc._closed_loop_break(ctx, "x") is True


def test_break_can_be_disabled_by_flag():
    ctx = {"_force_action_next": True}
    os.environ["ORRIN_CLOSED_LOOP_BREAK"] = "0"
    try:
        for _ in range(gc._PREEMPT_OPEN_THRESHOLD + 3):
            assert gc._closed_loop_break(ctx, "x") is False
    finally:
        os.environ.pop("ORRIN_CLOSED_LOOP_BREAK", None)


# ── A / R3 — retreat valve discharge ────────────────────────────────────────

def _patch_state(monkeypatch, core_signals):
    """Make the discharge read a controlled signal-state and capture arbiter calls."""
    calls = []
    monkeypatch.setattr(
        "brain.utils.json_utils.load_json",
        lambda *a, **k: {"core_signals": core_signals},
    )
    monkeypatch.setattr(
        "brain.control_signals.arbiter.submit_signal",
        lambda ctx, target, delta, **k: calls.append((target, delta, k.get("source"))),
    )
    return calls


def test_retreat_discharges_elevated_impasse(monkeypatch):
    calls = _patch_state(monkeypatch, {"impasse_signal": 0.64, "threat_level": 0.01})
    out = cc._submit_retreat_discharge()
    # Only the elevated signal is discharged, with a negative (relieving) delta.
    assert "impasse_signal" in out and out["impasse_signal"] < 0
    assert "threat_level" not in out
    assert calls and calls[0][0] == "impasse_signal" and calls[0][2] == "dream_retreat_discharge"


def test_retreat_discharge_is_bounded_and_proportional(monkeypatch):
    _patch_state(monkeypatch, {"threat_level": 1.0, "impasse_signal": 0.5})
    out = cc._submit_retreat_discharge()
    # Cap at 0.18 magnitude even at max threat; proportional (0.30*val) below the cap.
    assert out["threat_level"] == -0.18
    assert out["impasse_signal"] == round(-0.30 * 0.5, 3)


def test_retreat_noop_when_calm(monkeypatch):
    calls = _patch_state(monkeypatch, {"threat_level": 0.1, "impasse_signal": 0.2})
    out = cc._submit_retreat_discharge()
    assert out == {} and calls == []
