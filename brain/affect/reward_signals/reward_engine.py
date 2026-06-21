# brain/affect/reward_signals/reward_engine.py
#
# RewardEngine — the single definition of reward prediction error (RPE).
#
# THE PROBLEM IT SOLVES (V3_AUDIT.md §2.1, D5)
# The *reward value* used to be computed in at least five places, each with its
# own expected-reward baseline: core RPE used a per-action EMA, the calibrator
# hardcoded expected=0.05, priming hardcoded expected=0.5, env-delta hardcoded
# expected=0.5. Because they fed the SAME motivation / exploration / valence
# signals with different prediction baselines, a goal-progress reward and a
# calibrated reward for the same cycle could encode contradictory RPE — the
# learning signal was internally inconsistent.
#
# THE V3 MODEL: one RPE, one baseline
#   submit_reward(...) is the single funnel. It computes
#       expected := action_reward_ema.get_expected(action_type)   # the ONE baseline
#       rpe      := actual - expected                              # inside release_reward
#   then emits through release_reward (the lone affect-touching emitter) and
#   updates the EMA with the observed actual. goal_progress / env_snapshot /
#   reward_calibrator / priming are now *actual-reward providers* that feed this
#   one engine; they no longer each invent an expected baseline.
#
# Schultz, Dayan & Montague (1997) — TD reward prediction error.
from __future__ import annotations

from typing import Any, Dict

from brain.affect.reward_signals.action_reward_ema import get_expected, update_expected
from brain.affect.reward_signals.reward_signals import release_reward


def submit_reward(
    context: Dict[str, Any],
    *,
    actual: float,
    action_type: str,
    kind: str = "reward_signal",
    effort: float = 0.5,
    mode: str = "phasic",
    source: str = "",
) -> None:
    """
    Submit an observed (actual) reward for an action/event.

    The expected baseline is ALWAYS the per-action EMA for `action_type` — the
    single source of truth for "what did we predict here?". This is what makes the
    emitted signal a genuine surprise/RPE signal rather than a flat reward, and it
    is shared across every provider so two rewards in one cycle can never disagree
    on the prediction baseline.

    kind:        which affect channel release_reward routes into (reward_signal,
                 novelty, stability_signal, connection, completion_signal, …).
    action_type: EMA key — the thing whose expected value is being predicted.
    """
    if not isinstance(context, dict):
        return
    try:
        actual = float(actual)
    except (TypeError, ValueError):
        return

    expected = get_expected(context, action_type)
    release_reward(
        context,
        signal=kind,
        actual=actual,
        expected=expected,
        effort=effort,
        mode=mode,
        source=source or action_type,
    )
    # Learn: drift the prediction toward what actually happened.
    update_expected(context, action_type, actual)
