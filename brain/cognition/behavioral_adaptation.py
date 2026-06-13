# brain/cognition/behavioral_adaptation.py
#
# Closes the observation→behavior loop by translating metacognitive insights
# into concrete adjustments to drive weights, action bias, and planning pressure.
#
# SCIENTIFIC BASIS
# ──────────────────────────────────────────────────────────────────────────────
# Carver & Scheier (1982) Control Systems Theory:
#   Discrepancy between perceived state and goal standard generates a corrective
#   output signal — not just awareness of the gap, but behavioral change toward
#   closing it. Observing a rut without adjusting behavior is an open loop.
#   This module closes the loop.
#
# Bandura (1977) Self-Efficacy Theory:
#   Self-observation → self-evaluation → self-reaction. The reaction step must
#   include behavioral modification, not just cognitive labeling of the pattern.
#
# Powers (1973) Perceptual Control Theory:
#   Agents control their perceptions by acting on the world. An agent that only
#   updates beliefs but not actions fails to reduce the control error.
#
# Cybernetic negative feedback (Wiener, 1948):
#   Closed-loop control: error signal → corrective action → reduced error.
#   Metacog patterns are the error signal; this module generates the corrective.
#
# Tolman (1932) Latent Learning / Purposive Behaviorism:
#   Learned patterns only produce behavioral change when combined with a goal
#   incentive. Insight alone (latent learning) is not enough. We need pressure.
#
# Implementation:
#   Pattern text → classify pattern type → apply targeted context mutation:
#   - rut / oscillation     → suppress overused fn + raise action_vs_reflect_bias
#   - goal avoidance        → amplify action_debt pressure + set _force_action_next
#   - reflection imbalance  → raise action_vs_reflect_bias strongly, set flag
#   - emotional stagnation  → inject novelty-seeking drive weight boost
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import Dict, Any, List

from utils.log import log_private

# How strongly each pattern type nudges action_vs_reflect_bias toward action (0.0–1.0).
_BIAS_NUDGE = {
    "rut":                0.12,
    "oscillation":        0.10,
    "goal_avoidance":     0.18,
    "reflection_imbalance": 0.22,
    "emotional_stagnation": 0.08,
}

# After this many cycles of _force_action_next still uncleared, release the flag.
_FORCE_ACTION_MAX_CYCLES = 4

# Once action_debt reaches this, soft pressure has demonstrably failed: stop
# merely nudging and lock goal-DELIBERATION functions (assess_goal_progress,
# adapt_subgoals, adjust_goal_weights) out of selection for a cycle, so the only
# remaining goal-directed option is to actually act on the goal.
_DELIBERATION_LOCKOUT_DEBT = 5


def _classify(observation: str) -> str:
    """Return the pattern category for a metacog observation string."""
    obs = observation.lower()
    if "rut" in obs:
        return "rut"
    if "oscillat" in obs:
        return "oscillation"
    if "avoidance" in obs or "action_debt" in obs or "thinking but not doing" in obs:
        return "goal_avoidance"
    if "imbalance" in obs or "over-processing" in obs:
        return "reflection_imbalance"
    if "stagnation" in obs or "dominant emotion" in obs:
        return "emotional_stagnation"
    return "unknown"


def apply_behavioral_adaptations(
    context: Dict[str, Any],
    observations: List[str],
) -> None:
    """
    Translate metacognitive pattern observations into concrete behavioral
    context mutations so that insight produces action, not just memory.

    Called from metacog_flush() immediately after metacog_analyze() returns.

    Mutations applied to context (all readable by select_function.py):
      action_vs_reflect_bias  — raised toward 1.0 (action) when patterns demand it
      _force_action_next      — True → select_function prioritises _ACTIVE fns
      _goal_pressure_amplified — True → goal-pursuit fns get score boost
      _novelty_pressure       — float boost added to novel function scores

    Carver & Scheier (1982): discrepancy → corrective output, not just observation.
    """
    if not observations:
        return

    current_bias = float(context.get("action_vs_reflect_bias") or 0.5)
    patterns_applied: List[str] = []

    for obs in observations:
        ptype = _classify(obs)
        if ptype == "unknown":
            continue

        nudge = _BIAS_NUDGE.get(ptype, 0.0)
        current_bias = min(0.92, current_bias + nudge)
        patterns_applied.append(ptype)

        if ptype == "reflection_imbalance":
            # Powers (1973): the control error is maximal here — we need a strong
            # corrective signal that persists into the next function-selection.
            context["_force_action_next"] = True
            context["_force_action_remaining"] = _FORCE_ACTION_MAX_CYCLES
            log_private("[behavioral_adapt] force_action_next set — reflection imbalance")

        elif ptype == "goal_avoidance":
            # Bandura (1977): self-efficacy requires acting on goals, not just noting
            # avoidance. Amplify goal pressure so select_function scores it higher.
            context["_goal_pressure_amplified"] = True
            # READ the debt, never write it: action_debt means "consecutive
            # cycles without acting" and is maintained solely by ORRIN_loop
            # (one increment per cycle). Escalating it here inflated the counter
            # past the lifetime cycle count (5,724 "cycles" in a 4,193-cycle
            # run) and poisoned every memory/rule formed from it.
            debt = int(context.get("action_debt") or 0)
            # Arm the action-forcing override. "Thinking but not doing" is the
            # textbook case this flag exists for, yet previously only
            # reflection_imbalance set it — so goal avoidance got only a soft
            # bandit-feature nudge that boosted goal-DELIBERATION
            # (assess_goal_progress) as much as goal-EXECUTION, and the rut never
            # broke. Carver & Scheier (1982): the corrective output must change
            # behaviour, not just re-observe the gap. _force_action_next is what
            # actually penalises deliberation and lifts action in select_function.
            context["_force_action_next"] = True
            context["_force_action_remaining"] = _FORCE_ACTION_MAX_CYCLES
            # Debt escalation: once avoidance is entrenched, the soft override is
            # not enough (deliberation can still win on novelty/energy). Lock the
            # goal-deliberation functions out entirely for the next selection so
            # "assess / adapt / re-weight the goal" cannot stand in for doing it.
            lockout = debt >= _DELIBERATION_LOCKOUT_DEBT
            if lockout:
                context["_suppress_goal_deliberation"] = True
            log_private(
                f"[behavioral_adapt] goal_avoidance → force_action_next set, "
                f"debt now={debt}"
                + (", goal-deliberation locked out" if lockout else "")
            )

        elif ptype in ("rut", "oscillation"):
            # Tolman (1932): blocked habitual path → explore alternative routes.
            # Novelty pressure directly inflates exploration weight in select_function.
            existing_novelty = float(context.get("_novelty_pressure") or 0.0)
            context["_novelty_pressure"] = min(1.5, existing_novelty + 0.25)
            log_private(f"[behavioral_adapt] novelty_pressure → {context['_novelty_pressure']:.2f}")

        elif ptype == "emotional_stagnation":
            # Stagnant dominant emotion → seek novelty to break the attractor state.
            existing_novelty = float(context.get("_novelty_pressure") or 0.0)
            context["_novelty_pressure"] = min(1.5, existing_novelty + 0.15)

    if patterns_applied:
        context["action_vs_reflect_bias"] = round(current_bias, 3)
        log_private(
            f"[behavioral_adapt] patterns={patterns_applied} "
            f"bias→{current_bias:.3f}"
        )


def decay_behavioral_pressure(context: Dict[str, Any]) -> None:
    """
    Called each cycle to decay temporary behavioral pressure signals.
    Prevents a single observation from permanently distorting behavior.

    Carver & Scheier (1982): corrective signal should attenuate once the
    discrepancy is being addressed — not remain permanently amplified.
    """
    # Decay novelty pressure toward zero
    np = float(context.get("_novelty_pressure") or 0.0)
    if np > 0.0:
        context["_novelty_pressure"] = max(0.0, round(np * 0.75, 3))

    # Tick down _force_action countdown
    remaining = int(context.get("_force_action_remaining") or 0)
    if remaining > 0:
        remaining -= 1
        context["_force_action_remaining"] = remaining
        if remaining == 0:
            context.pop("_force_action_next", None)
            context.pop("_force_action_remaining", None)
            log_private("[behavioral_adapt] force_action_next released")

    # Release goal pressure once action_debt drops below warning threshold
    debt = int(context.get("action_debt") or 0)
    if debt < 2 and context.get("_goal_pressure_amplified"):
        context.pop("_goal_pressure_amplified", None)

    # Decay action_vs_reflect_bias back toward baseline (0.5) when no pressure
    bias = float(context.get("action_vs_reflect_bias") or 0.5)
    if bias > 0.5 and not context.get("_force_action_next"):
        context["action_vs_reflect_bias"] = max(0.5, round(bias * 0.95, 3))
