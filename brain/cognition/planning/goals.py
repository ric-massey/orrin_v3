# goals.py
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from brain.utils.json_utils import load_json, save_json, extract_json
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.cog_memory.working_memory import update_working_memory
from brain.utils.log import log_activity
from brain.affect.reward_signals.reward_signals import release_reward_signal

from brain.paths import GOALS_FILE, COMPLETED_GOALS_FILE, FOCUS_GOAL
from brain.utils.timeutils import now_iso_z
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
# Goal plan / step operations extracted to goal_plan_ops.py (Phase 4.5C);
# re-imported so the completion sweeper below + the many external callers keep
# their `from …planning.goals import …` paths.
from brain.cognition.planning.goal_plan_ops import (  # noqa: F401
    get_goal_plan, get_next_pending_step, advance_goal_plan, _normalize_step_text,
    is_placeholder_step, set_goal_plan, plan_drift_detected, insert_plan_step,
    skip_pending_steps, reprioritize_pending_steps, met_milestone_tokens,
    unmet_milestone_texts, prune_satisfied_steps, _plan_step_tokens,
    TERMINAL_STEP_STATUSES, _PLACEHOLDER_STEPS, _PLAN_STEP_STOPWORDS,
)
# Self-belief falsification on goal success extracted to goal_belief.py (Phase
# 4.5C); re-imported so mark_goal_completed below keeps its reference.
from brain.cognition.planning.goal_belief import (  # noqa: F401
    _revise_weak_area_beliefs, _domains_for_goal, _BELIEF_DOMAIN_KW,
)
_log = get_logger(__name__)

MAX_GOALS = 15





# Tree helpers

def _find_goal_by_name(tree: List[Dict], name: str) -> Optional[Dict]:
    for g in tree:
        if g.get("name") == name:
            return g
        subs = g.get("subgoals")
        if isinstance(subs, list):
            found = _find_goal_by_name(subs, name)
            if found:
                return found
    return None


def _attach_child(parent: Dict, child: Dict) -> None:
    if "subgoals" not in parent or not isinstance(parent["subgoals"], list):
        parent["subgoals"] = []
    parent["subgoals"].append(child)
    parent["last_updated"] = now_iso_z()


def ensure_immediate_actions_bucket(goals: List[Dict]) -> Dict:
    bucket_name = "Immediate Actions"
    for g in goals:
        if g.get("name") == bucket_name:
            return g
    bucket = {
        "name": bucket_name,
        "tier": "short_term",
        "status": "active",
        "timestamp": now_iso_z(),
        "last_updated": now_iso_z(),
        "history": ["Auto-created for micro goals"],
        "subgoals": [],
    }
    goals.append(bucket)
    return bucket


# Load / Save

def load_goals() -> List[Dict]:
    goals = load_json(GOALS_FILE, default_type=list)
    if not isinstance(goals, list):
        return []

    # Normalise list-valued fields. Persisted goals occasionally have a corrupted
    # history/subgoals/plan (a dict instead of a list); downstream code does
    # goal.setdefault("history", []).append(...), and setdefault returns the
    # existing dict, so .append blows up ("'dict' object has no attribute
    # 'append'"). Coercing here fixes every append site at the source.
    def _norm(g: Dict) -> Dict:
        if not isinstance(g, dict):
            return g
        for k in ("history", "subgoals", "plan", "milestones"):
            if k in g and not isinstance(g[k], list):
                g[k] = []
        for sub in (g.get("subgoals") or []):
            _norm(sub)
        return g

    return [_norm(g) for g in goals if isinstance(g, dict)]


_TERMINAL_STATUSES = {"completed", "failed", "abandoned", "cancelled"}


def _flatten_goals(nodes):
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        yield node
        yield from _flatten_goals(node.get("subgoals"))


def _reconcile_to_disk_terminal(goal: Dict) -> Dict:
    """Adopt an existing terminal state before merging a stale in-memory copy."""
    if not isinstance(goal, dict):
        return goal
    gid = goal.get("id") or goal.get("title") or goal.get("name")
    if not gid:
        return goal
    disk_goals = load_json(GOALS_FILE, default_type=list) or []
    for node in _flatten_goals(disk_goals):
        node_id = node.get("id") or node.get("title") or node.get("name")
        if (
            node_id == gid
            and str(node.get("status", "")).lower() in _TERMINAL_STATUSES
        ):
            goal["status"] = node["status"]
            if node.get("completed_timestamp"):
                goal["completed_timestamp"] = node["completed_timestamp"]
            break
    return goal


def save_goals(goals: List[Dict]) -> None:
    # Terminal-status stickiness (lost-update guard). Many call sites load→mutate→save
    # goals_mem.json WITHOUT the GoalArbiter (the arbiter's own header notes "dozens of
    # uncoordinated call sites"), so a writer holding a STALE in_progress copy can
    # overwrite a goal another path already completed — observed live: a satiety-closed
    # goal kept reverting to in_progress and being re-pursued (barren×25). Reconcile the
    # outgoing goals against the current on-disk terminal states here, at the single
    # save chokepoint, so a terminal goal can NEVER be silently downgraded by a stale
    # copy. (Removal still works — only goals present in BOTH are protected.)
    try:
        _existing = load_json(GOALS_FILE, default_type=list) or []
        _terminal: Dict[str, Dict] = {}

        def _collect(nodes):
            for n in (nodes or []):
                if isinstance(n, dict):
                    _gid = n.get("id") or n.get("title") or n.get("name")
                    if _gid and str(n.get("status", "")).lower() in _TERMINAL_STATUSES:
                        _terminal[_gid] = n
                    _collect(n.get("subgoals"))

        _collect(_existing)
        if _terminal:
            def _protect(nodes):
                for n in (nodes or []):
                    if isinstance(n, dict):
                        _gid = n.get("id") or n.get("title") or n.get("name")
                        _prev = _terminal.get(_gid)
                        if _prev is not None and str(n.get("status", "")).lower() not in _TERMINAL_STATUSES:
                            # A stale copy is trying to re-open a terminal goal — restore it.
                            n["status"] = _prev.get("status")
                            if _prev.get("completed_timestamp"):
                                n["completed_timestamp"] = _prev["completed_timestamp"]
                            _log.info("[goals] blocked re-open of terminal goal "
                                      f"{str(_gid)[:48]!r} ({_prev.get('status')}) by a stale copy.")
                        _protect(n.get("subgoals"))
            _protect(goals)
    except Exception as _e:
        record_failure("goals.save_goals", _e)

    # Sort by last_updated (fallback to timestamp), newest first
    def _key(g: Dict) -> str:
        return str(g.get("last_updated", g.get("timestamp", "")))

    goals_sorted = sorted(goals, key=_key, reverse=True)
    overflow = goals_sorted[MAX_GOALS:]
    if overflow:
        # Archive displaced goals rather than silently deleting them
        try:
            archived = load_json(COMPLETED_GOALS_FILE, default_type=list) or []
            if not isinstance(archived, list):
                archived = []
            for g in overflow:
                if not any(a.get("title") == g.get("title") and
                           a.get("name") == g.get("name") for a in archived):
                    archived.append(g)
            save_json(COMPLETED_GOALS_FILE, archived[-200:])
        except Exception as _e:
            record_failure("goals.save_goals.2", _e)
    save_json(GOALS_FILE, goals_sorted[:MAX_GOALS])


# Public actions

def add_goal(goal: Dict, parent_name: Optional[str] = None) -> Dict:
    full = load_goals()
    g = dict(goal)
    try:
        from brain.cognition.planning.goal_comprehension import hydrate_goal_model
        g = hydrate_goal_model(g)
    except Exception as exc:
        record_failure("goals.add_goal.hydrate", exc)
    now = now_iso_z()
    g.setdefault("status", "pending")
    g.setdefault("timestamp", now)
    g.setdefault("last_updated", now)
    g.setdefault("history", [{"event": "created", "timestamp": now}])

    parent = _find_goal_by_name(full, parent_name) if parent_name else None
    if not parent:
        parent = ensure_immediate_actions_bucket(full)

    _attach_child(parent, g)
    save_goals(full)
    return g


def create_micro_goal_for_action(action_desc: str, parent_name: Optional[str] = None) -> Dict:
    return add_goal({
        "name": action_desc.strip()[:140],
        "tier": "micro_goal",
        "status": "in_progress",
        "expected_cycles": 1,
        "history": [f"Created as micro-goal for action: {action_desc}"],
    }, parent_name=parent_name)


def mark_goal_status_by_name(name: str, new_status: str) -> bool:
    # Atomic load→mutate→save through the GoalArbiter (status write; daemon-ready).
    # Deferred import avoids the goals↔goal_arbiter import cycle. Phase 1.
    from brain.cognition.planning import goal_arbiter
    found = {"ok": False}

    def _mut(full):
        target = _find_goal_by_name(full, name)
        if target:
            target["status"] = new_status
            target["last_updated"] = now_iso_z()
            if new_status == "completed":
                target["completed_timestamp"] = now_iso_z()
            found["ok"] = True
        return full

    goal_arbiter.apply(_mut, source="mark_goal_status_by_name")
    return found["ok"]


# Tree utils

def merge_updated_goal_into_tree(tree: List[Dict], updated: Dict) -> List[Dict]:
    """
    Merge an updated goal node into the full tree by matching id, then (name, timestamp).
    Replaces the first match found; recurses into subgoals. If not found, appends at top level.
    """
    updated = _reconcile_to_disk_terminal(updated)

    def match(a: Dict, b: Dict) -> bool:
        # Id is authoritative: the same goal re-created at a different hour has a
        # new timestamp, and (name, timestamp) matching appended a duplicate
        # record each time (FINDINGS 2026-06-12 §1B: same id stored 8×).
        if b.get("id") and a.get("id"):
            return a.get("id") == b.get("id")
        return (a.get("name") == b.get("name")) and (
            a.get("timestamp") == b.get("timestamp") or not b.get("timestamp")
        )

    def replace_in_list(lst: List[Dict]) -> Tuple[List[Dict], bool]:
        out: List[Dict] = []
        replaced = False
        for g in lst:
            if not replaced and match(g, updated):
                merged = {**g, **updated}
                out.append(merged)
                replaced = True
            else:
                subs = g.get("subgoals")
                if isinstance(subs, list):
                    new_sub, sub_replaced = replace_in_list(subs)
                    if sub_replaced:
                        gg = dict(g)
                        gg["subgoals"] = new_sub
                        out.append(gg)
                        replaced = True
                        continue
                out.append(g)
        return out, replaced

    new_tree, did = replace_in_list(tree)
    if not did:
        new_tree.append(updated)
    return new_tree


# Pruning

def prune_goals(goals: List[Dict]) -> List[Dict]:
    def _parse_iso(ts: str) -> Optional[datetime]:
        try:
            if ts and isinstance(ts, str):
                # accept trailing Z
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                return datetime.fromisoformat(ts)
        except Exception as _e:
            record_failure("goals.prune_goals._parse_iso", _e)
        return None

    def is_active(goal: Dict) -> bool:
        if goal.get("tier") == "micro_goal":
            try:
                ts = goal.get("last_updated", goal.get("timestamp"))
                dt = _parse_iso(ts)
                if dt:
                    age = (datetime.now(timezone.utc) - dt).total_seconds()
                    if goal.get("status") == "completed" and age > 600:
                        return False
                    if goal.get("status", "pending") in ("pending", "blocked") and age > 1800:
                        return False
            except Exception as _e:
                record_failure("goals.prune_goals.is_active", _e)
        raw_status = goal.get("status")
        status = str(raw_status).strip().lower() if raw_status is not None else ""
        # Retire any goal in a terminal state (completed/failed/abandoned/cancelled).
        if status in _TERMINAL_STATUSES:
            return False
        # Invalid goals (missing/empty status) are retire-eligible ONLY when nothing
        # is legitimately in flight (no milestones, no subgoals). A real in-progress
        # goal that merely lacks a status field is kept.
        if status == "":
            return bool(goal.get("milestones")) or bool(goal.get("subgoals"))
        return True

    def prune(goal: Dict) -> Dict:
        subs = goal.get("subgoals")
        if isinstance(subs, list):
            goal["subgoals"] = [prune(sub) for sub in subs if is_active(sub)]
        return goal

    return [prune(g) for g in goals if is_active(g)]


# LLM helpers

def _rule_based_decompose(goal: Dict) -> List[Dict]:
    """Keyword-based subgoal decomposition when LLM is unavailable."""
    name = (goal.get("name") or goal.get("description") or goal.get("title") or "goal").lower()
    n = now_iso_z()

    # File search (benchmark_realignment.md F4): search-shaped goals decompose
    # into search → grep → summarize, mirroring _symbolic_plan's template, so a
    # goal like B3's "Find the word 'reaper' in any brain file" gets a plan its
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


def _rule_based_accomplish(goal: Dict) -> bool:
    """
    Check working memory for evidence this goal was recently completed.
    Returns True only if a clear success signal is found.
    """
    name = (goal.get("name") or "").lower()
    name_words = {w for w in name.split() if len(w) > 4}
    try:
        from brain.utils.json_utils import load_json as _lj
        from brain.paths import WORKING_MEMORY_FILE as _WMF
        wm = _lj(_WMF, default_type=list) or []
        for e in wm[-15:]:
            txt = str(e.get("content", e) if isinstance(e, dict) else e).lower()
            if ("✅" in txt or "accomplished" in txt or "completed" in txt):
                if any(w in txt for w in name_words):
                    return True
    except Exception as _e:
        record_failure("goals._rule_based_accomplish", _e)
    return False


def decompose_goal(goal: Dict) -> List[Dict]:
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


# P2 — production goals are artifact-gated and fail-able. The unit is *cycles*
# (the diagnosed run did ~10⁴ cycles at cycle_sleep≈20s). 200 is long enough that
# a genuine plan→execute→write attempt isn't guillotined, short enough that a full
# life surfaces many deadline evaluations so goals_failed actually moves off 0.
# Reuses the same epoch as the P6 reconciler so there is one cadence constant.
PRODUCTION_DEADLINE_CYCLES = 200


def _is_artifact_gated(goal: Dict) -> bool:
    """A goal that may complete ONLY when a real durable effect was recorded for it."""
    if not isinstance(goal, dict):
        return False
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    if bool(goal.get("requires_artifact") or spec.get("requires_artifact")):
        return True
    if str(goal.get("driven_by") or spec.get("driven_by") or "").lower() == "output_producing":
        return True
    text = " ".join(str(goal.get(k) or spec.get(k) or "") for k in ("title", "name", "description")).lower()
    return any(word in text for word in (
        "write ", "build ", "create ", "make ", "compose ", "publish ",
        "implement ", "produce ", "draft ",
    ))


def _definition_of_done(goal: Dict) -> List[Dict]:
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    raw = goal.get("definition_of_done") or spec.get("definition_of_done") or []
    out: List[Dict] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("criterion"):
            out.append(item)
        elif str(item or "").strip():
            out.append({"criterion": str(item).strip(), "kind": "quality", "met": False})
    return out


def _criteria_evidence_met(goal: Dict) -> bool:
    """Check persisted evidence, never a bare model assertion."""
    criteria = _definition_of_done(goal)
    if not criteria:
        return False
    gid = str(goal.get("id") or "")
    produced = False
    if gid:
        try:
            from brain.agency.effect_ledger import has_qualifying_effect
            produced = has_qualifying_effect(gid, goal)
        except Exception:
            pass
    milestones = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
    all_milestones = bool(milestones) and all(bool(m.get("met")) for m in milestones)
    evidence = goal.get("completion_evidence") or {}
    checks = evidence.get("criteria") if isinstance(evidence, dict) else []

    def _observed(text: str) -> bool:
        words = {w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())}
        if len(words) < 2:
            return False
        try:
            from brain.paths import WORKING_MEMORY_FILE
            memory = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        except Exception:
            memory = []
        for entry in memory[-40:] if isinstance(memory, list) else []:
            content = str(entry.get("content", entry) if isinstance(entry, dict) else entry).lower()
            if len(words & set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", content))) >= 2:
                return True
        return False

    checked = {
        str(row.get("criterion") or ""): (
            bool(row.get("met"))
            and bool(row.get("evidence"))
            and _observed(str(row.get("evidence") or ""))
        )
        for row in checks or [] if isinstance(row, dict)
    }
    for criterion in criteria:
        kind = str(criterion.get("kind") or "").lower()
        text = str(criterion.get("criterion") or "")
        met = bool(criterion.get("met"))
        if kind in {"artifact", "sections", "validation"} and produced:
            met = True
        if all_milestones:
            met = True
        if checked.get(text):
            met = True
        if not met:
            return False
    return True


def try_to_accomplish(goal: Dict) -> bool:
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
                from brain.cognition.intrinsic_goals import mark_aspiration_contribution
                mark_aspiration_contribution(goal.get("driven_by", ""))
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

def pursue_goal(goal: Dict) -> None:
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


def achievement_significance(goal: Optional[Dict]) -> float:
    """I17 — felt achievement scaled to real significance, so completion/milestone joy
    reflects what was *actually* accomplished (objective-met × difficulty × novelty),
    never a flat per-step drip that rebuilds "feels productive without accomplishing".
    Returns a multiplier centred ~1.0, clamped to [0.4, 1.3]. Objective-met is the gate
    (enforced by mark_goal_completed); this only shapes the *magnitude*."""
    if not isinstance(goal, dict):
        return 1.0
    # Difficulty — ambition (tier) × scope (milestones/plan) × struggle (attempts).
    _TIER_W = {"existential": 1.25, "core": 1.12, "identity": 1.12,
               "growth": 1.0, "exploratory": 0.92, "minor": 0.8, "trivial": 0.7}
    tier = str(goal.get("tier") or goal.get("kind") or "").lower()
    diff = _TIER_W.get(tier, 1.0)
    ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
    diff *= 1.0 + min(0.25, 0.05 * len(ms))      # more success criteria = bigger deal
    plan = [p for p in (goal.get("plan") or []) if isinstance(p, dict)]
    diff *= 1.0 + min(0.15, 0.02 * len(plan))    # longer plan = more work
    # Struggle — a goal that resisted and was finally met is a bigger accomplishment.
    attempts = int(goal.get("_completion_attempts", 0) or 0)
    sa = goal.get("_step_attempts")
    if isinstance(sa, dict) and sa:
        attempts = max(attempts, max(int(v or 0) for v in sa.values()))
    diff *= 1.0 + min(0.20, 0.06 * attempts)
    # Novelty — a first-of-its-kind / curiosity-driven goal lands harder than a routine
    # repeat. Proxy: intrinsic-driver tag carries a mild bonus.
    nov = 1.0
    driver = str(goal.get("driven_by") or "").lower()
    if any(k in driver for k in ("curiosity", "intrinsic", "explor", "novel")):
        nov = 1.08
    return max(0.4, min(1.3, diff * nov))


def mark_goal_completed(goal: Dict, context: Optional[Dict] = None) -> None:
    # Single-chokepoint guard against HOLLOW completion. A goal with explicit success
    # milestones is only "completed" when its objective is actually met — finishing the
    # plan steps is not enough. This protects every caller (pursue_goal, action_gate, …)
    # and, crucially, keeps the completion REWARD honest: the +1.0 reward_signal below
    # used to fire even when the objective was unmet, so hollow goals were rewarded and
    # the reward stream looked "steady" while hiding the difference between real and fake
    # accomplishment. No objective met → no completion, no reward.
    # Idempotence: completing an already-completed goal must be a no-op. The
    # zombie loop in the 2.7k-cycle audit ("Write a cognitive function..."
    # completed 3×, median_seconds_to_complete=0.0) was re-marking resurrected
    # goals whose milestones were already met — each pass re-fired the +1.0
    # reward and re-archived a duplicate.
    if goal.get("status") == "completed":
        return
    _ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
    if _ms and not all(m.get("met") for m in _ms):
        try:
            from brain.cognition.planning.env_snapshot import apply_milestone_updates
            if context:
                apply_milestone_updates(context)
                _ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
        except Exception as _e:
            record_failure("goals.mark_goal_completed", _e)
        if _ms and not all(m.get("met") for m in _ms):
            _unmet = sum(1 for m in _ms if not m.get("met"))
            log_activity(f"[goals] Refusing hollow completion of "
                         f"{(goal.get('title') or goal.get('name') or '?')!r} — "
                         f"{_unmet}/{len(_ms)} milestone(s) unmet; not marking complete, not rewarding.")
            return
    goal["status"] = "completed"
    now = now_iso_z()
    goal["completed_timestamp"] = now
    goal["last_updated"] = now
    goal.setdefault("history", []).append({"event": "completed", "timestamp": now})
    # Close out any still-pending plan steps so a completed goal never carries
    # live steps (audit found completed goals with steps 2/3 still "pending",
    # which the executive then tried to advance — the re-plan/stall loop).
    for _st in (goal.get("plan") or []):
        if isinstance(_st, dict) and _st.get("status") not in TERMINAL_STEP_STATUSES:
            _st["status"] = "skipped"
            _st["skip_reason"] = "goal completed"
    _sig = achievement_significance(goal)   # I17 — joy scaled to real significance
    # P8 — for an artifact-gated goal, let the REAL produced-effect significance
    # drive the recorded metric, so mean_significance reflects produced work rather
    # than the self-asserted achievement multiplier (which gave the run its 0.0).
    try:
        if _is_artifact_gated(goal) and goal.get("id"):
            from brain.agency.effect_ledger import significance_for_goal
            _eff_sig = significance_for_goal(str(goal.get("id")))
            if _eff_sig > 0.0:
                _sig = max(_sig, _eff_sig)
    except Exception as _e:
        record_failure("goals.mark_goal_completed.effsig", _e)
    _ctx = context or {}
    try:
        from brain.cognition.action_accounting import cycle_produced_goal_action
        _grounded = bool(_ms and all(m.get("met") for m in _ms)) or cycle_produced_goal_action(_ctx)
    except Exception:
        _grounded = bool(_ms and all(m.get("met") for m in _ms))
    _grounded = _grounded or bool(_ctx.get("_verified_artifact_this_cycle"))
    if _grounded:
        release_reward_signal(
            context=_ctx,
            signal_type="reward_signal",
            actual_reward=round(1.0 * _sig, 3),
            expected_reward=0.7,
            effort=0.4,
            mode="phasic",
        )
    else:
        log_activity(
            f"[goals] Completed {(goal.get('title') or goal.get('name') or '?')!r} "
            "without completion reward: no environment delta or verified artifact."
        )
    # Archive to completed goals file so Signal B can fire. Replace any prior
    # record with the same id — re-completion of a resurrected goal was appending
    # the same id repeatedly (FINDINGS 2026-06-12 §1B: g_3a933aec31 stored 8×).
    try:
        existing = load_json(COMPLETED_GOALS_FILE, default_type=list) or []
        _arch_id = goal.get("id")
        if _arch_id:
            existing = [a for a in existing
                        if not (isinstance(a, dict) and a.get("id") == _arch_id)]
        existing.append(goal)
        save_json(COMPLETED_GOALS_FILE, existing[-500:])
    except Exception as _e:
        record_failure("goals.mark_goal_completed.2", _e)

    # Completion is terminal (BEHAVIOR_FIX_PLAN 2.2): remove the goal from the
    # goals_mem.json active set in the same write that archives it, so it can
    # never exist in both {active, recently_completed} at once (audit §7 found
    # "Write a cognitive function" simultaneously active and completed).
    try:
        _gid = goal.get("id")
        _gtitle = (goal.get("title") or goal.get("name") or "").strip().lower()

        def _same(n: Dict) -> bool:
            if _gid and n.get("id") == _gid:
                return True
            _nt = (n.get("title") or n.get("name") or "").strip().lower()
            return bool(_gtitle) and _nt == _gtitle

        _removed = [0]

        def _drop(nodes: List[Dict]) -> List[Dict]:
            kept = []
            for n in nodes:
                if isinstance(n, dict):
                    if _same(n):
                        _removed[0] += 1
                        continue
                    if isinstance(n.get("subgoals"), list):
                        n["subgoals"] = _drop(n["subgoals"])
                kept.append(n)
            return kept

        _pruned = _drop(load_goals())
        if _removed[0]:
            save_goals(_pruned)
            log_activity(f"[goals] Removed completed goal '{str(_gtitle)[:60]}' from active set.")
    except Exception as _e:
        record_failure("goals.mark_goal_completed.3", _e)

    # Mirror the close into the v2 GoalsAPI store. committed_goals_v1 rebuilds
    # the context goal from v2 every cycle, so without this a goal completed on
    # the v1 side is resurrected as "in_progress" forever (FINDINGS 2026-06-12 §1).
    try:
        import brain.goal_io as goal_io
        if goal.get("id"):
            goal_io.close_goal_v2(goal["id"], status="DONE", reason="mark_goal_completed")
    except Exception as _e:
        record_failure("goals.mark_goal_completed.v2sync", _e)
    # Phase E outcome metric — record at this single completion chokepoint.
    try:
        from brain.cognition.planning.outcome_metrics import record_completion
        _secs = None
        _created = goal.get("created_at") or goal.get("timestamp")
        if isinstance(_created, str) and _created:
            try:
                _ct = datetime.fromisoformat(_created.replace("Z", "+00:00"))
                _secs = (datetime.now(timezone.utc) - _ct).total_seconds()
            except Exception:
                _secs = None
        record_completion(significance=_sig, seconds_to_complete=_secs)
    except Exception as _e:
        record_failure("goals.mark_goal_completed.4", _e)
    update_working_memory(f"🎉 Completed goal: {goal.get('name')}")
    log_activity(f"✅ Marked goal '{goal.get('name')}' as completed.")

    # Auto-resolve threads whose title overlaps significantly with this goal.
    # Threads of inquiry are "done" when the goal they drove is complete.
    try:
        _goal_name = (goal.get("title") or goal.get("name") or "").lower()
        if _goal_name:
            _goal_tokens = {
                w.strip(".,;:!?\"'").lower()
                for w in _goal_name.split()
                if len(w) > 3
            }
            from brain.cognition.threads import load_threads, resolve_thread
            _threads = load_threads()
            _ctx = context or {}
            for _t in _threads:
                if _t.get("status") != "alive":
                    continue
                _title_tokens = {
                    w.strip(".,;:!?\"'").lower()
                    for w in (_t.get("title") or "").split()
                    if len(w) > 3
                }
                _overlap = _goal_tokens & _title_tokens
                if len(_overlap) >= 2 or (len(_goal_tokens) <= 3 and _overlap):
                    resolve_thread(_t["id"], f"Resolved via completed goal: {goal.get('name')}", _ctx)
                    log_activity(f"[threads] Auto-resolved thread '{_t['title']}' — goal completed.")
    except Exception as _e:
        record_failure("goals.mark_goal_completed.5", _e)

    # Fix 6.4 (explore_loop_fix_plan.md) — spawn-thrash guard. Record THIS title in
    # the intrinsic-goals cooldown BEFORE the continuity hook runs, so the goal the
    # hook spawns can't immediately re-commit the very title we just completed
    # (close → spawn-same → close churn). The hook bypasses the rate limiter but
    # still honours _RECENTLY_COMPLETED.
    try:
        import time as _time
        from brain.cognition.intrinsic_goals import _RECENTLY_COMPLETED, _persist_recently_completed
        _done_title = (goal.get("title") or goal.get("name") or "").strip().lower()
        if _done_title:
            _RECENTLY_COMPLETED[_done_title] = _time.time()
            _persist_recently_completed()
    except Exception as _e:
        record_failure("goals.mark_goal_completed.6", _e)

    # P5 / G2 — intake→output laddering. When an intake (world_knowledge) goal
    # closes, queue its topic so the next making goal turns X into output instead
    # of the loop re-understanding X once its cooldown lapses.
    try:
        if str(goal.get("driven_by") or "").lower() == "world_knowledge":
            from brain.cognition.intrinsic_goals import note_intake_completed
            _raw = goal.get("title") or goal.get("name") or ""
            for _pfx in ("understand ", "follow-up on ", "open question:", "the causes of ",
                         "pick up my thread on "):
                if _raw.lower().startswith(_pfx):
                    _raw = _raw[len(_pfx):]
                    break
            _topic = _raw.replace(" more deeply", "").strip(" :?.")
            if _topic:
                note_intake_completed(_topic)
    except Exception as _e:
        record_failure("goals.mark_goal_completed.ladder", _e)

    # Goal-continuity hook: immediately generate and commit the next goal so
    # Orrin doesn't sit idle after completing one. Clear the just-finished goal
    # from context, reset the intrinsic-goals rate-limiter, then call
    # generate_intrinsic_goals — it will auto-commit the top candidate.
    try:
        _ctx = context or {}
        _ctx["committed_goal"] = None  # slot is now open
        import brain.cognition.intrinsic_goals as _ig
        _ig._LAST_INTRINSIC_TS = 0.0   # bypass rate limiter for this one call
        _new_goals = _ig.generate_intrinsic_goals(_ctx)
        if _new_goals:
            log_activity(
                f"[goals] Goal-continuity: spawned '{_new_goals[0].get('title','?')[:60]}' "
                f"after completing '{goal.get('name','?')[:60]}'."
            )
        else:
            log_activity("[goals] Goal-continuity hook ran but no new goals were generated.")
    except Exception as _gc_e:
        log_activity(f"[goals] Goal-continuity hook error: {_gc_e}")

    # Self-belief falsification: success in a "weak" area is evidence against
    # the weakness belief — revise it downward.
    _revise_weak_area_beliefs(goal)


def mark_goal_failed(goal: Dict, reason: str = "", context: Optional[Dict] = None) -> None:
    """
    Mark a goal as failed, write it to long-term memory, and inflict emotional penalty_signal.
    This should feel like a genuine setback — impasse_signal and negative_valence, not just a log line.
    """
    goal["status"] = "failed"
    now = now_iso_z()
    goal["failed_timestamp"] = now
    goal["last_updated"] = now
    goal.setdefault("history", []).append({
        "event": "failed",
        "reason": reason or "unknown",
        "timestamp": now,
    })

    # Mirror into the v2 store (no-op when the failure event CAME from v2 — the
    # goal is already terminal there). Same resurrection guard as completion.
    try:
        import brain.goal_io as goal_io
        if goal.get("id"):
            goal_io.close_goal_v2(goal["id"], status="FAILED", reason=reason or "mark_goal_failed")
    except Exception as _e:
        record_failure("goals.mark_goal_failed.v2sync", _e)

    # Phase E outcome metric — record at this single failure chokepoint.
    # Aliased import: a bare `record_failure` here would shadow the two-arg
    # failure-counter version for the whole function scope, so an exception in
    # the metrics call would explode inside this handler and skip the
    # long-memory write and emotional penalty below.
    try:
        from brain.cognition.planning.outcome_metrics import record_failure as record_outcome_failure
        record_outcome_failure()
    except Exception as _e:
        record_failure("goals.mark_goal_failed", _e)

    goal_name = goal.get("name") or goal.get("title") or "unknown goal"

    # Master plan 4.3: failing a goal with an active commitment costs in
    # proportion to how dearly the resolve was held, and the failure memory
    # points back at the moment of resolve so the failure ledger can see
    # WHICH KIND of vow keeps breaking.
    commitment = None
    penalty_scale = 1.0
    commitment_refs: Optional[List[str]] = None
    try:
        from brain.cognition.will import find_commitment_for_goal
        commitment = find_commitment_for_goal(str(goal_name), context)
        if isinstance(commitment, dict):
            _cstrength = float(
                commitment.get("initial_strength", commitment.get("strength", 1.0)) or 1.0
            )
            penalty_scale = 0.5 + _cstrength          # 0.75 (lightly held) .. 1.5 (dearly held)
            if commitment.get("wm_id"):
                commitment_refs = [str(commitment["wm_id"])]
            # The broken vow releases its shield — resolve doesn't outlive its goal.
            if isinstance(context, dict):
                _live = context.get("_commitment")
                if isinstance(_live, dict) and _live.get("id") == commitment.get("id"):
                    context.pop("_commitment", None)
                    context.pop("_commitment_bias", None)
    except Exception as _e:
        record_failure("goals.mark_goal_failed.commitment", _e)

    # Write to long-term memory so it's never forgotten
    # Uses update_long_memory so emotional_context snapshot and importance boost apply.
    try:
        from brain.cog_memory.long_memory import update_long_memory
        content = f"Failed goal: {goal_name}. Reason: {reason or 'no reason recorded'}."
        if commitment is not None:
            content += f" (a commitment was broken — strength {penalty_scale - 0.5:.2f})"
        update_long_memory(
            content,
            emotion="impasse_signal",
            event_type="goal_failure",
            importance=3,
            priority=3,
            related_memory_ids=commitment_refs,
            context=context,
        )
    except Exception as _e:
        log_activity(f"⚠️ Could not write goal failure to long memory: {_e}")

    # Emotional penalty_signal: impasse_signal + negative_valence spike —
    # strength-weighted when a commitment was broken (4.3), flat otherwise.
    release_reward_signal(
        context=context if isinstance(context, dict) else {},
        signal_type="reward_signal",
        actual_reward=0.0,
        expected_reward=0.8,
        effort=0.7,
        mode="phasic",
    )
    if isinstance(context, dict):
        emo = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            core["impasse_signal"] = min(1.0, float(core.get("impasse_signal", 0.0)) + 0.4 * penalty_scale)
            core["negative_valence"]     = min(1.0, float(core.get("negative_valence",     0.0)) + 0.3 * penalty_scale)
            core["confidence"]  = max(0.0, float(core.get("confidence",  0.5)) - 0.25 * penalty_scale)
            if "core_signals" in emo:
                emo["core_signals"] = core
            else:
                emo.update(core)
        context["affect_state"] = emo

    update_working_memory({
        "content": f"💔 Goal failed: {goal_name}. {reason or ''}".strip(),
        "event_type": "goal_failure",
        "importance": 3,
        "priority": 3,
    })
    log_activity(f"❌ Goal '{goal_name}' marked failed. Reason: {reason or 'none'}")


def fail_overdue_artifact_goals(context: Optional[Dict] = None) -> int:
    """P2 — timeout → failure for artifact-gated goals. Walks the goal store; an
    output_producing / requires_artifact goal that has been alive past its
    deadline_cycles WITHOUT a qualifying effect is routed into the existing
    mark_goal_failed path (reason="no_artifact_by_deadline"). This is what turns the
    run's hollow "0 failures" into a meaningful non-zero — a make-things goal that
    produced nothing is a real, staked failure, not a quiet fade.

    Cadence is measured in cognitive cycles: each goal's first observation cycle is
    stamped on first sight, and the deadline is measured from there. Run on the same
    low cadence as the P6 reconciler (every PRODUCTION_DEADLINE_CYCLES cycles)."""
    try:
        from brain.utils.get_cycle_count import get_cycle_count
        cur = int(get_cycle_count() or 0)
    except Exception:
        return 0
    try:
        goals = load_goals()
    except Exception:
        return 0
    if not isinstance(goals, list):
        return 0

    from brain.agency.effect_ledger import has_qualifying_effect
    failed: List[Dict] = []
    changed = False

    def _walk(nodes: List[Dict]) -> None:
        nonlocal changed
        for g in nodes:
            if not isinstance(g, dict):
                continue
            status = g.get("status")
            if _is_artifact_gated(g) and status in ("proposed", "pending", "in_progress", "active", "committed"):
                seen = g.get("_artifact_first_seen_cycle")
                if seen is None:
                    g["_artifact_first_seen_cycle"] = cur
                    changed = True
                else:
                    deadline = int(g.get("deadline_cycles") or PRODUCTION_DEADLINE_CYCLES)
                    gid = str(g.get("id") or "")
                    overdue = (cur - int(seen)) > deadline
                    if overdue and not (gid and has_qualifying_effect(gid, g)):
                        failed.append(g)
            _walk(g.get("subgoals") or [])

    _walk(goals)
    if changed and not failed:
        try:
            save_goals(goals)
        except Exception as _e:
            record_failure("goals.fail_overdue_artifact_goals.stamp", _e)
    for g in failed:
        try:
            mark_goal_failed(g, reason="no_artifact_by_deadline", context=context)
        except Exception as _e:
            record_failure("goals.fail_overdue_artifact_goals.fail", _e)
    if failed:
        log_activity(f"[goals] Failed {len(failed)} artifact-gated goal(s) past deadline "
                     f"with no produced artifact.")
    return len(failed)


# Focus selection

def select_focus_goals() -> Dict[str, Optional[Dict]]:
    """
    Load goals, select focus goals, and write to FOCUS_GOAL.
    Returns the focus goal dictionary.
    """
    goals = load_json(GOALS_FILE, default_type=list)
    if not isinstance(goals, list):
        goals = []

    def find_focus(goal_list: List[Dict], tier_names: List[str], collected: List[Dict], max_count: int) -> List[Dict]:
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

def goal_function_already_exists(goal_tree: Optional[List[Dict]], function_name: Optional[str]) -> bool:
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
    completed_goals: List[Dict] = []

    # Ensure completed goals file exists as a list
    existing_completed = load_json(COMPLETED_GOALS_FILE, default_type=list)
    if not isinstance(existing_completed, list):
        existing_completed = []
        save_json(COMPLETED_GOALS_FILE, existing_completed)

    def check_and_complete(goal: Dict) -> bool:
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
                mark_goal_completed(goal)
                completed_goals.append(goal)
                changed = True
                return True
            return all_steps_done

        subs = goal.get("subgoals")
        if isinstance(subs, list) and subs:
            all_done = all(check_and_complete(sub) for sub in subs)
            if all_done and goal.get("status") != "completed":
                mark_goal_completed(goal)
                completed_goals.append(goal)
                changed = True
                return True
            return all_done
        else:
            # Atomic: done only if explicitly completed
            return goal.get("status") == "completed"

    for g in goals:
        check_and_complete(g)

    if changed:
        save_goals(goals)
        update_working_memory("🗂️ Ran maybe_complete_goals: marked some goals as completed.")
        # Append newly completed to completed goals file
        existing_completed.extend(completed_goals)
        save_json(COMPLETED_GOALS_FILE, existing_completed)
    else:
        update_working_memory("maybe_complete_goals: No new goals completed.")

    return changed
