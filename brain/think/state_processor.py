"""
think/state_processor.py

Computes a CycleState from Orrin's current architectural state.
No LLM. No language generation. Pure state reading.

This is the primary cognitive step each cycle — before any LLM is consulted,
Orrin's architecture already knows what's active, what's unresolved, and
whether something is pressing for expression.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

from typing import Any, Dict, Tuple

from brain.think.cycle_state import CycleState
from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def compute_cycle_state(
    context: Dict[str, Any],
    user_input: str = "",
) -> CycleState:
    """
    Build a CycleState from current state. No LLM.

    Called at the top of every cognitive cycle, before the inner loop
    decides whether complex reasoning is actually needed.
    """
    emo_state = context.get("affect_state") or {}
    core = emo_state.get("core_signals") if isinstance(emo_state.get("core_signals"), dict) else emo_state

    # ── Felt state (rule-based, from affect signal values) ────────────────────
    affect_description = ""
    valence_ctx = ""
    dominant_signal = ""
    dominant_intensity = 0.0
    try:
        from brain.control_signals.signal_summary import (
            render_affect_state as _dfs,
            valence_summary_line as _acl,
        )
        affect_description = _dfs(emo_state)
        valence_ctx = _acl(emo_state)

        # Find dominant affect signal by intensity
        numeric = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
        if numeric:
            dominant_signal = max(numeric, key=numeric.get)
            dominant_intensity = numeric[dominant_signal]
    except Exception as _e:
        record_failure("state_processor.compute_cycle_state", _e)

    # ── Goal orientation (rule-based) ─────────────────────────────────────────
    goal_orientation = ""
    goal_stuck = False
    goal_progress = 0.0
    try:
        from brain.control_signals.signal_summary import format_goal_state as _gfo
        goal = context.get("committed_goal") or {}
        goal_orientation = _gfo(goal)
        goal_stuck = bool(goal.get("stuck") or goal.get("blocked"))
        goal_progress = float(goal.get("progress") or 0.0)
    except Exception as _e:
        record_failure("state_processor.compute_cycle_state.2", _e)

    # ── Active tensions ────────────────────────────────────────────────────────
    active_tension = ""
    tensions = context.get("active_tensions") or []
    if tensions:
        active_tension = str(tensions[0].get("title") or "")[:80]

    # ── Memory surfacing ───────────────────────────────────────────────────────
    relevant_memory = ""
    try:
        memories = context.get("retrieved_memories") or []
        if memories:
            from brain.cog_memory.reconstruction import reconstruct as _recon
            mood = float(emo_state.get("smoothed_state") or 0.0)  # was "mood" key
            relevant_memory = _recon(memories[0], current_mood=mood)[:200]
    except Exception as _e:
        record_failure("state_processor.compute_cycle_state.3", _e)

    # ── Expression seed (what wants to be said) ────────────────────────────────
    output_seed, output_pressure = _compute_output_seed(
        context=context,
        core=core,
        emo_state=emo_state,
        dominant_signal=dominant_signal,
        dominant_intensity=dominant_intensity,
        tensions=tensions,
        goal=context.get("committed_goal") or {},
        user_input=user_input,
    )

    # ── Should express? ────────────────────────────────────────────────────────
    input_urgency = float(context.get("_input_urgency") or 0.0)
    social_penalty = float(core.get("social_penalty") or 0.0)
    suppressed = social_penalty > 0.65

    output_triggered = (
        not suppressed
        and (
            bool(user_input)                    # user said something
            or output_pressure > 0.50        # something urgent wants out
            or dominant_intensity > 0.72        # strong affect pushing for expression
        )
    )

    salience = CycleState(
        affect_description=affect_description,
        dominant_signal=dominant_signal,
        emotion_intensity=dominant_intensity,
        valence_summary=valence_ctx,
        goal_orientation=goal_orientation,
        goal_stuck=goal_stuck,
        goal_progress=goal_progress,
        active_tension=active_tension,
        output_triggered=output_triggered,
        output_pressure=max(output_pressure, input_urgency * 0.8),
        output_seed=output_seed,
        relevant_memory=relevant_memory,
        input_intent=str(context.get("_input_intent") or ""),
        input_urgency=input_urgency,
    )

    log_private(
        f"[state_processor] dom={dominant_signal}({dominant_intensity:.2f}) "
        f"urgency={salience.output_pressure:.2f} express={output_triggered}"
    )
    return salience


def _compute_output_seed(
    context: Dict[str, Any],
    core: Dict[str, float],
    emo_state: Dict[str, Any],
    dominant_signal: str,
    dominant_intensity: float,
    tensions: list,
    goal: Dict[str, Any],
    user_input: str,
) -> Tuple[str, float]:
    """
    What's salient enough that it might need to be said?
    Returns (seed_text, urgency_0_to_1).

    The seed is not prose — it's a compressed signal: what the state is
    asking to communicate. The expression layer finds words for it.
    """
    urgency = 0.0
    seeds = []

    # Strong affect presses for expression
    if dominant_intensity > 0.60:
        try:
            from brain.control_signals.signal_summary import describe_dominant_affect as _dom
            sense = _dom(emo_state)
            if sense:
                seeds.append(sense)
            urgency = max(urgency, dominant_intensity * 0.75)
        except Exception as _e:
            record_failure("state_processor._compute_output_seed", _e)

    # Long-active tension
    if tensions:
        top = tensions[0]
        cycles = int(top.get("cycles_active") or 0)
        if cycles > 4:
            seeds.append(f"unresolved: {top.get('title','')[:50]}")
            urgency = max(urgency, 0.35 + min(cycles * 0.02, 0.25))

    # Blocked goal
    if goal.get("stuck") or goal.get("blocked"):
        title = (goal.get("title") or "")[:50]
        seeds.append(f"stuck: {title}")
        urgency = max(urgency, 0.45)

    # social_deficit presses for contact
    social_deficit = float(emo_state.get("social_deficit") or 0.0)
    if social_deficit > 0.55:
        seeds.append("wanting contact")
        urgency = max(urgency, social_deficit * 0.55)

    # User input always gives urgency to respond
    if user_input:
        urgency = max(urgency, 0.65)
        # Add the concept from comprehension if available
        last_comp = context.get("_last_comprehension") or {}
        concept = str(last_comp.get("concept") or "")
        if concept:
            seeds.append(f"responding to: {concept}")

    # Wonder / exploration_drive at high intensity wants to be shared
    wonder = float(core.get("novelty_signal") or 0.0)
    exploration_drive = float(core.get("exploration_drive") or 0.0)
    if max(wonder, exploration_drive) > 0.68:
        seeds.append("something pulling for attention")
        urgency = max(urgency, 0.40)

    seed = " / ".join(s for s in seeds[:3] if s)
    return seed, urgency
