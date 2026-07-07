# brain/cognition/planning/goal_deadlines.py
# P2 deadline enforcement for artifact-gated goals, extracted from
# goal_outcomes.py (module-size decomposition; goal_outcomes re-exports
# fail_overdue_artifact_goals so callers keep their existing import path).
from __future__ import annotations

from typing import Any, Dict, List, Optional

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.cognition.planning.goal_store import load_goals, save_goals
from brain.cognition.planning.goal_criteria import (
    PRODUCTION_DEADLINE_CYCLES, _is_artifact_gated, is_aspiration,
)


def fail_overdue_artifact_goals(context: Optional[Dict[str, Any]] = None) -> int:
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
    except Exception as _e:
        record_failure("goals.fail_overdue_artifact_goals.cycle", _e)
        return 0
    try:
        goals = load_goals()
    except Exception as _e:
        record_failure("goals.fail_overdue_artifact_goals.load", _e)
        return 0
    if not isinstance(goals, list):
        return 0

    from brain.agency.effect_ledger import has_qualifying_effect
    failed: List[Dict[str, Any]] = []
    changed = False

    def _walk(nodes: List[Dict[str, Any]]) -> None:
        nonlocal changed
        for g in nodes:
            if not isinstance(g, dict):
                continue
            # F2 (2026-07-05): aspirations are directional — the deadline is a
            # task concept. aspiration-output_producing is artifact-gated by its
            # driven_by tag, so without this skip the walker re-fails it every pass.
            if is_aspiration(g):
                _walk(g.get("subgoals") or [])
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
    from brain.cognition.planning.goal_outcomes import mark_goal_failed
    for g in failed:
        try:
            mark_goal_failed(g, reason="no_artifact_by_deadline", context=context)
        except Exception as _e:
            record_failure("goals.fail_overdue_artifact_goals.fail", _e)
    if failed:
        log_activity(f"[goals] Failed {len(failed)} artifact-gated goal(s) past deadline "
                     f"with no produced artifact.")
    return len(failed)
