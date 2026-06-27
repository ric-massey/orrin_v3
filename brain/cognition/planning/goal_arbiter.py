# brain/cognition/planning/goal_arbiter.py
#
# GoalArbiter — the single convergence point for goal-state mutations.
#
# THE PROBLEM IT SOLVES
# Goal state (status, plan-step status, milestones, _step_attempts) is mutated
# from ~dozens of uncoordinated call sites that each do load_goals -> mutate ->
# save_goals with no lock. Two writers that interleave (today: the loop + a
# repair/action path; tomorrow: a background Executive daemon) race on the same
# file exactly the way affect writers used to race on affect_state — the
# "split-brain" failure the AffectArbiter was built to fix. This is the goal half.
#
# THE MODEL: one coordinated, lock-guarded chokepoint (mirrors affect/arbiter.py)
#   * apply(mutator, source) atomically load -> mutate -> save under a reentrant
#     lock, so no two writers can interleave a load/save.
#   * Daemons / other threads that must NOT touch the file directly call
#     propose(...) to enqueue a mutation onto a thread-safe inbox; the main loop
#     drains and applies it via commit(). This is the single mechanism that makes
#     a Phase-5 continuous Executive daemon safe — a config flip, not a rewrite.
#
# DESIGN NOTE (dual_process_loop.md §7B, §20.3): this module is intentionally
# self-contained and side-effect-free until a caller opts in. Building it now
# (Phase 1) has present value — it removes today's uncoordinated-write race once
# the highest-risk sites (status / completion / failure) are migrated through it —
# and it is the prerequisite for the continuous Executive daemon (Phase 5).
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from brain.cognition.planning.goals import load_goals, save_goals
from brain.utils.log import log_activity

# Reentrant so a mutator that itself calls back into apply() (or a convenience
# helper that wraps apply) does not deadlock.
_goal_lock = threading.RLock()

# Thread-safe inbox for mutations proposed off the main loop (daemons). Drained by
# commit() on the main loop, mirroring AffectArbiter's _inbox. Capped so a stuck
# producer cannot grow it without bound.
_inbox_lock = threading.Lock()
_inbox: List[Dict[str, Any]] = []
_INBOX_CAP = 256

# Type of a mutator: receives the live goals list, returns the list to persist.
Mutator = Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]


def apply(mutator: Mutator, *, source: str = "") -> List[Dict[str, Any]]:
    """Atomically load → mutate → save the goal store under the arbiter lock.

    `mutator(goals) -> goals` must be pure-ish: mutate the list in place (or return
    a new one) and return the list to persist. Returns the persisted goals.

    This is the chokepoint: every goal write should ultimately go through here so
    no two writers can interleave a load/save.
    """
    with _goal_lock:
        goals = load_goals()
        try:
            result = mutator(goals)
        except Exception as exc:  # never let a bad mutator corrupt or crash the loop
            log_activity(f"[goal_arbiter] mutator from {source!r} failed: {exc}")
            return goals
        if not isinstance(result, list):
            log_activity(f"[goal_arbiter] mutator from {source!r} returned non-list; ignoring")
            return goals
        save_goals(result)
        return result


# ── Convenience helpers (thin wrappers over apply) ────────────────────────────
# These name the highest-risk mutations the spec migrates first (status /
# completion / failure / step advance / milestone), so call sites read clearly and
# every one of them is serialized through the same lock.

def _find(goals: List[Dict[str, Any]], goal_id: Any) -> Optional[Dict[str, Any]]:
    for g in goals:
        if isinstance(g, dict) and (g.get("id") == goal_id or g.get("title") == goal_id):
            return g
    return None


def set_status(goal_id: Any, status: str, *, source: str = "") -> List[Dict[str, Any]]:
    """Set a goal's status atomically (e.g. in_progress / completed / failed)."""
    def _mut(goals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        g = _find(goals, goal_id)
        if g is not None:
            g["status"] = str(status)
            _touch(g)
        return goals
    return apply(_mut, source=source or "set_status")


def advance_step(goal_id: Any, step_index: int, *, result: str = "",
                 source: str = "") -> List[Dict[str, Any]]:
    """Mark a plan step completed and stamp its result, atomically."""
    def _mut(goals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        g = _find(goals, goal_id)
        if g is not None:
            plan = g.get("plan")
            if isinstance(plan, list) and 0 <= step_index < len(plan) and isinstance(plan[step_index], dict):
                plan[step_index]["status"] = "completed"
                if result:
                    plan[step_index]["result"] = str(result)[:500]
                _touch(g)
        return goals
    return apply(_mut, source=source or "advance_step")


def update_goal(goal_id: Any, updates: Dict[str, Any], *, source: str = "") -> List[Dict[str, Any]]:
    """Shallow-merge `updates` into a goal atomically (status, milestones, etc.)."""
    def _mut(goals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        g = _find(goals, goal_id)
        if g is not None and isinstance(updates, dict):
            g.update(updates)
            _touch(g)
        return goals
    return apply(_mut, source=source or "update_goal")


def _touch(g: Dict[str, Any]) -> None:
    from datetime import datetime, timezone
    g["last_updated"] = datetime.now(timezone.utc).isoformat()


# ── Cross-thread propose / commit (Phase-5 daemon readiness) ──────────────────

def propose(mutation: Dict[str, Any]) -> None:
    """Queue a mutation from a non-main-loop thread. The main loop applies it in
    commit(). `mutation` = {"op": "set_status"|"advance_step"|"update_goal",
    "goal_id": ..., ...kwargs}. Off-thread writers MUST use this, never apply()."""
    if not isinstance(mutation, dict) or not mutation.get("op"):
        return
    with _inbox_lock:
        if len(_inbox) < _INBOX_CAP:
            _inbox.append(mutation)


_OPS = {
    "set_status": lambda m: set_status(m["goal_id"], m["status"], source=m.get("source", "inbox")),
    "advance_step": lambda m: advance_step(m["goal_id"], m["step_index"],
                                           result=m.get("result", ""), source=m.get("source", "inbox")),
    "update_goal": lambda m: update_goal(m["goal_id"], m.get("updates", {}), source=m.get("source", "inbox")),
}


def commit() -> int:
    """Drain and apply any proposed mutations from off-thread writers. Main-loop
    only. Returns the number applied. Safe to call every cycle (no-op when empty)."""
    with _inbox_lock:
        if not _inbox:
            return 0
        drained = list(_inbox)
        _inbox.clear()
    applied = 0
    for m in drained:
        fn = _OPS.get(str(m.get("op") or ""))
        if fn is None:
            continue
        try:
            fn(m)
            applied += 1
        except Exception as exc:
            log_activity(f"[goal_arbiter] inbox op {m.get('op')!r} failed: {exc}")
    return applied
