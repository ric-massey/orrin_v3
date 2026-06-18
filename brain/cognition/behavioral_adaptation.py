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

from datetime import datetime, timezone
from typing import Dict, Any, List

from utils.log import log_private
from utils.json_utils import modify_json
from paths import DATA_DIR

# Append-only, bounded record of every behavioral self-edit, so the dashboard can
# answer "is he actually learning?" by showing before → after → because. The engine
# already rewrites behaviour each metacog flush; this is the only place that the
# rewrite is captured as a structured, human-readable diff (see UI master plan §5.1).
_CHANGE_LOG_PATH = DATA_DIR / "behavior_changes.json"
_CHANGE_LOG_CAP = 250

# Per-pattern scientific rationale, kept human-readable for the "because" column.
_REASONS = {
    "rut": "Tolman (1932): a blocked habitual path should trigger exploration of "
           "alternative routes, not more repetition.",
    "oscillation": "Tolman (1932): flip-flopping between two functions is an unstable "
                   "loop — inject novelty pressure to settle on a new route.",
    "goal_avoidance": "Carver & Scheier (1982): the corrective output must change "
                      "behaviour (act on the goal), not just re-observe the gap.",
    "reflection_imbalance": "Powers (1973): over-reflection leaves the control error "
                            "uncorrected — force action to reduce it.",
    "emotional_stagnation": "A stuck dominant emotion is an attractor state; novelty "
                            "seeking is the push needed to leave it.",
}

# How strongly each pattern type nudges action_vs_reflect_bias toward action (0.0–1.0).
_BIAS_NUDGE = {
    "rut":                0.12,
    "oscillation":        0.10,
    "goal_avoidance":     0.18,
    "reflection_imbalance": 0.22,
    "emotional_stagnation": 0.08,
}

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


def _describe_state(
    ptype: str,
    bias: float,
    action: bool,
    context: Dict[str, Any] | None = None,
) -> str:
    """Human-readable snapshot of the behavioral posture for the change log.

    `action=False` describes the BEFORE posture (bias only — the levers were not
    yet pulled); `action=True` describes the AFTER posture including the concrete
    override this pattern armed, read back from the just-mutated context.
    """
    if not action:
        return f"action-vs-reflect bias {bias:.2f}"
    parts = [f"action-vs-reflect bias {bias:.2f}"]
    ctx = context or {}
    if ptype in ("reflection_imbalance", "goal_avoidance"):
        if ctx.get("_force_action_next"):
            parts.append("force-action armed until reward-rate recovery")
        if ptype == "goal_avoidance":
            parts.append("goal pressure amplified")
            if ctx.get("_suppress_goal_deliberation"):
                parts.append("goal-deliberation locked out")
    if ptype in ("rut", "oscillation", "emotional_stagnation"):
        parts.append(f"novelty pressure {float(ctx.get('_novelty_pressure') or 0.0):.2f}")
    return "; ".join(parts)


def _persist_changes(changes: List[Dict[str, Any]]) -> None:
    """Append behavior-change records to the bounded log. Best-effort: telemetry
    must never crash the cognitive loop."""
    try:
        with modify_json(_CHANGE_LOG_PATH, list) as log:
            log.extend(changes)
            overflow = len(log) - _CHANGE_LOG_CAP
            if overflow > 0:
                del log[:overflow]
    except Exception as e:
        log_private(f"[behavioral_adapt] failed to persist behavior changes: {e}")


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
    changes: List[Dict[str, Any]] = []

    for obs in observations:
        ptype = _classify(obs)
        if ptype == "unknown":
            continue

        bias_before = current_bias
        nudge = _BIAS_NUDGE.get(ptype, 0.0)
        current_bias = min(0.92, current_bias + nudge)
        patterns_applied.append(ptype)

        if ptype == "reflection_imbalance":
            # Powers (1973): the control error is maximal here — we need a strong
            # corrective signal that persists into the next function-selection.
            context["_force_action_next"] = True
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
            from cognition.reward_rate import is_stagnating, should_force_switch
            switched = is_stagnating(context) and should_force_switch(context)
            if switched:
                context["_force_action_next"] = True
                context["_suppress_goal_deliberation"] = True
                context["_suppress_intrinsic_goals"] = True
            context.setdefault("_escape_available", True)
            log_private(
                "[behavioral_adapt] goal_avoidance "
                + ("→ patch-leave switch armed" if switched else "→ leave pressure accruing")
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

        # Capture the rewrite as a structured before→after→because record. This is
        # the only place the engine's self-edits become inspectable in the UI.
        changes.append({
            "when": datetime.now(timezone.utc).isoformat(),
            "pattern": ptype,
            "situation": obs,
            "old_action": _describe_state(ptype, bias_before, action=False),
            "new_action": _describe_state(ptype, current_bias, action=True, context=context),
            "reason": _REASONS.get(ptype, ""),
            "evidence": obs,
        })

    if changes:
        _persist_changes(changes)

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

    from cognition.reward_rate import patch_deficit
    recovered = patch_deficit(context) < 0.1
    if recovered:
        for key in (
            "_suppress_goal_deliberation",
            "_suppress_intrinsic_goals",
            "_force_action_next",
        ):
            context.pop(key, None)
        context["_escape_available"] = True

    if recovered and context.get("_goal_pressure_amplified"):
        context.pop("_goal_pressure_amplified", None)

    # Decay action_vs_reflect_bias back toward baseline (0.5) when no pressure
    bias = float(context.get("action_vs_reflect_bias") or 0.5)
    if bias > 0.5 and not context.get("_force_action_next"):
        context["action_vs_reflect_bias"] = max(0.5, round(bias * 0.95, 3))
