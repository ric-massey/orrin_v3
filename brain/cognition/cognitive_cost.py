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
from typing import Dict, Any

from utils.log import log_private

# Functions that are purely inward-facing (no external effect)
_INTROSPECTIVE_FNS = frozenset({
    "reflect_on_affect", "self_review", "metacog_flush", "dream_cycle",
    "narrative_update", "propose_value_revision", "identity_check",
    "reflect_on_internal_agents", "generate_intrinsic_goals",
    "plan_self_evolution", "simulate_future_selves", "autobiography",
    "value_evolution", "tensions", "look_around",
})

_INTROSPECTIVE_KEYWORDS = ("reflect", "introspect", "dream", "selfhood", "ident", "narrat", "meta")


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

    # ── 1. RECURSIVE THOUGHT → RESOURCE_DEFICIT ────────────────────────────────────────
    # Each consecutive repeat past 2 drains energy. Thinking the same thought
    # again and again isn't free.
    if repeat_count >= 3:
        drain = min(0.03 * (repeat_count - 1), 0.15)
        # resource_deficit lives at the top level of affect_state, not inside core_signals
        emo["resource_deficit"] = min(1.0, float(emo.get("resource_deficit", 0.0)) + drain)
        penalties.append(
            f"recursive thought ({next_function} ×{repeat_count}) "
            f"→ resource_deficit +{drain:.2f}"
        )

    # ── 2. EXCESSIVE INTROSPECTION → RESOURCE_DEFICIT + REDUCED EFFECTIVENESS ──────────
    # Too much inward focus without action costs energy and dulls output.
    recent = context.get("recent_picks") or []
    window8 = recent[-8:]
    intr_count = sum(1 for f in window8 if is_introspective(f))
    if intr_count >= 5:
        drain = 0.03 * (intr_count - 4)
        emo["resource_deficit"] = min(1.0, float(emo.get("resource_deficit", 0.0)) + drain)
        context["_introspection_overload"] = intr_count  # read by action_gate scorer
        penalties.append(
            f"introspection overload ({intr_count}/8 recent picks) "
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
        core["motivation"] = min(1.0, float(core.get("motivation", 0.5)) + boost)
        core["confidence"] = min(1.0, float(core.get("confidence", 0.5)) + boost * 0.5)
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
    goal = context.get("committed_goal")
    if isinstance(goal, dict) and goal.get("title"):
        goal_id = goal.get("id") or goal.get("name") or goal.get("title")
        cc = context.get("cycle_count") or {}
        cycle = int(cc.get("count", 0) if isinstance(cc, dict) else cc or 0)

        if context.get("_tension_goal_id") != goal_id:
            # New goal — start tracking
            context["_tension_goal_id"] = goal_id
            context["_tension_goal_start_cycle"] = cycle
        else:
            cycles_active = cycle - int(context.get("_tension_goal_start_cycle", cycle))
            # Tension starts after 8 cycles, compounds every 4. NOT habituated: an
            # unresolved goal's impasse_signal is an HONEST alarm (ACC-style "this
            # strategy isn't yielding progress"), not noise to damp. It should be
            # resolved by the goal actually getting done or disengaged — never by
            # teaching the system to stop feeling it.
            if cycles_active > 8 and cycles_active % 4 == 0:
                tension = min(0.03 * ((cycles_active - 8) // 4), 0.15)
                core["impasse_signal"] = min(1.0, float(core.get("impasse_signal", 0.0)) + tension)
                core["uncertainty"] = min(1.0, float(core.get("uncertainty", 0.0)) + 0.02)
                title = goal.get("title", "?")[:40]
                penalties.append(
                    f"unresolved goal '{title}' ({cycles_active} cycles active) "
                    f"→ impasse_signal +{tension:.2f}, uncertainty +0.02"
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
