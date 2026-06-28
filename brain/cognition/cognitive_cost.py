# brain/cognition/cognitive_cost.py
#
# Real consequences for bad cognition.
#
# Humans pay for spiraling. So does Orrin.
#
#   recursive thought     → resource_deficit accumulates
#   contradiction         → emotional instability
#   unresolved goals      → tension and impasse_signal
#   excessive introspection → resource_deficit + reduced action effectiveness

from __future__ import annotations
from brain.cognition.global_workspace import bound_goal
from typing import Dict, Any

from brain.utils.log import log_private

# Functions that are purely inward-facing (no external effect)
_INTROSPECTIVE_FNS = frozenset({
    "reflect_on_affect", "self_review", "metacog_flush", "idle_consolidation_cycle",
    "narrative_update", "propose_value_revision", "identity_check",
    "reflect_on_internal_agents", "generate_intrinsic_goals",
    "plan_self_evolution", "simulate_future_selves", "autobiography",
    "value_evolution", "tensions", "look_around",
})

_INTROSPECTIVE_KEYWORDS = ("reflect", "introspect", "consolidat", "self_state", "ident", "narrat", "meta")


def _consolidating_now() -> bool:
    """True while the dream daemon is in the sleep phase."""
    try:
        from brain.cognition.idle_consolidation.consolidation_cycle import consolidating_now
        return bool(consolidating_now())
    except ImportError:  # intentional: dream daemon optional → not dreaming
        return False


def is_introspective(fn: str) -> bool:
    """True if the function is purely inward-facing with no external effect."""
    if fn in _INTROSPECTIVE_FNS:
        return True
    fn_lower = fn.lower()
    return any(k in fn_lower for k in _INTROSPECTIVE_KEYWORDS)


def apply_cognitive_costs(
    context: Dict[str, Any],
    next_function: str = "",
    repeat_count: int = 1,
) -> None:
    """
    Called once per cycle after a cognition function is chosen.
    Mutates affect_state in-place and logs warnings to working memory.
    Defaults allow safe dispatch from the cognition registry (context-only call).
    """
    try:
        _apply(context, next_function, repeat_count)
    except Exception as e:
        log_private(f"[cognitive_cost] error: {e}")


def _apply(context: Dict[str, Any], next_function: str, repeat_count: int) -> None:
    emo = context.get("affect_state") or {}
    if not isinstance(emo, dict):
        return
    core = emo.get("core_signals")
    if not isinstance(core, dict):
        core = emo  # flat format

    penalties: list[str] = []
    sleeping = _consolidating_now()

    # ── 1. RECURSIVE THOUGHT → RESOURCE_DEFICIT ────────────────────────────────────────
    # Each consecutive repeat past 2 drains energy. Thinking the same thought
    # again and again isn't free.
    if repeat_count >= 3 and not sleeping:
        drain = min(0.03 * (repeat_count - 1), 0.15)
        # resource_deficit lives at the top level of affect_state, not inside core_signals
        emo["resource_deficit"] = min(1.0, float(emo.get("resource_deficit", 0.0)) + drain)
        penalties.append(
            f"recursive thought ({next_function} ×{repeat_count}) "
            f"→ resource_deficit +{drain:.2f}"
        )

    # ── 2. EXCESSIVE INTROSPECTION → RESOURCE_DEFICIT + REDUCED EFFECTIVENESS ──────────
    # Too much inward focus without action costs energy and dulls output. But the
    # fatigue PUMP must fire only when the rumination DEEPENS, never every cycle it
    # persists — otherwise it self-reinforces: high resource_deficit + impasse biases
    # the bandit toward reflection → ≥5/8 introspective → more deficit → more impasse,
    # a rumination loop that pays for itself in fatigue (embodiment audit §H, Loop 2).
    # The steering flag (_introspection_overload) stays set the whole time so
    # action_gate keeps pushing him OUT of the loop; only the additive drain is gated
    # on escalation, so being in a reflective stretch is not itself perpetually taxed.
    recent = context.get("recent_picks") or []
    window8 = recent[-8:]
    intr_count = sum(1 for f in window8 if is_introspective(f))
    prev_overload = int(context.get("_introspection_overload", 0) or 0)
    if intr_count >= 5:
        context["_introspection_overload"] = intr_count  # read by action_gate scorer
        # Pump only on ONSET (crossing into overload) or ESCALATION (deeper than before).
        if intr_count > prev_overload and not sleeping:
            drain = 0.03 * (intr_count - max(prev_overload, 4))
            emo["resource_deficit"] = min(1.0, float(emo.get("resource_deficit", 0.0)) + drain)
            penalties.append(
                f"introspection overload deepening ({prev_overload or '<5'}→{intr_count}/8) "
                f"→ resource_deficit +{drain:.2f}, action effectiveness ↓"
            )
    else:
        context.pop("_introspection_overload", None)

    # ── 3. FLOW STATE: consecutive action-oriented picks → motivation boost ───
    # When Orrin picks non-introspective functions repeatedly, he enters flow.
    # Flow is rewarding in itself: motivation and confidence get a small lift.
    action_count = sum(1 for f in window8 if not is_introspective(f))
    if action_count >= 4:
        flow_depth = action_count - 3
        context["_flow_depth"] = flow_depth
        boost = min(0.08, 0.02 * flow_depth)
        from brain.control_signals.homeostasis import pump_signal
        pump_signal(core, "motivation", boost, default=0.5)
        pump_signal(core, "confidence", boost * 0.5, default=0.5)
    else:
        context.pop("_flow_depth", None)

    # ── 4. COGNITIVE INDECISION (ping-pong) → INSTABILITY ─────────────────────
    # Alternating A→B→A→B means Orrin can't commit. That's destabilising.
    rp6 = recent[-6:]
    if (
        len(rp6) >= 4
        and rp6[-1] == rp6[-3]   # same function two ago
        and rp6[-2] == rp6[-4]   # other function two ago
        and rp6[-1] != rp6[-2]   # they're different (actual alternation)
    ):
        old_stab = float(emo.get("affect_stability", 0.75))
        emo["affect_stability"] = max(0.1, old_stab - 0.06)
        core["uncertainty"] = min(1.0, float(core.get("uncertainty", 0.0)) + 0.05)
        penalties.append(
            f"cognitive indecision ({rp6[-2]} ↔ {rp6[-1]}) "
            f"→ stability −0.06, uncertainty +0.05"
        )

    # ── 5. UNRESOLVED GOALS → TENSION ─────────────────────────────────────────
    # A goal that keeps not getting done builds real impasse_signal.
    goal = bound_goal(context)
    if isinstance(goal, dict) and goal.get("title"):
        from brain.cognition.reward_rate import accrue_leave_pressure, patch_deficit

        deficit = patch_deficit(context)
        accrue_leave_pressure(context)
        if context.get("_escape_available", True):
            current_impasse = float(core.get("impasse_signal", 0.0) or 0.0)
            core["impasse_signal"] = min(
                1.0,
                current_impasse + 0.25 * deficit * (1.0 - current_impasse),
            )
            if deficit > 0.0:
                context["_impasse_reason"] = (
                    f"local reward rate ~{deficit:.0%} below background (stall)"
                )
        else:
            context["_force_disengage_goal"] = True

        goal_id = goal.get("id") or goal.get("name") or goal.get("title")
        cc = context.get("cycle_count") or {}
        cycle = int(cc.get("count", 0) if isinstance(cc, dict) else cc or 0)

        if context.get("_tension_goal_id") != goal_id:
            # New goal — start tracking
            context["_tension_goal_id"] = goal_id
            context["_tension_goal_start_cycle"] = cycle
        else:
            cycles_active = cycle - int(context.get("_tension_goal_start_cycle", cycle))
            if deficit > 0.0 and context.get("_escape_available", True):
                core["uncertainty"] = min(
                    1.0,
                    float(core.get("uncertainty", 0.0)) + 0.02 * deficit,
                )
                title = goal.get("title", "?")[:40]
                penalties.append(
                    f"unresolved goal '{title}' ({cycles_active} cycles active) "
                    f"→ reward-rate deficit {deficit:.0%}"
                )
    else:
        context.pop("_tension_goal_id", None)
        context.pop("_tension_goal_start_cycle", None)

    # ── Apply and log ──────────────────────────────────────────────────────────
    if not penalties:
        return

    # Write core back into the right place (handle both flat and nested)
    if isinstance(emo.get("core_signals"), dict):
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo

    log_private(f"[cognitive_cost] {' | '.join(penalties)}")
