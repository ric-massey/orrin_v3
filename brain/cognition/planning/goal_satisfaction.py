# brain/cognition/planning/goal_satisfaction.py
#
# The satisfaction handshake + the affect close-loop (Core Architecture Master
# Plan, T1.1 — the capstone).
#
# THE GAP THIS CLOSES. A felt-origin goal is spawned because a drive is elevated
# (curiosity, the need for contact, the itch to make something). The goal would
# then reach DONE, but nothing wrote the closure back DOWN onto the drive that
# spawned it — so the need never relaxed, contentment never rose, and Orrin
# re-spawned the same kind of goal forever. The loop was open at its most
# important seam: act → (satisfied) → ✗ → act again, identically.
#
# WHAT THIS BUILDS. On a REAL completion (evidence present — see `grounded`):
#   (1) Handshake: record on the goal WHICH need it satisfied (`satisfied_need`)
#       and the EVIDENCE that it did (`satisfaction_evidence`). A close with no
#       evidence relaxes nothing — the loop only shuts on real work, so hollow
#       completion can't farm contentment.
#   (2) Relax the spawning drive: a small, BOUNDED, decaying negative nudge on the
#       core need-signal the goal served, submitted through the single-writer
#       affect inbox. Bounded + floored so a closure NUDGES the drive down, never
#       collapses it to zero (a drive pinned at 0 kills motivation as badly as one
#       pinned at 1.0 — the ceiling pathology in reverse).
#   (3) Let contentment rise: a small positive nudge on `satisfaction_signal`
#       (the renamed contentment) that then drains on its own — the felt "that's
#       done, and it's good" that fades and frees the next act.
#
# This is the "act → satisfied → fades → act again" loop. Called once, from the
# single completion chokepoint (`mark_goal_completed`), after the close is
# confirmed real. Wholly fail-safe: a fault here can never break completion.
from __future__ import annotations

from typing import Any, Dict, Optional

from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

# A felt-origin goal's `driven_by` tag → the core need-signal that pursuing it was
# meant to relieve. These are the drives that ACCUMULATE as a felt need and should
# settle a notch when the need is met. (Aux drives alias onto the same need as
# their primary, mirroring intrinsic_objectives._AUX_DRIVE_ALIASES.)
_DRIVEN_BY_TO_NEED: Dict[str, str] = {
    "world_knowledge":    "exploration_drive",
    "curiosity":          "exploration_drive",
    "self_understanding": "exploration_drive",
    "self_exploration":   "exploration_drive",
    "simulate_selves":    "exploration_drive",
    "genuine_contact":    "social_deficit",
    "connection":         "social_deficit",
    "output_producing":   "stagnation_signal",
    "will":               "stagnation_signal",
    "problem_solving":    "impasse_signal",
}

# Bounds (conservative-first; one closure may only nudge, never lurch).
_RELAX_DELTA   = 0.10   # max downward nudge on the spawning drive per closure
_RELAX_WEIGHT  = 0.5    # a clear but not dominating voice in the weighted sum
_RELAX_TTL     = 6      # cycles the relaxation drains over
_DRIVE_FLOOR   = 0.05   # never relax a drive below this (overshoot guard)

_CONTENT_DELTA  = 0.12  # contentment (satisfaction_signal) rise on a real close
_CONTENT_WEIGHT = 0.5
_CONTENT_TTL    = 8      # then it drains on its own — contentment is meant to fade


def _core_signals(context: Dict[str, Any]) -> Dict[str, Any]:
    af = context.get("affect_state")
    if isinstance(af, dict):
        cs = af.get("core_signals")
        if isinstance(cs, dict):
            return cs
    return {}


def satisfaction_evidence(goal: Dict[str, Any], context: Dict[str, Any],
                          grounded: bool, significance: float) -> Dict[str, Any]:
    """The concrete evidence that this goal's need was actually met — milestone
    completion, produced/verified artifact, and effect significance. This is what
    makes DONE honest: a close with no evidence here is hollow and closes no loop."""
    ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
    return {
        "grounded": bool(grounded),
        "milestones_met": sum(1 for m in ms if m.get("met")),
        "milestones_total": len(ms),
        "verified_artifact": bool(context.get("_verified_artifact_this_cycle")),
        "significance": round(float(significance or 0.0), 3),
    }


def close_affect_loop(goal: Dict[str, Any], context: Optional[Dict[str, Any]],
                      grounded: bool, significance: float = 0.0) -> None:
    """Record the satisfaction handshake and close the loop back to affect.

    Only relaxes the drive / raises contentment when there is real evidence
    (`grounded`): the loop shuts on real work, never on a hollow close. Fail-safe."""
    try:
        if not isinstance(goal, dict) or not isinstance(context, dict):
            return

        driven_by = str(goal.get("driven_by") or "").lower()
        need = _DRIVEN_BY_TO_NEED.get(driven_by)
        evidence = satisfaction_evidence(goal, context, grounded, significance)

        # Always record the handshake so the archive can answer "did this DONE
        # satisfy a need, and on what evidence?" — the metric the run could not show.
        goal["satisfied_need"] = need if grounded else None
        goal["satisfaction_evidence"] = evidence

        # No evidence ⇒ no loop closure. A hollow close cannot relax a drive or
        # pay contentment (that would relocate the hollow-completion bug into affect).
        if not grounded or not need:
            return

        from brain.control_signals.arbiter import submit_signal

        # (2) Relax the spawning drive — bounded, floored. Clamp the decrement so
        # the signal can never be pushed below _DRIVE_FLOOR by this nudge.
        cur = 0.0
        try:
            cur = float(_core_signals(context).get(need, 0.0) or 0.0)
        except (TypeError, ValueError):
            cur = 0.0
        relax = min(_RELAX_DELTA, max(0.0, cur - _DRIVE_FLOOR))
        if relax > 0.0:
            submit_signal(context, target=need, delta=-relax, weight=_RELAX_WEIGHT,
                          source="goal_satisfaction", ttl_cycles=_RELAX_TTL)

        # (3) Let contentment rise, then drain on its own.
        submit_signal(context, target="satisfaction_signal", delta=_CONTENT_DELTA,
                      weight=_CONTENT_WEIGHT, source="goal_satisfaction",
                      ttl_cycles=_CONTENT_TTL)

        log_activity(
            f"[satisfaction] '{str(goal.get('title') or goal.get('name') or '?')[:50]}' "
            f"satisfied {driven_by} → relax {need} -{relax:.3f}, +contentment "
            f"(milestones {evidence['milestones_met']}/{evidence['milestones_total']}, "
            f"sig {evidence['significance']})."
        )
    except Exception as exc:
        record_failure("goal_satisfaction.close_affect_loop", exc)
