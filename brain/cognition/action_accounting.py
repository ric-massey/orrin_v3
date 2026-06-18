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
    from cognition.reward_rate import is_stagnating

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
