# brain/cognition/planning/goal_progress.py
# Rule-based goal progress measurement.
#
# Returns a [0.0, 1.0] score reflecting how much the current cycle actually
# moved toward the committed goal. This is the primary reward signal when a
# goal is active — no reward for spinning cycles without goal progress.
#
# Rules read real observable state (working memory, action debt, function name)
# so they are truthful and not LLM-guessed.  Orrin can introspect and adjust
# these weights as he learns what "making progress" means for different goal kinds.
from __future__ import annotations

from typing import Any, Dict


# --- Adjustable weights (Orrin can modify these) ---
_W_ACTION_TAKEN       = 0.40  # an action was actually executed this cycle
_W_PURSUIT_FN         = 0.30  # pursue_committed_goal explicitly ran
_W_GOAL_IN_WM         = 0.10  # per working-memory entry that mentions the goal (max 2)
_W_STALL_PENALTY      = 0.20  # subtracted when action_debt is high
_STALL_THRESHOLD      = 3     # debt level at which stalling penalty kicks in
# _BASE_SCORE matches the "no goal → 0.5" neutral return so that having a goal
# but not engaging it this cycle doesn't PENALISE good unrelated work.
# The stall penalty (-0.20) still fires when action_debt is high.
_BASE_SCORE           = 0.50


def compute_goal_progress(
    context: Dict[str, Any],
    action_was_taken: bool = False,
    fn_name: str = "",
) -> float:
    """
    Measure real goal progress from observable context state.

    Called in ORRIN_loop after each cycle when a committed goal is active.
    When no goal is active, returns 0.5 (neutral — don't penalize idle cycles).

    Rules (Orrin can inspect and revise these):
      +0.10  base credit for being active while a goal exists
      +0.40  an action was executed (action_debt resets to 0)
      +0.30  pursue_committed_goal ran this cycle (generated a concrete next step)
      +0.10  each working-memory entry in the last 5 that names the goal (max 2)
      -0.20  stalling: action_debt >= _STALL_THRESHOLD cycles without acting
    """
    goal = context.get("committed_goal")
    if not isinstance(goal, dict) or not goal.get("title"):
        return 0.5  # no goal active → neutral, don't penalize

    goal_title = (goal.get("title") or "").strip().lower()
    score = _BASE_SCORE

    # Credit for taking an action (most concrete signal of progress)
    if action_was_taken:
        score += _W_ACTION_TAKEN

    # Credit for actively pursuing the goal via the dedicated function
    if fn_name in ("pursue_committed_goal", "assess_goal_progress"):
        score += _W_PURSUIT_FN

    # Credit for working-memory entries that reference the goal.
    # Uses word-level matching so "writing a poem" matches goal "write a poem".
    if goal_title:
        _stop = {"a", "an", "the", "is", "to", "for", "in", "of", "and", "or", "my"}
        _goal_words = {w for w in goal_title.split() if w not in _stop and len(w) > 2}
        wm = context.get("working_memory") or []
        refs = sum(
            1 for e in wm[-5:]
            if _goal_words and any(w in str(e).lower() for w in _goal_words)
        )
        score += min(refs, 2) * _W_GOAL_IN_WM

    # Stalling penalty: many cycles with no action → not making progress
    debt = int(context.get("action_debt", 0) or 0)
    if debt >= _STALL_THRESHOLD:
        score -= _W_STALL_PENALTY

    return max(0.0, min(1.0, score))


def goal_weighted_reward(
    base_reward: float,
    context: Dict[str, Any],
    action_was_taken: bool = False,
    fn_name: str = "",
    goal_weight: float = 0.60,
) -> float:
    """
    Blend base reward with goal progress when a committed goal is active.

    When a goal is active:
        final = (1 - goal_weight) * base_reward + goal_weight * goal_progress
    When no goal is active:
        final = base_reward (unchanged)

    goal_weight=0.60 means 60% of the reward is determined by whether the
    cycle actually moved toward the goal, 40% by the function's own quality.
    This creates a strong incentive to stay goal-directed.
    """
    if not (context.get("committed_goal") or {}).get("title"):
        return base_reward

    gp = compute_goal_progress(context, action_was_taken=action_was_taken, fn_name=fn_name)
    blended = (1.0 - goal_weight) * base_reward + goal_weight * gp
    return max(0.0, min(1.0, blended))
