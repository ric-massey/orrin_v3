# brain/cognition/planning/survival_goals.py
# Phase 2 of GOALS_MASTER_PLAN_2026-06-23 — the autonomic→cortical recruiter.
#
# Phase 1 wired the ACUTE case: a critical vital signal preempts the committed
# goal for the cycle (transient). This is the CHRONIC case: a homeostatic alert
# that goes UNADDRESSED for enough cycles stops being a mere signal nudge and
# becomes a committed *intention* — a survival-tier restoration goal whose first
# step is the alert's own suggested_fn. The human pattern: "this depletion isn't a
# crisis, but it keeps coming back, so I'll make addressing it a goal."
#
# It reuses the alert's suggested_fn as the action, so it never invents capability
# Orrin lacks. Submission mirrors the intrinsic-goal path exactly (a kind="generic"
# proposed-goal dict appended to context["proposed_goals"], synced to GoalsAPI by
# goal_io.sync_proposed_goals), so the recruited goal competes in the normal
# commitment path — but at a survival-tier priority floor (executive._TIER_TURNS +
# top priority) so it can outrank growth goals without a special case in the selector.
#
# Refractory dedup: never recruit the same alert id while a goal for it is still
# open (this cycle's proposals OR a non-terminal goal already in the store).
from __future__ import annotations
import time
from typing import Any, Dict, Optional

from brain.core.runtime_log import get_logger
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

# Unaddressed cycles at which a chronic deficit recruits a goal. Higher than the
# Phase-1 acute preempt's 2-cycle hysteresis: recruitment is for the *persistent*
# sub-acute case, not a transient threshold spike.
RECRUIT_AFTER_CYCLES = 5

SURVIVAL_TIER = "survival"
# Top of the intrinsic 1..5 priority scale — the survival floor at the proposal-
# adoption step (intrinsic adoption picks the highest-priority proposal).
SURVIVAL_PRIORITY = 5

# Phase 3 — minimum interval before a satisfied (dormant) deficit may re-fire. The
# hunger-returns cycle must let the slot go back to other work between bouts, so a
# just-restored need can't immediately re-recruit. 30 minutes.
MIN_REFIRE_INTERVAL_S = 1800.0

# Statuses that mean a recruited goal is no longer "open" (so the deficit may be
# recruited again). 'dormant' is Phase-3's satiety-with-return state — re-recruitable,
# but only after MIN_REFIRE_INTERVAL_S (see _in_refractory).
_TERMINAL_STATUSES = frozenset({"completed", "abandoned", "failed", "dormant"})


def _homeostatic_signal(alert: Dict[str, Any]) -> str:
    """The drive a survival goal is `driven_by` — the alert's homeostatic signal.
    Prefer an explicit tag; else strip a severity suffix off the id
    ('resource_deficit_critical' → 'resource_deficit')."""
    for t in (alert.get("tags") or []):
        if t:
            return str(t)
    aid = str(alert.get("id") or "")
    for suf in ("_critical", "_warning"):
        if aid.endswith(suf):
            return aid[: -len(suf)]
    return aid or "homeostasis"


def build_survival_goal(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Construct the survival-tier restoration goal from an alert (no submission).

    tier='survival', driven_by=the homeostatic signal, first plan step = the
    alert's suggested_fn, title from its description. `recruit_aid` stamps the goal
    so the refractory dedup can find it later."""
    aid = str(alert.get("id") or "")
    desc = (str(alert.get("description") or aid or "a homeostatic deficit")).strip()
    first_step = (str(alert.get("suggested_fn") or "").strip()) or "rest"
    drive = _homeostatic_signal(alert)
    title = f"Restore: {desc}"[:120]
    return {
        "title": title,
        "name": title,  # v1 compat
        "description": (
            f"A homeostatic deficit ('{desc}') has gone unaddressed for several "
            f"cycles, so it has become an intention rather than just a signal. "
            f"Restore it — first action: {first_step}."
        )[:300],
        "priority": SURVIVAL_PRIORITY,
        "kind": "generic",          # routes to GoalsAPI via sync_proposed_goals (intrinsic path)
        "source": "survival_recruit",
        "tier": SURVIVAL_TIER,
        "driven_by": drive,
        "recruit_aid": aid,
        "status": "proposed",
        "tags": ["survival", drive],
        "plan": [{"step": first_step, "status": "pending"}],
        "next_action": first_step,
        "milestones": [
            {"text": f"The deficit '{desc[:60]}' was restored.", "met": False, "met_at": None}
        ],
    }


def _in_refractory(aid: str, context: Dict[str, Any]) -> bool:
    """Refractory dedup: should recruitment for this alert id be skipped right now?
    True when EITHER an open recruited goal already exists (this cycle's proposals OR
    a non-terminal goal in the store), OR a recently-satisfied DORMANT goal for it is
    still inside MIN_REFIRE_INTERVAL_S (Phase-3 hunger-returns cooldown).
    Fail-safe to False (a possible duplicate beats missing a real deficit; the
    proposal-path's own title dedup is a second guard)."""
    low_aid = str(aid)
    for g in (context.get("proposed_goals") or []):
        if isinstance(g, dict) and str(g.get("recruit_aid") or "") == low_aid:
            return True
    try:
        from brain.cognition.planning.goals import load_goals

        now = time.time()

        def _walk(nodes) -> bool:
            for n in nodes or []:
                if not isinstance(n, dict):
                    continue
                if str(n.get("recruit_aid") or "") == low_aid:
                    status = str(n.get("status") or "").lower()
                    if status not in _TERMINAL_STATUSES:
                        return True                      # an open goal for this deficit
                    if status == "dormant":
                        try:
                            sat = float(n.get("_satisfied_ts") or 0.0)
                        except (TypeError, ValueError):
                            sat = 0.0
                        if sat and (now - sat) < MIN_REFIRE_INTERVAL_S:
                            return True                  # still cooling down (hunger-returns)
                if _walk(n.get("subgoals")):
                    return True
            return False

        return _walk(load_goals())
    except Exception as exc:  # store unreadable — don't block recruitment on it
        record_failure("survival_goals._in_refractory", exc)
        return False


def recruit_survival_goal(alert: Dict[str, Any],
                          context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Recruit a restoration goal from a chronically-neglected alert.

    Builds the survival goal and queues it into context['proposed_goals'] (the
    intrinsic submission path), unless a goal for this alert id is already open
    (refractory dedup). Returns the recruited goal, or None if deduped / the alert
    has no id. The neglect-threshold decision lives in the caller (tier1_health_check),
    which owns the per-alert neglect counter."""
    context = context if context is not None else {}
    aid = str(alert.get("id") or "")
    if not aid:
        return None
    if _in_refractory(aid, context):
        return None
    goal = build_survival_goal(alert)
    context.setdefault("proposed_goals", []).append(goal)
    log_activity(
        f"[survival_goals] recruited restoration goal for chronic deficit "
        f"'{aid}' → first action '{goal['next_action']}'."
    )
    return goal
