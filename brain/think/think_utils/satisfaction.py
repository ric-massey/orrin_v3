"""Rule-based cycle satisfaction scoring (Phase 4.5B, from finalize.py).

`_state_satisfaction` derives a 0..1 satisfaction score from observable cycle
state — rewarding agentic and outward actions, goal references in working memory,
and penalising action/outward-presence debt and sustained impasse. finalize_cycle
imports it to score the cycle's outcome. Clark (1997): acting on the environment
is constitutive of cognition.
"""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

# Functions that constitute genuine outward action — coupling cognition to the
# world. These receive a standing reward bonus so the bandit learns to value
# environmental engagement, not just internal computation.
# Clark (1997) embodied cognition; Lave (1988) situated action.
_OUTWARD_ACTION_FNS = frozenset({
    "look_outward", "look_around", "leave_note", "write_desktop_note",
    "survey_environment", "read_clipboard", "announce_to_dashboard",
    "seek_novelty", "pursue_committed_goal", "write_cognitive_function",
    "write_tool", "wikipedia_search", "read_rss", "research_topic",
    "fetch_and_read", "search_own_files", "grep_files", "check_user_presence",
})

# How many cycles since an outward action to start building pressure
_OUTWARD_PRESSURE_RAMP = 8


def _state_satisfaction(context: dict, is_agentic: bool) -> float:
    """
    Rule-based satisfaction from real observable state.
    Outward actions score higher than pure reflection — Orrin should couple
    his cognition to the world, not just process internally.
    Clark (1997): acting on the environment is constitutive of cognition.
    """
    score = 0.40  # neutral baseline

    # Agentic actions are inherently more satisfying than pure reflection
    if is_agentic:
        score += 0.15

    # Outward-action bonus: talking, writing, exploring, researching
    # score 0.20 higher than internal reflection alone.
    fn = context.get("last_function_chosen", "")
    if fn in _OUTWARD_ACTION_FNS:
        score += 0.20

    # Goal progress bonus: did working memory reference the goal?
    goal = bound_goal(context) or {}
    goal_title = (goal.get("title") or "").strip().lower()
    if goal_title:
        wm = context.get("working_memory") or []
        refs = sum(1 for e in wm[-5:] if goal_title in str(e).lower())
        score += min(refs, 2) * 0.10

    # Action debt: stalling on a goal is unsatisfying
    debt = int(context.get("action_debt", 0) or 0)
    if debt >= 3:
        score -= 0.15

    # Outward-presence debt: if too many cycles without outward action, penalise.
    # This creates steady pressure toward environmental engagement.
    outward_debt = int(context.get("_outward_debt", 0) or 0)
    if outward_debt >= _OUTWARD_PRESSURE_RAMP:
        score -= min(0.20, (outward_debt - _OUTWARD_PRESSURE_RAMP) * 0.025)

    # Emotional friction: sustained impasse_signal reduces satisfaction
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    impasse_signal = float(core.get("impasse_signal") or 0.0)
    score -= impasse_signal * 0.15

    return max(0.0, min(1.0, score))
