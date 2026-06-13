# Finding 1 (decompose run_cognitive_loop into stage(context) -> context
# functions): _apply_transient_signal_decay is the first extracted stage —
# it decays short-lived affect signals and tracks the sustained-crisis
# counter (_extreme_cycles) that the emergency_self_modification gate reads.
# Importing ORRIN_loop is slow (~5s, pulls in the whole cognition stack) but
# does not register signal handlers or start threads at module scope, so it
# is safe to import directly here.
import pytest

import ORRIN_loop as loop
from config.tuning import (
    AFFECT_TRANSIENT_DECAY,
    CRISIS_ABOVE_HALF_COUNT,
    CRISIS_ABOVE_HALF_THRESHOLD,
    CRISIS_ACUTE_PEAK,
    CRISIS_CHRONIC_MEAN,
)


def test_returns_same_context_object():
    context = {"affect_state": {}}
    result = loop._apply_transient_signal_decay(context)
    assert result is context


def test_decays_transient_signals_and_floors_small_values():
    context = {
        "affect_state": {
            "impasse_signal": 1.0,
            "penalty_signal": 0.1,
            "threat_level": 0.04,  # below the 0.05 floor after one decay
            "uncertainty": 0.5,
        }
    }
    loop._apply_transient_signal_decay(context)
    affect_state = context["affect_state"]
    assert affect_state["impasse_signal"] == pytest.approx(1.0 * AFFECT_TRANSIENT_DECAY)
    assert affect_state["penalty_signal"] == pytest.approx(0.1 * AFFECT_TRANSIENT_DECAY)
    assert affect_state["uncertainty"] == pytest.approx(0.5 * AFFECT_TRANSIENT_DECAY)
    assert affect_state["threat_level"] == 0.0


def test_defaults_missing_stagnation_signal_to_zero():
    context = {"affect_state": {}}
    loop._apply_transient_signal_decay(context)
    assert context["affect_state"]["stagnation_signal"] == 0.0


def test_acute_crisis_increments_extreme_cycles():
    context = {
        "affect_state": {
            "core_signals": {
                "impasse_signal": CRISIS_ACUTE_PEAK,
                "threat_level": CRISIS_ABOVE_HALF_THRESHOLD,
                "negative_valence": 0.0,
                "conflict_signal": CRISIS_ABOVE_HALF_THRESHOLD,
                "rejection_signal": 0.0,
            },
            "risk_estimate": 0.0,
            "social_deficit": 0.0,
        },
        "_extreme_cycles": 0,
    }
    assert CRISIS_ABOVE_HALF_COUNT == 2  # two others at/above the half threshold, as set up above
    loop._apply_transient_signal_decay(context)
    assert context["_extreme_cycles"] == 1


def test_chronic_crisis_increments_extreme_cycles():
    context = {
        "affect_state": {
            "core_signals": {
                "impasse_signal": CRISIS_CHRONIC_MEAN,
                "threat_level": CRISIS_CHRONIC_MEAN,
                "negative_valence": CRISIS_CHRONIC_MEAN,
                "conflict_signal": CRISIS_CHRONIC_MEAN,
                "rejection_signal": CRISIS_CHRONIC_MEAN,
            },
            "risk_estimate": CRISIS_CHRONIC_MEAN,
            "social_deficit": CRISIS_CHRONIC_MEAN,
        },
        "_extreme_cycles": 5,
    }
    loop._apply_transient_signal_decay(context)
    assert context["_extreme_cycles"] == 6


def test_no_crisis_recovers_three_times_faster():
    context = {
        "affect_state": {
            "core_signals": {
                "impasse_signal": 0.0,
                "threat_level": 0.0,
                "negative_valence": 0.0,
                "conflict_signal": 0.0,
                "rejection_signal": 0.0,
            },
            "risk_estimate": 0.0,
            "social_deficit": 0.0,
        },
        "_extreme_cycles": 2,
    }
    loop._apply_transient_signal_decay(context)
    assert context["_extreme_cycles"] == 0  # max(0, 2 - 3)


def test_extreme_cycles_capped_at_fifty():
    context = {
        "affect_state": {
            "core_signals": {
                "impasse_signal": CRISIS_ACUTE_PEAK,
                "threat_level": CRISIS_ABOVE_HALF_THRESHOLD,
                "negative_valence": 0.0,
                "conflict_signal": CRISIS_ABOVE_HALF_THRESHOLD,
                "rejection_signal": 0.0,
            },
            "risk_estimate": 0.0,
            "social_deficit": 0.0,
        },
        "_extreme_cycles": 50,
    }
    loop._apply_transient_signal_decay(context)
    assert context["_extreme_cycles"] == 50
