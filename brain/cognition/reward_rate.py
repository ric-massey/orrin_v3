"""Adaptive reward-rate-relative baselines for leaving an unproductive goal."""
from __future__ import annotations

import math
import random
from typing import Any, Dict

_GLOBAL_ALPHA = 0.002
_LOCAL_ALPHA = 0.05


def update_reward_rate(
    context: Dict[str, Any],
    *,
    reward: float,
    committed_goal_id: str | None,
) -> None:
    """Update life-scale and current-goal reward EMAs once per cycle."""
    g = float(context.get("_global_reward_ema", reward))
    g += _GLOBAL_ALPHA * (reward - g)
    context["_global_reward_ema"] = g
    if committed_goal_id != context.get("_local_rate_goal_id"):
        context["_local_reward_ema"] = g
        context["_local_rate_goal_id"] = committed_goal_id
    local = float(context.get("_local_reward_ema", g))
    context["_local_reward_ema"] = local + _LOCAL_ALPHA * (reward - local)


def patch_deficit(context: Dict[str, Any]) -> float:
    """How far the current goal's reward rate has fallen below the global rate."""
    global_rate = float(context.get("_global_reward_ema", 0.0))
    local_rate = float(context.get("_local_reward_ema", global_rate))
    if global_rate <= 1e-6:
        return 0.0
    return max(0.0, min(1.0, (global_rate - local_rate) / global_rate))


def accrue_leave_pressure(context: Dict[str, Any]) -> float:
    """Continuously integrate patch deficit, with post-switch refractory damping."""
    deficit = patch_deficit(context)
    pressure = float(context.get("_leave_pressure", 0.0))
    pressure = (
        pressure
        + deficit * (1.0 - pressure)
        - (1.0 - deficit) * 0.10 * pressure
    )
    pressure *= _refractory_factor(context)
    context["_leave_pressure"] = max(0.0, min(1.0, pressure))
    return context["_leave_pressure"]


def should_force_switch(context: Dict[str, Any]) -> bool:
    """Sample a smooth patch-leaving hazard from the accrued pressure."""
    pressure = float(context.get("_leave_pressure", 0.0))
    hazard = 1.0 - math.exp(-pressure / 0.35)
    if random.random() < hazard:
        context["_last_switch_cycle"] = int(context.get("_cycle_index", 0) or 0)
        context["_leave_pressure"] = 0.0
        return True
    return False


def _refractory_factor(context: Dict[str, Any]) -> float:
    last = context.get("_last_switch_cycle")
    if last is None:
        return 1.0
    age = int(context.get("_cycle_index", 0) or 0) - int(last)
    return max(0.0, min(1.0, age / (age + 8.0)))


def is_stagnating(context: Dict[str, Any]) -> bool:
    """Whether internal-only progress should stop discharging action debt."""
    return (
        patch_deficit(context) >= 0.5
        and int(context.get("action_debt", 0) or 0) > 0
    )
