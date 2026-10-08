# brain/cognition/commitment_competition.py
# P7: commitment competition (close the self-commit bypass) — extracted from
# intrinsic_goals.py (module-size decomposition; public import paths preserved
# by re-export there).
#
# generate_intrinsic_goals used to commit the FIRST goal it produced directly into
# context["committed_goal"], so the competition/arbiter layer was moot and P1's
# gradient + P3's pressure were evaluated AFTER the choice was already locked.
# These helpers let the committed goal be CHOSEN among the live proposals, weighted
# by aspiration pressure + the (rewired) usefulness drive, so an artifact-gated
# production goal can actually win commitment over a cheap intake goal.
from __future__ import annotations

from typing import Any, Dict, List, Optional

from brain.cognition.global_workspace import bound_goal
from brain.cognition.intrinsic_objectives import _serves_aspiration, objective_pressure
from brain.cognition.intrinsic_helpers import _classify_tier, _weighted_sample, _zone_tags
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity


def _proposal_commit_score(g: Dict, pressure: Dict[str, float], strengths: Dict[str, float]) -> float:
    drive = str(g.get("driven_by") or "")
    serves = _serves_aspiration(drive)
    score = 1.0 + 2.0 * float(pressure.get(serves, 0.0))
    try:
        score += 0.1 * (float(g.get("priority", 3) or 3) / 3.0)
    except (TypeError, ValueError):  # intentional: non-numeric priority → no bonus
        pass
    if drive in ("output_producing", "genuine_contact"):
        score += float(strengths.get("usefulness", 0.0)) * 0.5
    return max(0.0, score)


def _select_commit_proposal(proposals: List[Dict], context: Dict[str, Any]) -> Optional[Dict]:
    # B11 (smoke life 2026-10-08): a daemon-only goal (characterize) is never the
    # brain's commitment — this direct-commit path bypassed committed_goals_v1's
    # guard and the brain satiety-closed a characterization again.
    from brain.goal_io import is_daemon_only
    cands = [g for g in (proposals or []) if isinstance(g, dict) and g.get("title")
             and not is_daemon_only(g)]
    if not cands:
        return None
    try:
        pressure = objective_pressure(context)
    except Exception:
        pressure = {}
    strengths = {}
    try:
        from brain.cognition.goal_competition import compute_drive_strengths
        strengths = compute_drive_strengths(context) or {}
    except Exception:
        strengths = {}
    scored = [(g, _proposal_commit_score(g, pressure, strengths)) for g in cands]
    picked = _weighted_sample(scored, 1)
    return picked[0] if picked else cands[0]


def _build_committed_goal(g: Dict, gid: str) -> Dict:
    """Build the context committed_goal dict from a proposal — crucially carrying
    requires_artifact / deadline_cycles so P2's artifact gate + deadline survive
    the v1 commit path (the old inline blocks dropped them).

    Canonical-ID contract: mint the goal's id ONCE here and stamp it back onto the
    source proposal `g` immediately, so the committed goal (which the effect ledger
    keys on), the proposal that later syncs to v2, and the v2 record all share one
    identity. Reuse an id already on `g` so a re-commit doesn't fork a new thread."""
    gid = g.get("id") or gid
    g["id"] = gid            # stamp the source proposal in place (live reference)
    drive = g.get("driven_by", "")
    cg = {
        "id": gid, "title": g["title"], "name": g["title"], "kind": "generic",
        "tier": g.get("tier") or _classify_tier(g["title"], drive, g.get("description", "")),
        "priority": "NORMAL",
        "tags": ["intrinsic", g.get("driven_by", "exploration_drive"), *_zone_tags(g.get("zone", "self"))],
        "zone": g.get("zone", "self"), "orientation": g.get("orientation", "selfward"),
        "spec": {"description": g.get("description", ""), "driven_by": drive,
                 "zone": g.get("zone", "self"), "orientation": g.get("orientation", "selfward")},
        "next_action": None, "status": "in_progress",
        "milestones": g.get("milestones", []),
        "serves": _serves_aspiration(drive),
    }
    if g.get("requires_artifact"):
        cg["requires_artifact"] = True
        cg["deadline_cycles"] = g.get("deadline_cycles")
    # T2.3 — record the `attempted` funnel stage: a goal serving this drive's
    # aspiration was committed for pursuit (not merely generated). This is what
    # makes the scoreboard's per-aspiration `attempted` non-zero, so coverage can be
    # read as generated → attempted → progressed → completed per aspiration.
    try:
        from brain.cognition.objective_scoreboard import record_by_drive
        record_by_drive(drive, "attempted")
    except Exception:  # intentional: scoreboard is best-effort, never block a commit
        pass
    try:
        from brain.cognition.planning.goal_comprehension import hydrate_goal_model
        return hydrate_goal_model(cg)
    except Exception as exc:
        record_failure("intrinsic_goals._build_committed_goal.hydrate", exc)
        return cg


def _evict_spent_committed_goal(context: Dict[str, Any]) -> bool:
    """Clear a spent/orphaned goal from the committed slot. Returns True if it cleared
    one.

    A goal that has already failed/completed/abandoned can never be advanced by the
    executive (its queue drops terminal goals) nor closed-from-the-slot (the
    completion-finalize path only runs while it is actively pursued), yet while it
    lingers it (a) blocks origination via the action_debt gate and (b) prevents the
    commit-to-slot in generate_intrinsic_goals (`if not committed_goal`). That wedged
    the loop on 2026-06-24: a FAILED problem_refocus diagnosis goal sat in the slot for
    hours, starving origination and execution alike.

    Trigger on terminal STATUS only — never on a missing id. A freshly committed
    intrinsic goal is legitimately id-less until the v2 projection assigns one, so
    evicting on `id is None` would thrash a healthy pending goal out of the slot every
    cycle."""
    cg = bound_goal(context)
    if not isinstance(cg, dict):
        return False
    status = str(cg.get("status") or "").lower()
    if status in ("failed", "completed", "abandoned"):
        log_activity(
            "[intrinsic_goals] Clearing spent committed goal "
            f"'{str(cg.get('title') or cg.get('name') or '?')[:50]}' "
            f"(status={cg.get('status')!r}, id={cg.get('id')!r}) from the slot."
        )
        context["committed_goal"] = None
        return True
    return False
