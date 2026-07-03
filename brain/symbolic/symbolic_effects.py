# brain/symbolic/symbolic_effects.py
#
# AR1 (CODEBASE_AUDIT_2026-07-01 D7): the symbolic engine makes real things —
# synthesized principles, crystallized skills, resolved experiments, established
# causal edges — and recorded ZERO production effects, so the goal/production/
# reward system was blind to all of it. This is the one seam every symbolic
# production point calls to make its work visible on the effect ledger.
#
# Deliberately thin: content composition + goal binding + a fail-safe wrapper.
# All honesty gates (novelty dedup, MIN_ARTIFACT_CHARS, the symbolic rate cap)
# live in the ledger itself, so a caller cannot over-credit by calling this more.
from __future__ import annotations

from typing import Any, Dict, Optional

from brain.utils.failure_counter import record_failure


def record_symbolic_effect(
    sub_kind: str,
    content: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """Record one symbolic production on the effect ledger.

    sub_kind: "rule" | "skill" | "experiment" | "causal_edge" (metadata.kind).
    Binds to the committed goal when a context with one is supplied; otherwise
    records ungoaled (still counts for production metrics). Returns the ledger
    row on credit, None otherwise — and never raises: a ledger failure must not
    break the symbolic engine.
    """
    goal_id: Optional[str] = None
    if isinstance(context, dict):
        try:
            from brain.cognition.global_workspace import bound_goal
            goal = bound_goal(context) or {}
            gid = goal.get("id") if isinstance(goal, dict) else None
            goal_id = str(gid) if gid else None
        except Exception as _e:
            record_failure("symbolic_effects.bound_goal", _e)
    if goal_id is None:
        # Contextless call chains (edge establishment, crystallization) still
        # attribute to the recently committed goal via the workspace mirror —
        # anonymous effects can't feed aspiration credit (2026-07-02: 116/150
        # rows had goal_id null for exactly this reason).
        try:
            from brain.cognition.global_workspace import last_bound_goal_id
            goal_id = last_bound_goal_id()
        except Exception as _e:
            record_failure("symbolic_effects.goal_mirror", _e)
    try:
        from brain.agency.effect_ledger import record_effect
        meta = dict(metadata or {})
        meta["kind"] = sub_kind
        return record_effect(
            "symbolic_artifact", content,
            goal_id=goal_id, context=context, metadata=meta,
        )
    except Exception as _e:
        record_failure("symbolic_effects.record", _e)
        return None
