# tests/brain/test_consciousness_trigger.py
#
# Unit tests for think/consciousness_trigger.py
# Covers: all 10 priority conditions, the floor rule, edge cases with missing/None data.

from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch

BRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "brain"
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from think.consciousness_trigger import (
    should_think,
    MAX_SILENT_CYCLES,
    _UNCERTAINTY_THRESHOLD,
    _SIGNAL_STRENGTH_TRIGGER,
    _EMOTION_SPIKE_DELTA,
    _STAGNATION_SIGNAL_THRESHOLD,
    _WONDER_THRESHOLD,
    _ACTION_DEBT_TRIGGER,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ctx(**kwargs):
    """Build a minimal context dict that keeps should_think from firing on defaults."""
    base = {
        "affect_state": {"core_signals": {
            "uncertainty": 0.0,
            "impasse_signal": 0.0,
            "threat_level": 0.0,
            "conflict_signal": 0.0,
            "social_penalty": 0.0,
            "loss_signal": 0.0,
            "stagnation_signal": 0.0,
            "wonder": 0.0,
        }},
        "raw_signals": [],
        "committed_goal": {},
        "_emo_pre_cycle": {},
        "latest_user_input": "",
        "action_debt": 0,
        "_last_think_cycle": 0,
    }
    base.update(kwargs)
    return base


def _silent_ctx(current_cycle: int = 0) -> dict:
    """Context that passes all 9 checks and sits just under the floor."""
    ctx = _ctx(_last_think_cycle=current_cycle - (MAX_SILENT_CYCLES - 1))
    return ctx


# ── Condition 1: user input ───────────────────────────────────────────────────

def test_user_input_fires():
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(_ctx(latest_user_input="hello"))
    assert fire
    assert reason == "user_input"


def test_empty_user_input_does_not_fire():
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(_ctx(latest_user_input="   "))
    assert not fire


def test_none_user_input_does_not_fire():
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(_ctx(latest_user_input=None))
    assert not fire


# ── Condition 2: uncertainty ──────────────────────────────────────────────────

def test_high_uncertainty_fires():
    ctx = _ctx()
    ctx["affect_state"]["core_signals"]["uncertainty"] = _UNCERTAINTY_THRESHOLD + 0.01
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "high_uncertainty" in reason


def test_uncertainty_at_threshold_does_not_fire():
    ctx = _ctx()
    ctx["affect_state"]["core_signals"]["uncertainty"] = _UNCERTAINTY_THRESHOLD
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


# ── Condition 3: strong signal ────────────────────────────────────────────────

def test_strong_signal_fires():
    sig = {"source": "emotion", "signal_strength": _SIGNAL_STRENGTH_TRIGGER, "content": "x"}
    ctx = _ctx(raw_signals=[sig])
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "strong_signal" in reason


def test_weak_signal_does_not_fire():
    sig = {"source": "emotion", "signal_strength": _SIGNAL_STRENGTH_TRIGGER - 0.01, "content": "x"}
    ctx = _ctx(raw_signals=[sig])
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


def test_strongest_signal_chosen_in_reason():
    weak = {"source": "a", "signal_strength": 0.50, "content": ""}
    strong = {"source": "b", "signal_strength": _SIGNAL_STRENGTH_TRIGGER + 0.05, "content": ""}
    ctx = _ctx(raw_signals=[weak, strong])
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "b@" in reason


def test_signals_none_does_not_crash():
    ctx = _ctx(raw_signals=None)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, reason = should_think(ctx)
    assert isinstance(fire, bool)


# ── Condition 4: emotion spike ────────────────────────────────────────────────

def test_emotion_spike_fires():
    pre = {"impasse_signal": 0.30}
    now = {"impasse_signal": 0.30 + _EMOTION_SPIKE_DELTA + 0.01}
    ctx = _ctx(_emo_pre_cycle=pre)
    ctx["affect_state"]["core_signals"]["impasse_signal"] = now["impasse_signal"]
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "emotion_spike_impasse_signal" in reason


def test_small_emotion_change_does_not_fire():
    pre = {"impasse_signal": 0.30}
    ctx = _ctx(_emo_pre_cycle=pre)
    ctx["affect_state"]["core_signals"]["impasse_signal"] = 0.30 + _EMOTION_SPIKE_DELTA - 0.01
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


def test_missing_emo_pre_cycle_does_not_crash():
    ctx = _ctx()
    ctx.pop("_emo_pre_cycle", None)
    ctx["affect_state"]["core_signals"]["impasse_signal"] = 0.90
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, reason = should_think(ctx)
    # _emo_pre_cycle is missing → treated as 0.0 → spike fires
    assert fire
    assert "emotion_spike_impasse_signal" in reason


# ── Condition 5: prediction error ────────────────────────────────────────────

def test_prediction_error_fires():
    ctx = _ctx(_prediction_error=True)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert reason == "prediction_error"


def test_no_prediction_error_does_not_fire():
    ctx = _ctx(_prediction_error=False)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


# ── Condition 6: goal drift / stall ──────────────────────────────────────────

def test_goal_drift_fires():
    ctx = _ctx(committed_goal={"_drift_detected": True})
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert reason == "goal_drift_or_stall"


def test_goal_stall_fires():
    ctx = _ctx(committed_goal={"_stalled": True})
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert reason == "goal_drift_or_stall"


def test_healthy_goal_does_not_fire():
    ctx = _ctx(committed_goal={"title": "do something"})
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


# ── Condition 7: action debt ─────────────────────────────────────────────────

def test_action_debt_fires():
    ctx = _ctx(committed_goal={"title": "goal"}, action_debt=_ACTION_DEBT_TRIGGER)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "action_debt" in reason


def test_action_debt_without_goal_does_not_fire():
    # no committed_goal → condition 7 is skipped
    ctx = _ctx(committed_goal={}, action_debt=_ACTION_DEBT_TRIGGER + 5)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


def test_action_debt_below_threshold_does_not_fire():
    ctx = _ctx(committed_goal={"title": "goal"}, action_debt=_ACTION_DEBT_TRIGGER - 1)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


# ── Condition 8: stagnation_signal ─────────────────────────────────────────────────────

def test_stagnation_signal_fires():
    ctx = _ctx()
    ctx["affect_state"]["core_signals"]["stagnation_signal"] = _STAGNATION_SIGNAL_THRESHOLD + 0.01
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "stagnation_signal" in reason


def test_stagnation_signal_at_threshold_does_not_fire():
    ctx = _ctx()
    ctx["affect_state"]["core_signals"]["stagnation_signal"] = _STAGNATION_SIGNAL_THRESHOLD
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, _ = should_think(ctx)
    assert not fire


# ── Condition 9: wonder ───────────────────────────────────────────────────────

def test_wonder_fires():
    ctx = _ctx()
    ctx["affect_state"]["core_signals"]["wonder"] = _WONDER_THRESHOLD + 0.01
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "wonder" in reason


# ── Condition 10: periodic floor ─────────────────────────────────────────────

def test_floor_fires_after_max_silent_cycles():
    ctx = _ctx(_last_think_cycle=10)
    current = 10 + MAX_SILENT_CYCLES
    with patch("think.consciousness_trigger.get_cycle_count", return_value=current):
        fire, reason = should_think(ctx)
    assert fire
    assert "periodic_floor" in reason
    assert f"silent_for={MAX_SILENT_CYCLES}" in reason


def test_floor_does_not_fire_one_cycle_early():
    ctx = _ctx(_last_think_cycle=10)
    current = 10 + MAX_SILENT_CYCLES - 1
    with patch("think.consciousness_trigger.get_cycle_count", return_value=current):
        fire, _ = should_think(ctx)
    assert not fire


def test_floor_fires_on_fresh_context_with_no_last_think():
    # _last_think_cycle defaults to 0; if current cycle >= MAX_SILENT_CYCLES, it fires
    ctx = _ctx(_last_think_cycle=0)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=MAX_SILENT_CYCLES):
        fire, reason = should_think(ctx)
    assert fire
    assert "periodic_floor" in reason


# ── Quiet result ──────────────────────────────────────────────────────────────

def test_quiet_when_nothing_fires():
    ctx = _ctx(_last_think_cycle=10)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=10):
        fire, reason = should_think(ctx)
    assert not fire
    assert reason == "quiet"


# ── Edge: missing / malformed emotional state ─────────────────────────────────

def test_none_emotional_state_does_not_crash():
    ctx = _ctx(affect_state=None, _last_think_cycle=0)
    with patch("think.consciousness_trigger.get_cycle_count", return_value=0):
        fire, reason = should_think(ctx)
    assert isinstance(fire, bool)


def test_flat_emotional_state_without_core_emotions_key():
    # Some callers pass a flat dict (no "core_emotions" sub-key)
    ctx = _ctx(_last_think_cycle=0)
    ctx["affect_state"] = {"uncertainty": _UNCERTAINTY_THRESHOLD + 0.10}
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert fire
    assert "high_uncertainty" in reason


# ── Priority ordering ─────────────────────────────────────────────────────────

def test_user_input_beats_uncertainty():
    ctx = _ctx(latest_user_input="hi")
    ctx["affect_state"]["core_signals"]["uncertainty"] = 0.99
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        fire, reason = should_think(ctx)
    assert reason == "user_input"


def test_uncertainty_beats_strong_signal():
    ctx = _ctx()
    ctx["affect_state"]["core_signals"]["uncertainty"] = _UNCERTAINTY_THRESHOLD + 0.05
    ctx["raw_signals"] = [{"source": "s", "signal_strength": 0.99, "content": ""}]
    with patch("think.consciousness_trigger.get_cycle_count", return_value=999):
        _, reason = should_think(ctx)
    assert "high_uncertainty" in reason
