# AR8 (CODEBASE_AUDIT_2026-07-01 R2): resource_deficit ≈ 0.037 constant meant
# fatigue carried no behavioral signal and _allostatic_load never armed. These
# simulations drive the extracted _update_resource_deficit dynamics through a
# work/rest schedule and lock in the acceptance: fatigue RISES over a sustained
# working session, RECOVERS at rest, and the allostatic/exhaustion machinery is
# reachable (non-zero _allostatic_load under sustained load, with forced-low τ).

from brain.control_signals.update_signal_state import _update_resource_deficit


def _run(state, cycles, *, ms=None, mode=None):
    """Simulate `cycles` updates with a fixed workload; returns the trajectory."""
    traj = []
    for _ in range(cycles):
        ctx = {}
        if ms is not None:
            ctx["_cost_prediction"] = {"actual_ms": ms}
        if mode is not None:
            ctx["energy_mode"] = mode
        traj.append(_update_resource_deficit(ctx, state))
    return traj


def test_fatigue_rises_under_sustained_heavy_work():
    state = {"resource_deficit": 0.15}
    traj = _run(state, 200, ms=800)   # heavy measured cycles
    assert traj[-1] > 0.55, f"sustained heavy work must tire (got {traj[-1]})"
    assert traj[-1] > traj[0]


def test_fatigue_recovers_at_rest():
    state = {"resource_deficit": 0.65}
    traj = _run(state, 300, mode="rest")
    assert traj[-1] < 0.40, f"rest must restore (got {traj[-1]})"


def test_rise_and_recover_curve_not_flatline():
    # the acceptance shape: work → up, rest → down, and the band is wide
    state = {"resource_deficit": 0.15}
    up = _run(state, 200, ms=800)
    peak = max(up)
    down = _run(state, 300, mode="rest")
    trough = down[-1]
    assert peak - trough > 0.2, f"band too narrow: peak={peak} trough={trough}"


def test_allostatic_load_arms_under_sustained_load():
    state = {"resource_deficit": 0.15}
    _run(state, 400, ms=800)
    assert float(state.get("_allostatic_load", 0.0)) > 0.0, \
        "sustained load must accrue allostatic load (exhaustion reachable)"


def test_active_mode_fallback_can_arm_exhaustion():
    # audit R2 residual: the energy_mode fallback's old "active"=0.75 equilibrium
    # (~0.55) sat forever just below the 0.60 arming line
    state = {"resource_deficit": 0.15}
    traj = _run(state, 400, mode="active")
    assert traj[-1] > 0.60, f"sustained active mode must cross the arming line (got {traj[-1]})"
    assert float(state.get("_allostatic_load", 0.0)) > 0.0


def test_high_load_forces_recovery_tau():
    # run hot until load passes 0.5 → τ is forced low → deficit falls back even
    # under CONTINUED moderate work (mandatory-recovery, not optional rest)
    state = {"resource_deficit": 0.15}
    _run(state, 600, ms=800)
    load = float(state.get("_allostatic_load", 0.0))
    if load > 0.5:
        tau = float(state.get("_resource_setpoint", 1.0))
        assert tau <= 0.2, f"high load must force a low recovery target (τ={tau})"


def test_fatigue_never_pins_at_one():
    state = {"resource_deficit": 0.9}
    traj = _run(state, 200, ms=800)
    assert max(traj) < 1.0
