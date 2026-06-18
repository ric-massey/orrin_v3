import pytest

import cognition.reward_rate as rr
from affect.homeostasis import update_allostatic_load
from cognition.action_accounting import (
    cycle_produced_goal_action,
    mark_consequential_cognition,
    reset_cycle_action_flags,
)
from cognition.cognitive_cost import apply_cognitive_costs


def test_consequential_cognition_credits_environment_change():
    ctx = {"committed_goal": {"id": "g1"}}

    assert mark_consequential_cognition(
        ctx, env_r=0.7, ticked_n=0, is_failure=False,
    )
    assert ctx["__acted_this_tick__"] is True
    assert cycle_produced_goal_action(ctx) is True


def test_consequential_cognition_rejects_neutral_or_failed_steps():
    ctx = {"committed_goal": {"id": "g1"}}

    assert not mark_consequential_cognition(
        ctx, env_r=0.5, ticked_n=0, is_failure=False,
    )
    assert not cycle_produced_goal_action(ctx)
    assert not mark_consequential_cognition(
        ctx, env_r=0.9, ticked_n=1, is_failure=True,
    )


def test_reset_cycle_action_flags_preserves_behavioral_stamp_until_consumed():
    ctx = {
        "__acted_this_tick__": True,
        "_milestones_ticked_this_cycle": 3,
        "_consequential_cognition_this_cycle": True,
    }
    reset_cycle_action_flags(ctx)
    assert ctx["_milestones_ticked_this_cycle"] == 0
    assert "_consequential_cognition_this_cycle" not in ctx
    assert ctx["__acted_this_tick__"] is True


def test_reward_rate_reseeds_local_rate_on_goal_switch():
    ctx = {"_global_reward_ema": 0.8, "_local_reward_ema": 0.2}
    rr.update_reward_rate(ctx, reward=0.6, committed_goal_id="new")
    assert ctx["_local_rate_goal_id"] == "new"
    assert ctx["_local_reward_ema"] > 0.5


def test_patch_deficit_and_leave_pressure_are_continuous():
    ctx = {"_global_reward_ema": 0.8, "_local_reward_ema": 0.2}
    assert rr.patch_deficit(ctx) == pytest.approx(0.75)
    first = rr.accrue_leave_pressure(ctx)
    second = rr.accrue_leave_pressure(ctx)
    assert 0.0 < first < second < 1.0


def test_exploration_allostatic_load_rises_only_after_existing_load():
    state = {"allostatic_load": 0.2}
    core = {"exploration_drive": 0.9}
    first = update_allostatic_load(state, core)
    second = update_allostatic_load(state, core)
    assert second > first

    recovered = update_allostatic_load(state, {"exploration_drive": 0.3})
    assert recovered < second


def test_impasse_does_not_rise_without_an_escape():
    ctx = {
        "committed_goal": {"id": "g1", "title": "blocked"},
        "affect_state": {
            "core_signals": {"impasse_signal": 0.3, "uncertainty": 0.1},
        },
        "_global_reward_ema": 0.8,
        "_local_reward_ema": 0.2,
        "_escape_available": False,
    }

    apply_cognitive_costs(ctx, "reflection", 1)

    assert ctx["affect_state"]["core_signals"]["impasse_signal"] == 0.3
    assert ctx["_force_disengage_goal"] is True
