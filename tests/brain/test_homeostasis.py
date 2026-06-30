# HomeostasisManager: single decay law + net velocity budget (V3 D3/D8).
from brain.control_signals.homeostasis import (
    apply_restoring_forces, apply_cross_inhibition, enforce_velocity_budget,
    DEFAULT_MAX_L1,
)
from brain.control_signals.setpoints import setpoint, SETPOINTS, CORE_BASELINES
from brain.control_signals.signals import get_all_signal_names


def test_decay_pulls_toward_baseline_not_half():
    # reward_positive rests at its CORE_BASELINE (0.10), never 0.5.
    state = {"emotional_decay": True}
    core = {"reward_positive": 0.9}
    # large hours_passed → strong approach to baseline
    apply_restoring_forces(state, core, decay_rate=0.5, hours_passed=24.0)
    assert core["reward_positive"] < 0.9
    assert core["reward_positive"] >= CORE_BASELINES["reward_positive"] - 1e-6


def test_decay_respects_emotional_decay_flag():
    state = {"emotional_decay": False}
    core = {"reward_positive": 0.9}
    apply_restoring_forces(state, core, decay_rate=0.5, hours_passed=24.0)
    assert core["reward_positive"] == 0.9  # untouched when decay disabled


def test_cross_inhibition_pulls_antagonist_down():
    core = {"impasse_signal": 0.95, "confidence": 0.9}
    apply_cross_inhibition(core)
    assert core["confidence"] < 0.9  # antagonist pulled toward baseline


def test_velocity_budget_caps_large_net_move():
    prev = {"a": 0.0, "b": 0.0, "c": 0.0}
    core = {"a": 1.0, "b": 1.0, "c": 1.0}  # total L1 = 3.0 >> budget
    moved = enforce_velocity_budget(core, prev, max_l1=1.0)
    assert abs(moved - 3.0) < 1e-9
    new_total = sum(abs(core[k] - prev[k]) for k in core)
    assert abs(new_total - 1.0) < 1e-6  # scaled down to the cap


def test_velocity_budget_passes_small_move_untouched():
    prev = {"a": 0.5}
    core = {"a": 0.55}
    enforce_velocity_budget(core, prev, max_l1=DEFAULT_MAX_L1)
    assert abs(core["a"] - 0.55) < 1e-9  # under budget → unchanged


def test_setpoint_resolution_order():
    # SETPOINTS override wins; otherwise CORE_BASELINES; otherwise 0.0
    assert setpoint("motivation") == 0.5         # in SETPOINTS
    assert setpoint("reflective") == 0.35        # only in CORE_BASELINES
    assert setpoint("totally_unknown_xyz") == 0.0


# ── Phase 1B Task 1: the by-construction registration guarantee ──────────────
# Every signal in the affect model must declare a baseline EXPLICITLY (not the
# silent 0.0 fallback) and be subject to the restoring force, so no signal runs
# OPEN-LOOP — runaway is impossible everywhere, including loops not yet found
# (Grounded Cognition plan, invariant #1).

def test_every_signal_has_an_explicit_setpoint():
    """No signal may rely on the implicit 0.0 default — a missing baseline is an
    accident, not a chosen resting value. This guards against a new signal being
    added to the model without declaring where it rests."""
    explicit = set(SETPOINTS) | set(CORE_BASELINES)
    missing = [n for n in get_all_signal_names() if n not in explicit]
    assert not missing, f"signals running open-loop (no declared baseline): {missing}"


def test_restoring_force_acts_on_every_signal():
    """The single decay law must move EVERY model signal toward its baseline —
    proving the restoring force is universal, not selectively wired."""
    names = get_all_signal_names()
    # Start each signal off its baseline; decay must pull it back toward setpoint.
    core = {n: min(1.0, setpoint(n) + 0.5) for n in names}
    before = dict(core)
    apply_restoring_forces({"emotional_decay": True}, core,
                           decay_rate=0.5, hours_passed=24.0)
    for n in names:
        sp = setpoint(n)
        # each signal moved strictly toward (or already at) its baseline
        assert abs(core[n] - sp) <= abs(before[n] - sp) + 1e-9, (
            f"{n}: decay did not move it toward baseline {sp}")


# ── Phase 1B Task 2: allostasis-by-equilibrium (invariant #1's correction) ────
# The plan's key correction: do NOT force every signal to baseline. Distinguish
# habituation to REPETITION (good — damp a repeated thought) from decay of a
# genuinely STANDING condition (bad to force). The architecture achieves this
# WITHOUT a value-tracking setpoint (which would re-introduce the positive-feedback
# saturation the session just fixed): a standing condition is continuously
# re-driven by fresh appraisal, so drive-vs-decay settles at an elevated
# EQUILIBRIUM (the emergent allostatic setpoint); a one-off spike with no re-drive
# decays to baseline. Explicit setpoint-shifting is reserved for resource_deficit
# (cost_prediction.allostatic_setpoint), where mandatory recovery is required and
# the load integrator bounds the runaway — it is deliberately NOT generalised to
# affect signals.

def test_standing_pressure_holds_signal_elevated_but_spike_decays():
    """A continuously re-driven standing condition settles above baseline; a
    transient spike with no re-drive decays back to baseline. This is the
    allostatic distinction, emergent from drive-vs-decay equilibrium."""
    sp = setpoint("impasse_signal")

    # Standing condition: a genuine problem re-drives the signal each cycle.
    core = {"impasse_signal": sp}
    for _ in range(50):
        core["impasse_signal"] = min(1.0, core["impasse_signal"] + 0.15)  # fresh pressure
        apply_restoring_forces({"emotional_decay": True}, core,
                               decay_rate=0.3, hours_passed=1.0)
    standing = core["impasse_signal"]
    assert standing > sp + 0.20, "a standing condition must stay genuinely elevated"

    # Transient: the same elevation, but no re-drive — must decay back to baseline.
    core2 = {"impasse_signal": standing}
    for _ in range(50):
        apply_restoring_forces({"emotional_decay": True}, core2,
                               decay_rate=0.3, hours_passed=1.0)
    assert abs(core2["impasse_signal"] - sp) < 0.06, "a transient spike must decay to baseline"
