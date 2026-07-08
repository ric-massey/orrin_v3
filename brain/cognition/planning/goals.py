# goals.py
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import json
from pathlib import Path
from typing import Any, List, Dict, Optional

from brain.utils.json_utils import load_json, save_json, extract_json
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.cog_memory.working_memory import update_working_memory

from brain.paths import GOALS_FILE, COMPLETED_GOALS_FILE, FOCUS_GOAL
from brain.utils.timeutils import now_iso_z
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
# Goal plan / step operations extracted to goal_plan_ops.py (Phase 4.5C);
# re-imported so the completion sweeper below + the many external callers keep
# their `from …planning.goals import …` paths.
from brain.cognition.planning.goal_plan_ops import (  # noqa: F401
    get_goal_plan as get_goal_plan, get_next_pending_step as get_next_pending_step,
    advance_goal_plan as advance_goal_plan, _normalize_step_text as _normalize_step_text,
    is_placeholder_step as is_placeholder_step, set_goal_plan as set_goal_plan,
    plan_drift_detected as plan_drift_detected, insert_plan_step as insert_plan_step,
    skip_pending_steps as skip_pending_steps,
    reprioritize_pending_steps as reprioritize_pending_steps,
    met_milestone_tokens as met_milestone_tokens,
    unmet_milestone_texts as unmet_milestone_texts,
    prune_satisfied_steps as prune_satisfied_steps, _plan_step_tokens as _plan_step_tokens,
    TERMINAL_STEP_STATUSES as TERMINAL_STEP_STATUSES,
    _PLACEHOLDER_STEPS as _PLACEHOLDER_STEPS, _PLAN_STEP_STOPWORDS as _PLAN_STEP_STOPWORDS,
)
# Self-belief falsification on goal success extracted to goal_belief.py (Phase
# 4.5C); re-imported so mark_goal_completed below keeps its reference.
from brain.cognition.planning.goal_belief import (  # noqa: F401
    _revise_weak_area_beliefs as _revise_weak_area_beliefs,
    _domains_for_goal as _domains_for_goal, _BELIEF_DOMAIN_KW as _BELIEF_DOMAIN_KW,
)
# The goal-tree store (read/write/mutate primitives) extracted to goal_store.py
# (Phase 4.5C); re-imported so the goal logic below + the many external callers
# keep their `from …planning.goals import …` paths.
from brain.cognition.planning.goal_store import (  # noqa: F401
    MAX_GOALS as MAX_GOALS, _TERMINAL_STATUSES as _TERMINAL_STATUSES,
    load_goals as load_goals, save_goals as save_goals, add_goal as add_goal,
    create_micro_goal_for_action as create_micro_goal_for_action,
    mark_goal_status_by_name as mark_goal_status_by_name,
    merge_updated_goal_into_tree as merge_updated_goal_into_tree,
    prune_goals as prune_goals,
    ensure_immediate_actions_bucket as ensure_immediate_actions_bucket,
    _find_goal_by_name as _find_goal_by_name, _attach_child as _attach_child,
    _flatten_goals as _flatten_goals,
    _reconcile_to_disk_terminal as _reconcile_to_disk_terminal,
)
# Artifact / completion-criteria gating extracted to goal_criteria.py (Phase
# 4.5C); re-imported for the pursuit + outcome logic below + external callers.
from brain.cognition.planning.goal_criteria import (  # noqa: F401
    PRODUCTION_DEADLINE_CYCLES as PRODUCTION_DEADLINE_CYCLES,
    _is_artifact_gated as _is_artifact_gated, _definition_of_done as _definition_of_done,
    _criteria_evidence_met as _criteria_evidence_met,
)
# Goal outcome handling (completion/failure/significance) extracted to
# goal_outcomes.py (Phase 4.5C); re-imported so the sweeper below + external
# callers keep their `from …planning.goals import …` paths.
from brain.cognition.planning.goal_outcomes import (  # noqa: F401
    achievement_significance as achievement_significance,
    mark_goal_completed as mark_goal_completed, mark_goal_failed as mark_goal_failed,
    fail_overdue_artifact_goals as fail_overdue_artifact_goals,
)
_log = get_logger(__name__)


# LLM helpers

def _rule_based_decompose(goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Keyword-based subgoal decomposition when LLM is unavailable."""
    name = (goal.get("name") or goal.get("description") or goal.get("title") or "goal").lower()
    n = now_iso_z()

    # File search (benchmark_realignment.md F4): search-shaped goals decompose
    # into search → grep → summarize, mirroring _symbolic_plan's template, so a
    # goal like B3's "Find the word 'supervisor' in any brain file" gets a plan its
    # steps can actually execute instead of the generic template.
    if (("grep" in name) or
            (any(w in name for w in ("find", "search", "locate", "look for"))
             and any(w in name for w in ("file", "files", "word", "string", "code", "brain", "repo")))):
        steps = [
            "Search my own files for the target with search_own_files",
            "Grep the matching files for the exact string with grep_files",
            "Write a one-line summary of where it was found to working memory",
        ]
    elif any(w in name for w in ("research", "learn", "understand", "study", "investigate", "read about")):
        steps = [
            "Research the topic using research_topic (DuckDuckGo + Wikipedia)",
            "Read a full article via fetch_and_read to deepen understanding",
            "Reflect on findings and write a summary to working memory",
        ]
    elif any(w in name for w in ("write", "create", "compose", "draft", "document")):
        steps = [
            "Gather relevant context from long memory and working memory",
            "Draft the content from memory and prior research",
            "Review for accuracy and write the final output",
        ]
    elif any(w in name for w in ("fix", "debug", "error", "problem", "broken", "issue")):
        steps = [
            "Identify the root cause by reviewing recent activity and error logs",
            "Search long memory for similar past issues and solutions",
            "Apply the most likely fix and verify the result",
        ]
    elif any(w in name for w in ("connect", "relat", "social", "person", "ric", "user")):
        steps = [
            "Review known persons and last contact timestamps",
            "Prepare a meaningful update or open question",
            "Log intent to share it at next opportunity",
        ]
    elif any(w in name for w in ("reflect", "introspect", "review", "evaluate", "assess")):
        steps = [
            "Load recent long memory entries (last 20)",
            "Identify recurring themes, unresolved questions, or new patterns",
            "Write a synthesis reflection to working memory",
        ]
    else:
        steps = [
            "Gather context from working memory and long memory",
            "Identify the clearest concrete next action",
            "Execute the action and log the result",
        ]

    return [{
        "name": s, "status": "pending", "timestamp": n, "last_updated": n,
        "subgoals": [], "history": [{"event": "created", "timestamp": n}],
    } for s in steps]


def _rule_based_accomplish(goal: Dict[str, Any]) -> bool:
    """
    Check working memory for evidence this goal was recently completed.
    Returns True only if a clear success signal is found.
    """
    name = (goal.get("name") or "").lower()
    name_words = {w for w in name.split() if len(w) > 4}
    try:
        from brain.utils.json_utils import load_json as _lj
        from brain.paths import WORKING_MEMORY_FILE as _WMF
        wm: List[Any] = _lj(_WMF, default_type=list) or []
        for e in wm[-15:]:
            txt = str(e.get("content", e) if isinstance(e, dict) else e).lower()
            if ("✅" in txt or "accomplished" in txt or "completed" in txt):
                if any(w in txt for w in name_words):
                    return True
    except Exception as _e:
        record_failure("goals._rule_based_accomplish", _e)
    return False


def decompose_goal(goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Break a complex goal into actionable subgoals.
    Uses rule-based decomposition when LLM is unavailable.
    """
    if not llm_callable_by("goals"):
        return _rule_based_decompose(goal)

    prompt = (
        "Decompose the following goal into 3-7 concrete, sequential subgoals.\n"
        f"Goal: {goal.get('name', goal.get('description', 'Unnamed'))}\n"
        'Be concise. Output JSON list of subgoals: ["", ""]'
    )
    result = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "goals")
    subgoals = extract_json(result or "")
    if isinstance(subgoals, list):
        now = now_iso_z()
        return [{
            "name": s if isinstance(s, str) else str(s),
            "status": "pending",
            "timestamp": now,
            "last_updated": now,
            "subgoals": [],
            "history": [{"event": "created", "timestamp": now}],
        } for s in subgoals]
    return _rule_based_decompose(goal)



def try_to_accomplish(goal: Dict[str, Any]) -> bool:
    """
    Attempt an atomic goal. Uses working-memory evidence when LLM unavailable.
    Returns True if succeeded, False if needs decomposition.
    """
    # P2 — artifact gate. An output_producing / requires_artifact goal completes
    # ONLY when the effect ledger holds a novel, structurally-significant effect for
    # it. No LLM self-report and no rule-based accomplish can close it — this is the
    # felt-cost channel's real bite (a make-things goal that produced nothing simply
    # is not done, and will eventually fail at its deadline).
    if _is_artifact_gated(goal):
        gid = str(goal.get("id") or "")
        try:
            from brain.agency.effect_ledger import has_qualifying_effect
            _produced = bool(gid) and has_qualifying_effect(gid, goal)
        except Exception:
            _produced = False
        now = now_iso_z()
        if _produced:
            for m in (goal.get("milestones") or []):
                if isinstance(m, dict) and not m.get("met"):
                    m["met"] = True
                    m["met_at"] = now
            goal["status"] = "completed"
            goal["last_updated"] = now
            goal.setdefault("history", []).append(
                {"event": "completed", "reason": "artifact_verified", "timestamp": now})
            update_working_memory(f"✅ Produced artifact for goal: {goal.get('name')}")
            # P3 — a real, effect-backed contribution decays the served aspiration's
            # recruitment pressure (a bookkeeping closure would not).
            try:
                from brain.cognition.intrinsic_goals import mark_objective_contribution
                mark_objective_contribution(goal.get("driven_by", ""))
            except Exception as _e:
                record_failure("goals.try_to_accomplish.aspiration", _e)
            return True
        goal.setdefault("history", []).append({"event": "awaiting_artifact", "timestamp": now})
        return False

    if _criteria_evidence_met(goal):
        goal["status"] = "completed"
        goal["last_updated"] = now_iso_z()
        goal.setdefault("history", []).append(
            {"event": "completed", "reason": "criteria_verified", "timestamp": now_iso_z()})
        update_working_memory(f"✅ Verified completion criteria for goal: {goal.get('name')}")
        return True

    if not llm_callable_by("goals"):
        success = _rule_based_accomplish(goal)
        if success and not _definition_of_done(goal):
            goal["status"] = "completed"
            goal["last_updated"] = now_iso_z()
            goal.setdefault("history", []).append({"event": "completed", "timestamp": now_iso_z()})
            update_working_memory(f"✅ Accomplished goal: {goal.get('name')}")
        else:
            goal.setdefault("history", []).append({"event": "failed_attempt", "timestamp": now_iso_z()})
        return success

    criteria = _definition_of_done(goal)
    prompt = (
        f'Evaluate completion evidence for this goal: "{goal.get("name", "")}"\n'
        f"Criteria: {criteria}\n"
        "Return JSON only: {\"criteria\": [{\"criterion\": \"exact criterion\", "
        "\"met\": true/false, \"evidence\": \"specific observed evidence\"}]}. "
        "A statement of confidence or success is not evidence."
    )
    result = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "goals")
    out = extract_json(result or "")
    if isinstance(out, dict) and isinstance(out.get("criteria"), list):
        goal["completion_evidence"] = {"criteria": out["criteria"], "checked_at": now_iso_z()}
    if _criteria_evidence_met(goal):
        goal["status"] = "completed"
        goal["last_updated"] = now_iso_z()
        goal.setdefault("history", []).append(
            {"event": "completed", "reason": "criteria_verified", "timestamp": now_iso_z()})
        update_working_memory(f"✅ Accomplished goal: {goal.get('name')}")
        return True
    else:
        goal.setdefault("history", []).append({"event": "failed_attempt", "timestamp": now_iso_z()})
        return False


# Pursuit / completion

def pursue_goal(goal: Dict[str, Any]) -> None:
    if goal.get("tier") == "micro_goal":
        if goal.get("status") in {"completed", "abandoned"}:
            return
        result = try_to_accomplish(goal)
        if result:
            mark_goal_completed(goal)
        else:
            goal["status"] = "blocked"
            goal["last_updated"] = now_iso_z()
        return

    # Composite
    subs = goal.get("subgoals")
    if isinstance(subs, list) and subs:
        for sub in subs:
            if sub.get("status", "pending") in {"pending", "in_progress", "active"}:
                pursue_goal(sub)
                return  # depth-first, one at a time
        # all subgoals done
        mark_goal_completed(goal)
    else:
        result = try_to_accomplish(goal)
        if not result:
            if not goal.get("decomposed"):
                subgoals = decompose_goal(goal)
                if subgoals:
                    goal["subgoals"] = subgoals
                    goal["decomposed"] = True
                    full_tree = load_goals()
                    full_tree = merge_updated_goal_into_tree(full_tree, goal)
                    save_goals(full_tree)
                    update_working_memory(f"🪓 Decomposed goal: {goal.get('name')}")
                    return
            else:
                update_working_memory(
                    f"⚠️ Blocked on goal: {goal.get('name')}. Needs user input or abandonment."
                )
                goal["status"] = "blocked"
                goal["last_updated"] = now_iso_z()


# Focus selection

def select_focus_goals() -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Load goals, select focus goals, and write to FOCUS_GOAL.
    Returns the focus goal dictionary.
    """
    goals: List[Any] = load_json(GOALS_FILE, default_type=list)
    if not isinstance(goals, list):
        goals = []

    def find_focus(goal_list: List[Dict[str, Any]], tier_names: List[str], collected: List[Dict[str, Any]], max_count: int) -> List[Dict[str, Any]]:
        for goal in goal_list:
            if len(collected) >= max_count:
                break
            if goal.get("status") in {"pending", "in_progress", "active"}:
                if goal.get("tier") in tier_names:
                    collected.append(goal)
                subs = goal.get("subgoals")
                if isinstance(subs, list):
                    find_focus(subs, tier_names, collected, max_count)
        return collected

    short_or_mid_goals = find_focus(goals, ["short_term", "mid_term"], [], 2)
    long_term_goals = find_focus(goals, ["long_term"], [], 1)

    focus = {
        "short_or_mid": short_or_mid_goals[0] if short_or_mid_goals else None,
        "long_term": long_term_goals[0] if long_term_goals else None,
    }

    # Only write if V2 GoalsAPI is not the canonical source. When goal_io syncs to GoalsAPI it is
    # active, V2 already owns this state; writing here would create drift.
    try:
        _fg = Path(str(FOCUS_GOAL))
        _existing = {}
        if _fg.exists():
            _existing = json.loads(_fg.read_text(encoding="utf-8"))
        # V2-written entries have an "id" field (UUID); V1-written have "timestamp".
        # Skip the write only when V2 owns it (has "id" on the active goal entry).
        _active = _existing.get("short_or_mid") or _existing.get("long_term")
        _v2_owns = isinstance(_active, dict) and "id" in _active
    except Exception:
        _v2_owns = False

    if not _v2_owns:
        save_json(FOCUS_GOAL, {
            "timestamp": now_iso_z(),
            "short_or_mid": focus["short_or_mid"],
            "long_term": focus["long_term"],
        })
    return focus


# NOTE: the old long-term-goal scaffolding (ensure_long_term_goal /
# update_and_select_focus_goals) was dead code — never called — and has been
# removed. The human-like long-term layer is now the live "aspirations" in
# cognition/intrinsic_goals.py, which the active goal loop maintains.


# Search / uniqueness

def goal_function_already_exists(goal_tree: Optional[List[Dict[str, Any]]], function_name: Optional[str]) -> bool:
    """
    Check if tokens of function_name appear in goal text/history anywhere in the tree.
    """
    target = re.sub(r"\W+", " ", (function_name or "")).strip().lower()
    if not target:
        return False

    def contains_fn(text: str) -> bool:
        tokens = set(re.sub(r"\W+", " ", (text or "")).strip().lower().split())
        return target in tokens

    for goal in goal_tree or []:
        hist_list = goal.get("history")
        hist_text = " ".join(
            h.get("event", "") if isinstance(h, dict) else str(h)
            for h in (hist_list if isinstance(hist_list, list) else [])
        )
        goal_text = f"{goal.get('goal','')} {goal.get('name','')} {hist_text}"
        if contains_fn(goal_text):
            return True
        subs = goal.get("subgoals")
        if isinstance(subs, list) and subs:
            if goal_function_already_exists(subs, function_name):
                return True
    return False



# Completion sweeper

def maybe_complete_goals() -> bool:
    """
    Traverses the full goal tree.
    - Marks goals as completed if all subgoals are completed.
    - Logs and rewards each completion.
    - Saves updated goals back to GOALS_FILE and appends to COMPLETED_GOALS_FILE.
    """
    goals = load_goals()
    changed = False
    completed_goals: List[Dict[str, Any]] = []

    # Ensure completed goals file exists as a list
    existing_completed: List[Any] = load_json(COMPLETED_GOALS_FILE, default_type=list)
    if not isinstance(existing_completed, list):
        existing_completed = []
        save_json(COMPLETED_GOALS_FILE, existing_completed)

    def check_and_complete(goal: Dict[str, Any]) -> bool:
        nonlocal changed
        # If already completed/abandoned, treat as done for parent consideration
        if goal.get("status") in {"completed", "abandoned"}:
            return True

        # Check plan steps — all steps completed means the goal is done
        plan = goal.get("plan")
        if isinstance(plan, list) and plan:
            # A step counts as "done" when completed OR deliberately skipped
            # (e.g. pruned by dynamic subgoal adaptation as already satisfied).
            all_steps_done = all(
                isinstance(s, dict) and s.get("status") in TERMINAL_STEP_STATUSES
                for s in plan
            )
            if all_steps_done and goal.get("status") != "completed":
                # F12 (2026-07-08 addendum): mark_goal_completed is a GUARD that
                # can refuse (hollow milestones, no grounded effect, directional
                # driver). Every downstream effect — the archive append, the
                # changed flag, the WM note — is gated on the actual status flip,
                # so a refusal is never laundered into a recorded completion.
                mark_goal_completed(goal)
                if goal.get("status") == "completed":
                    completed_goals.append(goal)
                    changed = True
                    return True
                return False
            return all_steps_done

        subs = goal.get("subgoals")
        if isinstance(subs, list) and subs:
            all_done = all(check_and_complete(sub) for sub in subs)
            if all_done and goal.get("status") != "completed":
                mark_goal_completed(goal)
                if goal.get("status") == "completed":
                    completed_goals.append(goal)
                    changed = True
                    return True
                return False
            return all_done
        else:
            # Atomic: done only if explicitly completed
            return goal.get("status") == "completed"

    for g in goals:
        check_and_complete(g)

    if changed:
        save_goals(goals)
        update_working_memory("🗂️ Ran maybe_complete_goals: marked some goals as completed.")
        # Append newly completed to completed goals file — only goals whose
        # status genuinely flipped (F12; the guard's refusals never land here).
        existing_completed.extend(
            g for g in completed_goals if g.get("status") == "completed"
        )
        save_json(COMPLETED_GOALS_FILE, existing_completed)
    else:
        update_working_memory("maybe_complete_goals: No new goals completed.")

    return changed
