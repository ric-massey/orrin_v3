"""Phase B cluster 7 — B12 / CT-A clock time instead of cycle time.

The observable (CONTINUOUS_TIME_DESIGN §2 A.2): the same scenario at cadence
×0.5 and ×2 produces the same curve in seconds.
"""
from __future__ import annotations

import random

import pytest

from brain.utils import clock


def test_tick_measures_seconds_and_caps_stalls():
    assert clock.tick(mono=1000.0) == clock.MEAN_CYCLE_S     # first tick of a process
    ctx: dict = {}
    assert clock.tick(ctx, mono=1002.5) == pytest.approx(2.5)
    assert ctx["_dt_s"] == pytest.approx(2.5)
    assert clock.tick(mono=5000.0) == clock._MAX_DT_S        # a stall is not one giant step


def _affect_curve(cadence_s: float, horizon_s: float = 16.0):
    from brain.control_signals.signal_buffer import drain_signal_queue, queue_signal_change
    random.seed(0)                       # same TTL jitter in both runs
    state: dict = {}
    core = {"motivation": 0.2}
    queue_signal_change(state, "motivation", 0.3, ttl_cycles=3)
    curve, t = {}, 0.0
    while t < horizon_s - 1e-9:
        drain_signal_queue(state, core, dt=cadence_s)
        t += cadence_s
        curve[round(t, 3)] = core["motivation"]
    return curve


def test_affect_drain_is_cadence_invariant():
    slow, fast = _affect_curve(8.0), _affect_curve(2.0)
    for t in (8.0, 16.0):
        assert fast[t] == pytest.approx(slow[t], abs=1e-9)
    assert slow[16.0] == pytest.approx(0.5)      # the whole delta lands, once


def test_staleness_accrues_by_time_not_pulls(monkeypatch):
    from brain.cognition.planning import commitment_value as cv

    def held_for(seconds: float, cadence_s: float) -> float:
        monkeypatch.setattr(clock, "last_dt", lambda: cadence_s)
        total = 0.0
        for _ in range(int(round(seconds / cadence_s))):
            total += cv._stale_step()
        return total

    assert held_for(400.0, 2.0) == pytest.approx(held_for(400.0, 8.0))
    assert held_for(400.0, clock.MEAN_CYCLE_S) == pytest.approx(100.0)   # unchanged at 4 s


def test_decay_half_life_is_in_seconds():
    assert clock.decay(1.0, 60.0, 60.0) == pytest.approx(0.5)
    two_steps = clock.decay(clock.decay(1.0, 30.0, 60.0), 30.0, 60.0)
    assert two_steps == pytest.approx(clock.decay(1.0, 60.0, 60.0))
