# Run 4 fix B1 (RUN4_FIX_PLAN_2026-07-04 §B1): the jammed-horn law. An unchanged
# strong signal used to win ignition (trigger 3) every cycle forever, short-
# circuiting emotion/prediction-error/consolidation (three lives, three horns:
# action_debt → drive_rest → social_presence, each 84%+). Habituation attenuates
# a signal that keeps firing at the SAME (source, value) key; a changed value
# restores full strength.

from brain.think import deliberation_gate as dg


def _ctx(strength):
    return {
        "affect_state": {"core_signals": {}},
        "raw_signals": [{"source": "social_presence", "signal_strength": strength}],
    }


def test_unchanged_strong_signal_loses_its_monopoly():
    ctx = {
        "affect_state": {"core_signals": {}},
        "raw_signals": [{"source": "social_presence", "signal_strength": 1.0}],
        "_last_think_cycle": 10**9,   # keep the periodic floor from ever firing
    }
    wins = 0
    for _ in range(60):
        fire, reason = dg.should_think(ctx)
        if fire and reason.startswith("strong_signal"):
            wins += 1
    # The horn no longer dominates: well under 40% of cycles.
    assert wins / 60 < 0.40, f"strong_signal won {wins}/60 — habituation failed"


def test_falls_through_to_lower_triggers_when_habituated():
    # A jammed horn AND a real emotion spike present: once habituated, the gate
    # must fall through and let the emotion trigger fire instead.
    ctx = {
        "affect_state": {"core_signals": {"impasse_signal": 0.9}},
        "_emo_pre_cycle": {"impasse_signal": 0.0},   # +0.9 spike > 0.10
        "raw_signals": [{"source": "social_presence", "signal_strength": 1.0}],
        "_last_think_cycle": 10**9,
    }
    reasons = [dg.should_think(ctx)[1] for _ in range(10)]
    # After the first few strong wins habituate, emotion_spike must appear.
    assert any(r.startswith("emotion_spike") for r in reasons), reasons


def test_value_change_restores_full_strength():
    ctx = {
        "affect_state": {"core_signals": {}},
        "raw_signals": [{"source": "social_presence", "signal_strength": 1.0}],
        "_last_think_cycle": 10**9,
    }
    # Burn the 1.0 key down until it stops winning.
    for _ in range(10):
        dg.should_think(ctx)
    fire_same, reason_same = dg.should_think(ctx)
    assert not (fire_same and reason_same.startswith("strong_signal"))

    # A CHANGED value is a new key with a zero streak — it wins immediately.
    ctx["raw_signals"] = [{"source": "social_presence", "signal_strength": 0.7}]
    fire_new, reason_new = dg.should_think(ctx)
    assert fire_new and reason_new.startswith("strong_signal")
