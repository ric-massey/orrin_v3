# HomeostasisManager: single decay law + net velocity budget (V3 D3/D8).
from brain.affect.homeostasis import (
    apply_restoring_forces, apply_cross_inhibition, enforce_velocity_budget,
    DEFAULT_MAX_L1,
)
from brain.affect.setpoints import setpoint, CORE_BASELINES


def test_decay_pulls_toward_baseline_not_half():
    # positive_valence rests at its CORE_BASELINE (0.10), never 0.5.
    state = {"emotional_decay": True}
    core = {"positive_valence": 0.9}
    # large hours_passed → strong approach to baseline
    apply_restoring_forces(state, core, decay_rate=0.5, hours_passed=24.0)
    assert core["positive_valence"] < 0.9
    assert core["positive_valence"] >= CORE_BASELINES["positive_valence"] - 1e-6


def test_decay_respects_emotional_decay_flag():
    state = {"emotional_decay": False}
    core = {"positive_valence": 0.9}
    apply_restoring_forces(state, core, decay_rate=0.5, hours_passed=24.0)
    assert core["positive_valence"] == 0.9  # untouched when decay disabled


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
