# brain/cognition/planning/pursue_goal.py
"""
Active goal pursuit with adaptive reasoning depth, plan versioning, and
inner-loop-powered drift recovery.

pursue_committed_goal():
  - Reads the stored plan on context["committed_goal"]["plan"] if it exists.
  - Executes the next pending step directly (no replanning needed).
  - Only replans when:
      - The goal has no plan yet  (first run)
      - The plan is exhausted     (all steps completed)
      - assess_goal_progress() detected drift (drift_score > 0.15)
  - Drift severity determines replan depth:
      - drift_score 0.15–0.40 → lightweight replan (_generate_plan)
      - drift_score > 0.40    → deep replan through run_inner_loop
  - Plan history is versioned; rollback available via _rollback_plan_version().

assess_goal_progress():
  - Evaluates recent pursuit history using 3-step reasoning.
  - Stores both _drift_detected (bool) and _drift_score (float 0.0–1.0).
"""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger

import re
from typing import Any, Dict, Optional

from brain.cog_memory.working_memory import update_working_memory
from brain.cognition.planning.goals import (
    get_next_pending_step, set_goal_plan,
)
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)
# Goal closure / survival / disengagement, extracted to goal_closure.py (Phase 4D).
from brain.cognition.planning.goal_closure import (  # noqa: F401
    _FINALIZED_IDS, _tier_closure_enabled, _survival_preempt_enabled, _survival_critical,
    _finalize_goal_completion, _maybe_close_on_tier,
    _degrade_or_disengage as _degrade_or_disengage,
    _repromote_if_recovered,
)


# ── LLM gate ─────────────────────────────────────────────────────────────────

# ── Drift severity scorer ─────────────────────────────────────────────────────

# Drift-scoring + plan-versioning helpers, extracted to plan_versioning.py
# (Phase 4D). Re-imported for internal callers below.
from brain.cognition.planning.plan_versioning import (  # noqa: F401
    _score_drift, _save_plan_version, _rollback_plan_version,
)

# Refractory period between pursuit acts. A short refractory is plausible (you
# don't re-fire the same motor program instantly), but 90s was long enough that,
# at ~10s/cycle, most pursuit picks returned "cooldown" and did nothing —
# starving the forced-action path. 30s lets a forced pursuit actually act.
# Goal IDs finalized recently (id → ts), to stop the same goal closing twice across
# its several in-flight dict copies (committed_goal / committed_goals / store pull).
# Give a recognised-but-ineffective step this many tries before advancing past
# it, so one unreachable step cannot hard-stall the whole plan.

# Honest hand-off / disengagement (dual_process Phase 5 + Wrosch goal disengagement):
# how many cognitive cycles the conscious mind is given to perform a deliberate/
# generative step the Executive can't run, before the goal is disengaged. Counted
# at most once per cognitive cycle (not per Executive tick) so it tracks real
# conscious opportunities, not daemon frequency.
# Goal plan generation, extracted to goal_planning.py (Phase 4D).
from brain.cognition.planning.goal_planning import (  # noqa: F401
    _symbolic_plan, _generate_plan, _causal_first_step,
)
# Active goal execution, extracted to goal_execution.py (Phase 4D).
from brain.cognition.planning.goal_execution import (  # noqa: F401
    pursue_committed_goal as pursue_committed_goal, _STEP_MAX_ATTEMPTS,
)
# Goal adaptation, extracted to goal_adaptation.py (Phase 4D).
from brain.cognition.planning.goal_adaptation import (  # noqa: F401
    assess_goal_progress as assess_goal_progress,
    adapt_subgoals as adapt_subgoals,
)



# ── Deliberate goal-attention (does NOT execute) ──────────────────────────────

def attend_goal(context: Optional[Dict[str, Any]] = None) -> str:
    """Thin DELIBERATE act (dual_process_loop.md §6.3): consciously focus on the
    committed goal WITHOUT executing its steps. Step execution is owned by the
    Executive (which runs pursue_committed_goal in the background) — so this keeps
    "deciding to concentrate" available to the conscious slot without double
    execution (I3). Surfaces the goal and its next step into working memory so the
    deliberate mind can think about, supervise, or recommit to it.
    """
    context = context or {}
    goal = bound_goal(context)
    if not isinstance(goal, dict):
        return "No committed goal to attend to."
    title = goal.get("title") or goal.get("name") or "(untitled)"
    step = get_next_pending_step(goal)
    step_text = step.get("step") if isinstance(step, dict) else None
    msg = (f"[attend_goal] Holding focus on '{title}'. "
           + (f"Next step (the Executive is advancing it): {step_text}"
              if step_text else "Plan complete — awaiting objective check."))
    update_working_memory(msg)
    return msg


# ── Deliberate SUPERVISION of the Executive (I6 — the supervisor steers the
#    autopilot). Goal writes go through the GoalArbiter (Phase 1). ──────────────

def _stuck_enough(goal: Dict[str, Any]) -> bool:
    """True only when a goal is genuinely struggling — guards destructive commands
    so an exploratory pick can't kill a goal that's progressing fine."""
    if int(goal.get("_completion_attempts", 0) or 0) >= 2:
        return True
    sa = goal.get("_step_attempts")
    return isinstance(sa, dict) and any(int(v or 0) >= _STEP_MAX_ATTEMPTS for v in sa.values())


def redirect_goal_plan(context: Optional[Dict[str, Any]] = None) -> str:
    """Deliberate command (§6.3/I6): regenerate the committed goal's plan — the
    conscious mind steering the autopilot when the current approach isn't working.
    Non-destructive (re-plans, never kills)."""
    context = context or {}
    goal = bound_goal(context)
    if not isinstance(goal, dict):
        return "No committed goal to redirect."
    title = goal.get("title") or goal.get("name") or "(untitled)"
    new_plan = _symbolic_plan(title, context)
    if not new_plan:
        return f"Could not generate a new plan for '{title}'."
    set_goal_plan(goal, new_plan)
    goal.pop("_step_attempts", None)
    goal.pop("_completion_attempts", None)
    try:
        from brain.cognition.planning.goals import merge_updated_goal_into_tree
        from brain.cognition.planning import goal_arbiter
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="redirect_goal_plan")
    except Exception as _e:
        record_failure("pursue_goal.redirect_goal_plan", _e)
    update_working_memory(f"[redirect_goal_plan] Re-planned '{title}' — {len(new_plan)} new step(s).")
    return f"Re-planned '{title}' with {len(new_plan)} steps."


def abandon_goal(context: Optional[Dict[str, Any]] = None) -> str:
    """Deliberate command (§6.3/I6/I10): let go of the committed goal. Guarded — only
    abandons a genuinely-stuck goal, so an exploratory pick can't kill a healthy one.
    Marking-failed feeds the self-repair loop and is a CONSCIOUS decision, never the
    Executive's."""
    context = context or {}
    goal = bound_goal(context)
    if not isinstance(goal, dict):
        return "No committed goal to abandon."
    title = goal.get("title") or goal.get("name") or "(untitled)"
    if not _stuck_enough(goal):
        return f"'{title}' is still progressing — not abandoning it."
    try:
        from brain.cognition.planning.goals import mark_goal_failed, merge_updated_goal_into_tree
        from brain.cognition.planning import goal_arbiter
        mark_goal_failed(goal, reason="released by deliberate decision (stuck)", context=context)
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="abandon_goal")
    except Exception as _e:
        record_failure("pursue_goal.abandon_goal", _e)
    context["committed_goal"] = None
    context["_last_bootstrap_ts"] = 0.0  # let a fresh goal spawn
    update_working_memory(f"[abandon_goal] Let go of '{title}' (stuck) — making room for what's next.")
    return f"Abandoned '{title}'."


# ── Fix 1 (explore_loop_fix_plan.md §5): tier-aware objective closure ─────────















# ── Main entry ───────────────────────────────────────────────────────────────



# ── Progress assessment ──────────────────────────────────────────────────────



# ── Dynamic subgoal adaptation ─────────────────────────────────────────────────


# Words/phrases in working memory that signal an emergent blocker — something
# that must be handled before the rest of the plan can make progress.
_BLOCKER_TERMS = (
    "blocked", "cannot", "can't", "unable to", "missing", "prerequisite",
    "requires", "depends on", "need to first", "failed to", "stuck on",
    "obstacle", "waiting on", "not available",
)
_MAX_GAP_FILL = 2  # cap new steps generated per adaptation pass




# Self-nesting guard (BEHAVIOR_FIX_PLAN 2.2): WM text that surfaces as a blocker
# may itself be a previous blocker step or status note ("Resolve blocker: I am
# blocked: …"). Build remediation steps from the RAW reason only — strip any
# accumulated prefixes, repeatedly, before re-wrapping.
_BLOCKER_PREFIX_RE = re.compile(
    r"^\s*(?:resolve blocker\s*:\s*|i am blocked\s*:?\s*|blocked\s*:\s*)+",
    re.IGNORECASE,
)






