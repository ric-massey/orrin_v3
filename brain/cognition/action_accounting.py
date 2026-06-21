"""Single source of truth for whether a cycle produced goal-relevant action."""
from __future__ import annotations

from typing import Any, Dict


def mark_consequential_cognition(
    context: Dict[str, Any],
    *,
    env_r: float | None,
    ticked_n: int,
    is_failure: bool,
    info_gain: float | None = None,
) -> bool:
    """Credit cognition only when it changed the environment or produced healthy learning."""
    from brain.cognition.reward_rate import is_stagnating

    external = (not is_failure) and (
        int(ticked_n or 0) > 0
        or (env_r is not None and float(env_r) > 0.5)
    )
    internal = (
        (not is_failure)
        and info_gain is not None
        and float(info_gain) > 0.0
    )
    produced = external or (internal and not is_stagnating(context))
    if produced and context.get("committed_goal"):
        context["_consequential_cognition_this_cycle"] = True
        context["__acted_this_tick__"] = True
        # P1 reward split: tag the credit KIND so finalize can pay production more
        # than intake. A cycle only counts as production when a durable external
        # effect was actually recorded (effect_ledger returned a non-dedupe row);
        # consequential cognition (info-gain, milestone tick, env touch) is intake.
        # We do NOT stop crediting info-gain as progress — the phantom-action-debt
        # fix stays intact; we only stop paying it the *production* rate.
        if context.get("_production_effect_this_cycle"):
            context["_action_kind"] = "production"
        else:
            context["_action_kind"] = "intake"
    return bool(produced)


def cycle_produced_goal_action(context: Dict[str, Any]) -> bool:
    """Return the authoritative goal-action result for the current cycle."""
    if not context.get("committed_goal"):
        return False
    if context.get("__acted_this_tick__"):
        return True
    if int(context.get("_milestones_ticked_this_cycle", 0) or 0) > 0:
        return True
    return bool(context.get("_consequential_cognition_this_cycle"))


def reset_cycle_action_flags(context: Dict[str, Any]) -> None:
    """Clear transient accounting state at the start of a cycle."""
    context["_milestones_ticked_this_cycle"] = 0
    context.pop("_consequential_cognition_this_cycle", None)
    context.pop("_last_reach_outcome", None)
    context.pop("_reward_rate_updated_this_cycle", None)
    # P1 reward-split per-cycle flags (set by the effect ledger wire-ins and read
    # by finalize's three-tier reward); must not leak across cycles.
    context.pop("_production_effect_this_cycle", None)
    context.pop("_effect_rows_this_cycle", None)
    context.pop("_action_kind", None)
    context.pop("_verified_artifact_this_cycle", None)
