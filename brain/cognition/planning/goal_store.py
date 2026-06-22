# brain/cognition/planning/goal_store.py
# The goal-tree store, extracted from goals.py (Phase 4.5C): the on-disk goal
# tree's read/write/mutate primitives — load_goals / save_goals (with terminal-
# status reconciliation), add_goal / create_micro_goal_for_action, the
# immediate-actions bucket, name lookup + child attach, status marking, merge of
# an updated node back into the tree, and prune_goals. This is the foundational
# leaf layer: it calls none of the higher-level goal logic (decompose / outcomes /
# pursuit), so those import from here without a cycle, and goals.py re-exports it.
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
from brain.paths import GOALS_FILE, COMPLETED_GOALS_FILE

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

