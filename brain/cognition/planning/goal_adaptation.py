"""Goal adaptation (Phase 4D, from pursue_goal.py).

assess_goal_progress() evaluates recent pursuit for drift (storing _drift_score);
adapt_subgoals() reshapes a committed goal's plan surgically (blocker detection,
milestone-gap filling) rather than wholesale replanning. Imported helpers are
downward-only (no cycle); pursue_goal re-exports assess_goal_progress and
adapt_subgoals.
"""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger

import re
import time
from typing import Any, Dict, List, Optional

from brain.utils.generate_response import generate_reasoning_chain
from brain.utils.json_utils import load_json
from brain.utils.log import log_activity, log_error
from brain.cog_memory.working_memory import update_working_memory
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import LONG_MEMORY_FILE
from brain.utils.failure_counter import record_failure
from brain.cognition.planning.goals import (
    get_goal_plan, insert_plan_step,
    prune_satisfied_steps, reprioritize_pending_steps, unmet_milestone_texts,
    _plan_step_tokens,
)
from brain.cognition.planning.plan_versioning import _score_drift, _save_plan_version

_log = get_logger(__name__)

_last_adapt_ts: float = 0.0
_ADAPT_COOLDOWN_S: float = 60.0


def assess_goal_progress(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Review recent pursuit steps and self-assess whether the goal is converging.
    Sets goal["_drift_detected"] = True if assessment signals off-track, which
    causes pursue_committed_goal() to replan on the next call.
    """
    context = context or {}
    goal    = bound_goal(context)
    if not isinstance(goal, dict) or not goal.get("title"):
        return {"status": "ok", "skipped": True}

    goal_title = goal.get("title", "")

    long_mem: List[Any] = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(long_mem, list):
        return {"status": "ok", "skipped": True, "reason": "no_long_memory"}

    pursuit_entries = [
        e for e in long_mem
        if isinstance(e, dict)
        and e.get("event_type") == "goal_pursuit"
        and goal_title.lower() in str(e.get("content", "")).lower()
    ][-8:]

    if len(pursuit_entries) < 2:
        return {"status": "ok", "skipped": True, "reason": "insufficient_history"}

    steps_text = "\n".join(
        f"  {i+1}. {e.get('content','')[:120]}"
        for i, e in enumerate(pursuit_entries)
    )

    plan_summary = ""
    plan = get_goal_plan(goal)
    if plan:
        done    = sum(1 for s in plan if s.get("status") == "completed")
        pending = sum(1 for s in plan if s.get("status") == "pending")
        plan_summary = f"Plan: {done} completed, {pending} pending of {len(plan)} steps."

    context_text = (
        f"Recent pursuit steps:\n{steps_text}\n\n"
        f"Goal kind: {goal.get('kind', '')}\n"
        f"Goal source: {goal.get('source', 'unknown')}\n"
        f"{plan_summary}"
    )

    try:
        result = generate_reasoning_chain(
            topic=f"Assess progress on goal: {goal_title}",
            context_text=context_text,
            caller="goal_progress_assess",
        )
        assessment = (result.get("content") or "").strip()
        scratchpad  = result.get("scratchpad", {})

        if assessment:
            update_working_memory({
                "content":    f"[Goal assessment] {goal_title}: {assessment[:300]}",
                "event_type": "goal_assessment",
                "importance": 3, "priority": 2,
            })
            if scratchpad.get("reasoning"):
                update_long_memory(
                    f"[goal_assessment_reasoning] '{goal_title}': {scratchpad['reasoning'][:200]}",
                    emotion="exploration_drive",
                    event_type="goal_assessment",
                    importance=2,
                    context=context,
                )

            # Score drift severity and signal if above detection threshold (0.15)
            drift_score = _score_drift(assessment)
            if drift_score > 0.15:
                goal["_drift_detected"] = True
                goal["_drift_score"]    = round(drift_score, 3)
                context["committed_goal"] = goal
                log_activity(
                    f"[goal_progress] Drift flagged for '{goal_title}' "
                    f"(score={drift_score:.2f}) — will replan"
                )
                if drift_score > 0.70:
                    # Severe drift → immediate long-memory escalation
                    try:
                        update_long_memory(
                            f"[goal_severe_drift] '{goal_title}' — assessment signals severe drift "
                            f"(score={drift_score:.2f}): {assessment[:200]}",
                            emotion="impasse_signal",
                            event_type="goal_drift",
                            importance=4,
                            context=context,
                        )
                    except Exception as _e:
                        record_failure("pursue_goal.assess_goal_progress", _e)

            log_activity(f"[goal_progress] assessed '{goal_title}' drift={drift_score:.2f}")
            return {
                "status":     "ok",
                "assessment": assessment,
                "drift":      goal.get("_drift_detected", False),
                "drift_score": round(drift_score, 3),
            }

    except Exception as e:
        log_error(f"[goal_progress] assess error: {e}")

    return {"status": "ok"}


# ── Dynamic subgoal adaptation ─────────────────────────────────────────────────
# (_last_adapt_ts / _ADAPT_COOLDOWN_S are defined once at module top.)

# Words/phrases in working memory that signal an emergent blocker — something
# that must be handled before the rest of the plan can make progress.
_BLOCKER_TERMS = (
    "blocked", "cannot", "can't", "unable to", "missing", "prerequisite",
    "requires", "depends on", "need to first", "failed to", "stuck on",
    "obstacle", "waiting on", "not available",
)
_MAX_GAP_FILL = 2  # cap new steps generated per adaptation pass


def _detect_blocker(context: Dict[str, Any], goal: Dict[str, Any]) -> str:
    """
    Scan recent working memory for a freshly surfaced blocker. Returns a short
    description, or "" if none found or one is already being addressed.
    Skips the pursuit loop's own bookkeeping entries to avoid false positives.
    """
    plan = get_goal_plan(goal)
    if any(
        isinstance(s, dict) and s.get("status") == "pending"
        and "resolve blocker" in str(s.get("step", "")).lower()
        for s in plan
    ):
        return ""  # a remediation step is already queued

    wm = context.get("working_memory") or []
    for entry in reversed(wm[-8:]):
        if isinstance(entry, dict):
            etype = str(entry.get("event_type", "")).lower()
            text = str(entry.get("content", ""))
        else:
            etype, text = "", str(entry)
        low = text.lower()
        # Skip our own pursuit/adaptation notes — they aren't real blockers.
        if low.startswith("[goal pursuit]") or low.startswith("[subgoal_adapt]"):
            continue
        if etype in ("goal_blocked", "goal_failure") or any(t in low for t in _BLOCKER_TERMS):
            return _strip_blocker_prefixes(text)[:140]
    return ""


# Self-nesting guard (BEHAVIOR_FIX_PLAN 2.2): WM text that surfaces as a blocker
# may itself be a previous blocker step or status note ("Resolve blocker: I am
# blocked: …"). Build remediation steps from the RAW reason only — strip any
# accumulated prefixes, repeatedly, before re-wrapping.
_BLOCKER_PREFIX_RE = re.compile(
    r"^\s*(?:resolve blocker\s*:\s*|i am blocked\s*:?\s*|blocked\s*:\s*)+",
    re.IGNORECASE,
)


def _strip_blocker_prefixes(text: str) -> str:
    out = str(text or "").strip()
    for _ in range(8):
        new = _BLOCKER_PREFIX_RE.sub("", out).strip()
        if new == out:
            break
        out = new
    return out


def _fill_milestone_gaps(goal: Dict[str, Any]) -> int:
    """
    For each unmet milestone with no pending plan step covering it, append a
    concrete step so the milestone is actually worked toward. Symbolic, capped.
    Returns the number of steps added.
    """
    plan = get_goal_plan(goal)
    pending_token_sets = [
        _plan_step_tokens(s.get("step"))
        for s in plan
        if isinstance(s, dict) and s.get("status") == "pending"
    ]
    added = 0
    for text in unmet_milestone_texts(goal):
        if added >= _MAX_GAP_FILL:
            break
        ms_tokens = _plan_step_tokens(text)
        if len(ms_tokens) < 2:
            continue
        covered = any(len(ms_tokens & pts) >= 2 for pts in pending_token_sets)
        if covered:
            continue
        new = insert_plan_step(
            goal, f"Work toward milestone: {text}", position=None,
            reason="milestone_gap",
        )
        if new:
            pending_token_sets.append(_plan_step_tokens(new.get("step")))
            added += 1
    return added


def adapt_subgoals(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Dynamically adapt the committed goal's breakdown to current conditions.

    Surgical, progress-preserving complement to the drift→full-replan path in
    pursue_committed_goal(): instead of discarding the plan, it
      1. ticks milestones newly observable in working memory,
      2. skips pending steps whose work is already done (milestone-covered),
      3. inserts a remediation step when a blocker surfaces in working memory,
      4. reprioritizes the pending tail toward still-unmet milestones,
      5. fills coverage gaps for unmet milestones that have no pending step.

    Every operation is symbolic (no LLM) so it works with the LLM gate closed.
    The plan is versioned before mutation so a bad adaptation can be rolled back.
    """
    global _last_adapt_ts
    context = context or {}

    goal = bound_goal(context)
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"status": "ok", "skipped": True, "reason": "no_committed_goal"}
    if goal.get("status") in ("completed", "abandoned", "failed"):
        return {"status": "ok", "skipped": True, "reason": "goal_already_done"}

    now = time.time()
    if now - _last_adapt_ts < _ADAPT_COOLDOWN_S:
        return {"status": "ok", "skipped": True, "reason": "cooldown"}
    _last_adapt_ts = now

    goal_title = goal.get("title") or goal.get("name", "")
    changes: List[str] = []

    # Snapshot the current plan so adapt_subgoals is reversible like a replan.
    _save_plan_version(goal, reason="adapt_subgoals")

    # 1. Tick any milestones now satisfied in working memory.
    try:
        from brain.cognition.planning.env_snapshot import apply_milestone_updates
        ticked = apply_milestone_updates(context)
        if ticked:
            changes.append(f"ticked {ticked} milestone(s)")
    except Exception as _e:
        log_error(f"[adapt_subgoals] milestone update failed: {_e}")

    # 2. Skip pending steps already satisfied by a met milestone.
    skipped = prune_satisfied_steps(goal, context)
    if skipped:
        changes.append(f"skipped {skipped} satisfied step(s)")

    # 3. Insert a remediation step for a freshly surfaced blocker.
    blocker = _detect_blocker(context, goal)
    if blocker:
        ins = insert_plan_step(
            goal, f"Resolve blocker: {blocker}", reason="blocker_detected",
        )
        if ins:
            changes.append("inserted blocker-remediation step")

    # 4. Reprioritize the pending tail toward still-unmet milestones.
    unmet_tokens: set[str] = set()
    for text in unmet_milestone_texts(goal):
        unmet_tokens |= _plan_step_tokens(text)
    if unmet_tokens:
        if reprioritize_pending_steps(
            goal, lambda s: len(_plan_step_tokens(s.get("step")) & unmet_tokens)
        ):
            changes.append("reprioritized pending steps")

    # 5. Fill coverage gaps for unmet milestones with no pending step.
    added = _fill_milestone_gaps(goal)
    if added:
        changes.append(f"added {added} step(s) for uncovered milestone(s)")

    # Persist: context (live slot) + goal tree (survives restart).
    context["committed_goal"] = goal
    try:
        from brain.cognition.planning.goals import merge_updated_goal_into_tree
        from brain.cognition.planning import goal_arbiter
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="adapt_subgoals")
    except Exception as _e:
        log_activity(f"[adapt_subgoals] could not persist goal tree: {_e}")

    if changes:
        summary = "; ".join(changes)
        update_working_memory(f"[subgoal_adapt] '{goal_title[:60]}': {summary}")
        log_activity(f"[adapt_subgoals] '{goal_title[:60]}': {summary}")
        return {"status": "ok", "goal": goal_title, "changes": changes}

    return {"status": "ok", "goal": goal_title, "changes": [], "note": "no adaptation needed"}
