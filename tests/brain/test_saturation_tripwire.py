# R10-9: a control signal welded to a hard bound (0.0/1.0) for hundreds of
# cycles is an attractor the normal restoring law failed to break. The tripwire
# must force-recalibrate it off the bound and re-arm — so no signal stays flat
# at a bound for > SATURATION_MAX_CYCLES (Run 9: drive_mastery == 1.00 all life).

from brain.control_signals import homeostasis as H


def test_pinned_signal_is_recalibrated_after_the_window():
    state = {}
    signals = {"drive_mastery": 1.0}
    fired_any = False
    for c in range(H.SATURATION_MAX_CYCLES + 1):
        fired = H.saturation_tripwire(state, signals, cycle=c)
        if fired:
            fired_any = True
            break
    assert fired_any, "a signal at 1.0 past the window must trip"
    assert signals["drive_mastery"] < 1.0 - H._SATURATION_EPS, "must leave the bound"
    # Streak re-armed to 0 so it doesn't trip again next cycle.
    assert state[H._SAT_STREAK_KEY]["drive_mastery"] == 0


def test_lower_bound_also_trips():
    state = {}
    signals = {"confidence": 0.0}
    fired_at = None
    for c in range(H.SATURATION_MAX_CYCLES + 1):
        if H.saturation_tripwire(state, signals, cycle=c):
            fired_at = c
            break
    assert fired_at == H.SATURATION_MAX_CYCLES - 1, "trips on the Nth call at the bound"
    assert signals["confidence"] > H._SATURATION_EPS


def test_signal_resting_at_its_setpoint_bound_never_trips():
    # loss_signal's healthy setpoint is 0.0 — sitting at 0.0 forever is correct
    # rest, NOT saturation. The tripwire must not manufacture fake affect by
    # kicking it off the bound. (drive_mastery at 1.0 with setpoint 0.0 still trips
    # — covered by test_pinned_signal_is_recalibrated_after_the_window.)
    state = {}
    signals = {"loss_signal": 0.0}
    for c in range(H.SATURATION_MAX_CYCLES + 50):
        assert H.saturation_tripwire(state, signals, cycle=c) == []
    assert signals["loss_signal"] == 0.0, "a healthy-zero signal must be left at rest"


def test_healthy_signal_never_trips_and_clears_streak():
    state = {}
    signals = {"motivation": 1.0}
    # Sit at the bound briefly, then relax below it — streak must clear.
    for c in range(10):
        H.saturation_tripwire(state, signals, cycle=c)
    assert state[H._SAT_STREAK_KEY].get("motivation", 0) > 0
    signals["motivation"] = 0.6
    H.saturation_tripwire(state, signals, cycle=11)
    assert "motivation" not in state[H._SAT_STREAK_KEY]
    # And a signal that never pins never trips over a long horizon.
    for c in range(H.SATURATION_MAX_CYCLES + 50):
        signals["motivation"] = 0.55
        assert H.saturation_tripwire(state, signals, cycle=c) == []
