"""F1 + F2 of the 2026-10-17 learning investigation
(analysis/2026-10-17-cognitive-learning-investigation/REPORT.md).

F1 — goal progress credited activity: an unrelated non-failing call scored 0.9
progress and a 0.32 reward came out 0.668; a failure's -0.1 came out +0.26.
F2 — think()'s finalizer runs before the pick executes, so it filed the previous
function's reward under the new pick (history, replay, the deliberation
discount) and under the selector's pick even when an override ran something else.
"""
from __future__ import annotations

import json

import pytest

from brain.cognition.planning.goal_progress import compute_goal_progress, goal_weighted_reward

_GOAL = {"committed_goal": {"id": "g1", "title": "map the dictionary"}}


# ── F1 ───────────────────────────────────────────────────────────────────────

def test_unrelated_call_is_not_goal_progress():
    ctx = dict(_GOAL)
    assert compute_goal_progress(ctx, action_was_taken=False, fn_name="read_rss") == 0.5
    # the investigation's probe case: base .32 used to become .668
    assert goal_weighted_reward(0.32, ctx, action_was_taken=False, fn_name="read_rss") == pytest.approx(0.32)


def test_failure_keeps_its_sign_under_a_goal():
    ctx = dict(_GOAL)
    assert goal_weighted_reward(-0.1, ctx, action_was_taken=False, fn_name="x") == pytest.approx(-0.1)


def test_advancing_the_goal_pays():
    ctx = dict(_GOAL)
    assert goal_weighted_reward(0.32, ctx, action_was_taken=True, fn_name="x") == pytest.approx(0.56)
    pursued = goal_weighted_reward(0.32, ctx, action_was_taken=True, fn_name="pursue_committed_goal")
    assert pursued > 0.56


def test_assessing_or_naming_the_goal_is_not_progress():
    ctx = dict(_GOAL, working_memory=["thinking about the dictionary"] * 5)
    assert compute_goal_progress(ctx, action_was_taken=False, fn_name="assess_goal_progress") == 0.5
    assert compute_goal_progress(ctx, action_was_taken=False, fn_name="pursue_committed_goal") == 0.5


def test_stalling_still_costs():
    ctx = dict(_GOAL, action_debt=5)
    assert goal_weighted_reward(0.32, ctx) < 0.32


def test_cognition_path_reads_the_consequential_flag():
    from brain.loop.cognition_reward import shape_cognition_reward
    emo = {"core_signals": {}}

    def r(**extra):
        return shape_cognition_reward(dict(_GOAL, **extra), "sort_word_list", "", emo, emo,
                                      env_r=0.0, status_r=0.5, is_failure=False)

    assert r(_consequential_cognition_this_cycle=True) > r()


# ── F2 ───────────────────────────────────────────────────────────────────────

class _Speaker:
    def speak_final(self, *a, **k):
        return None


def _cycle(ctx, pick, ran=None, reward=None, n=1):
    """One cycle: think()'s finalize for `pick`, then the loop executing `ran`."""
    from brain.cognition.action_accounting import _record_step_outcome
    from brain.think.think_utils.finalize import finalize_cycle
    ctx["_cycle_index"] = n
    ctx["cycle_count"] = {"count": n}
    finalize_cycle(ctx, "", pick, {"via": "test"}, _Speaker())
    if ran is not None:
        _record_step_outcome(ctx, ran, reward)
        ctx["last_function_chosen"] = pick


def _history():
    from brain.paths import COGNITION_HISTORY_FILE
    return json.loads(COGNITION_HISTORY_FILE.read_text() or "[]")


@pytest.fixture
def fresh(monkeypatch):
    from brain.paths import COGNITION_HISTORY_FILE, SIGNAL_FUNCTION_MAP_FILE
    COGNITION_HISTORY_FILE.write_text("[]")
    SIGNAL_FUNCTION_MAP_FILE.write_text("{}")
    submitted = []
    import brain.control_signals.reward_signals.reward_engine as re_mod
    monkeypatch.setattr(re_mod, "submit_reward",
                        lambda ctx, actual, action_type, **k: submitted.append((action_type, actual)))
    return submitted


def test_history_pairs_each_pick_with_its_own_reward(fresh):
    ctx = {"affect_state": {"core_signals": {}}}
    _cycle(ctx, "alpha", ran="alpha", reward=0.9, n=1)
    _cycle(ctx, "beta", ran="beta", reward=0.1, n=2)
    _cycle(ctx, "gamma", n=3)
    h = {e["choice"]: e["reward"] for e in _history()}
    assert h == {"alpha": 0.9, "beta": 0.1}


def test_reward_engine_keys_on_the_function_that_ran(fresh):
    ctx = {"affect_state": {"core_signals": {}}}
    # selector picked alpha; a setpoint override ran repair instead
    _cycle(ctx, "alpha", ran="repair", reward=0.7, n=1)
    _cycle(ctx, "beta", n=2)
    assert ("repair", 0.7) in fresh
    assert not any(k == "alpha" for k, _ in fresh)
    entry = _history()[-1]
    assert entry["choice"] == "alpha" and entry["executed"] == "repair"


def test_outer_finalize_names_the_override():
    from brain.cognition.action_accounting import _record_step_outcome
    import brain.loop.finalize as fin
    ctx = {"_cycle_index": 4}
    _record_step_outcome(ctx, "repair", 0.5)
    # only the stamp logic is under test; stop after last_function_chosen is set
    try:
        fin.finalize_cycle(ctx, {"next_function": "alpha"}, 0.5, {}, 4)
    except Exception:
        pass
    assert ctx["last_function_chosen"] == "repair"
