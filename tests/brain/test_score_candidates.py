"""Isolation tests for the per-action scoring loop (selection/score_actions.py).

Phase 4.5A extracted the scoring loop into `score_candidates(actions, defs,
ScoreInputs, context)`. Bundling its inputs in `ScoreInputs` is what finally
makes a single scoring step assertable in isolation: build a neutral baseline,
flip exactly one input, and confirm the loop's `total` moves by exactly that
amount (and only for the affected candidate). These pin individual contributions
the older single-function shape could only test through the full selector.
"""
import dataclasses

import pytest

from brain.think.think_utils.selection.score_actions import (
    ScoreInputs, score_candidates,
)


def _baseline() -> ScoreInputs:
    """A neutral ScoreInputs: zero weights, empty boost maps, no goal context.
    Every component the loop sums is 0 (or identical across candidates), so any
    delta in a candidate's total is attributable to the single field flipped."""
    return ScoreInputs(
        w_dir=0.0, w_goal=0.0, w_emo=0.0, w_novel=0.0, w_band=0.0, w_drive=0.0,
        directive="", focus_goal_text="", recent=[],
        emo_pref={}, sem_prior={}, band_hint={},
        drive_pull={}, tension_boost={}, attn_fn_boost={}, energy_boost={},
        helpfulness_boost={}, emo_route_boost={}, chain_boost={}, neuro_boost={},
        emo_mode_boost={}, outward_boost={}, goal_recruit={}, recruit_boost={},
        workspace_prior={}, unconscious_damp={},
        has_committed_goal=False, goal_type="general", mismatch_fn=None,
        type_family=frozenset(),
        stats={}, pool_median_reward=None,
        expl_drive=0.0, goal_commit=0.0, impasse=0.0,
        reach_value_fn=None, reach_fns=frozenset(),
        dominant="", stagnation_signal=0.0, attention_mode="neutral",
        user_spoke=False,
    )


def _totals(si: ScoreInputs, actions, context=None):
    defs = {a: a for a in actions}
    scored = score_candidates(actions, defs, si, context if context is not None else {})
    return {name: total for name, total, _parts in scored}


def test_returns_one_tuple_per_action_with_component_breakdown():
    actions = ["alpha", "beta", "gamma"]
    scored = score_candidates(actions, {a: a for a in actions}, _baseline(), {})
    assert [name for name, _t, _p in scored] == actions
    # Each entry carries the component-score dict the reason payload surfaces.
    for _name, total, parts in scored:
        assert isinstance(total, float)
        assert {"dir", "goal", "emo", "novel", "band", "outward"} <= set(parts)


def test_additive_boost_map_contributes_exactly_its_value():
    """A per-function additive boost (here energy_boost) lands on the target
    candidate's total one-for-one, and leaves other candidates untouched."""
    actions = ["alpha", "beta"]
    base = _totals(_baseline(), actions)
    boosted = _totals(
        dataclasses.replace(_baseline(), energy_boost={"alpha": 0.5}), actions
    )
    assert boosted["alpha"] == pytest.approx(base["alpha"] + 0.5)
    assert boosted["beta"] == pytest.approx(base["beta"])


def test_weighted_component_scales_by_its_weight():
    """The bandit hint is a weighted component: its contribution to total is
    w_band * band_hint, so doubling the weight doubles its contribution."""
    actions = ["alpha", "beta"]
    si_w = dataclasses.replace(_baseline(), w_band=0.2, band_hint={"alpha": 1.0})
    si_2w = dataclasses.replace(_baseline(), w_band=0.4, band_hint={"alpha": 1.0})
    base = _totals(_baseline(), actions)
    t_w = _totals(si_w, actions)
    t_2w = _totals(si_2w, actions)
    assert t_w["alpha"] == pytest.approx(base["alpha"] + 0.2)
    assert t_2w["alpha"] == pytest.approx(base["alpha"] + 0.4)


def test_no_goal_suppression_penalises_goal_pursuit_fns():
    """With no committed goal, goal-pursuit functions take a decisive -0.65 so a
    high prior can't pick them; the penalty lifts once a goal is committed."""
    actions = ["assess_goal_progress", "alpha"]
    no_goal = _totals(_baseline(), actions)
    with_goal = _totals(
        dataclasses.replace(_baseline(), has_committed_goal=True), actions
    )
    assert with_goal["assess_goal_progress"] - no_goal["assess_goal_progress"] == pytest.approx(0.65)
    # A non-pursuit function is unaffected by the committed-goal flag here.
    assert with_goal["alpha"] == pytest.approx(no_goal["alpha"])


def test_consecutive_repetition_penalty_decays_total():
    """A function picked on the last 2+ consecutive cycles has its (positive)
    total scaled down (×0.6 beyond 2), so it cannot hold the slot indefinitely."""
    actions = ["alpha"]
    # Give alpha a positive baseline via an additive boost. Compare the same
    # inputs with vs without a 2-pick repeat streak so the (name-dependent)
    # pre-penalty total cancels and only the ×0.6 repetition factor remains.
    boosted = dataclasses.replace(_baseline(), energy_boost={"alpha": 1.0})
    no_repeat = _totals(boosted, actions)["alpha"]
    repeated = _totals(
        dataclasses.replace(boosted, recent=["alpha", "alpha"]), actions
    )["alpha"]
    # _consec == 2 → factor 0.6 ** (2 - 1) == 0.6
    assert repeated == pytest.approx(no_repeat * 0.6)
