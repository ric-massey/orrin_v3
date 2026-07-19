"""Goal closure / survival / disengagement (Phase 4D, from pursue_goal.py).

The goal-lifecycle terminus: detect a survival-critical preempt, finalize a
completed goal (_finalize_goal_completion), close growth/core goals on tier
satiety (_maybe_close_on_tier), and degrade-or-disengage / re-promote a stalled
goal (_degrade_or_disengage / _repromote_if_recovered) per Wrosch goal
disengagement. Tree/goal mutations are inline imports, so no cycle back to
pursue_goal, which re-imports these (and shares the _FINALIZED_IDS dedup dict,
the same object, so finalize-once stays coherent across both modules).
"""
from __future__ import annotations

import copy
import time
from typing import Any, Dict, Optional, Tuple

from brain.core.runtime_log import get_logger
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.utils.env import env_bool
from brain.cog_memory.working_memory import update_working_memory
from brain.cognition.planning.goals import set_goal_plan

_log = get_logger(__name__)

# Goal IDs finalized recently (id → ts), shared with pursue_committed_goal to stop
# the same goal closing twice across its in-flight dict copies.
_FINALIZED_IDS: Dict[str, float] = {}

# F-LN4b — how many satiety-close attempts an understanding goal with an
# UNANSWERED question can block before the close proceeds and the question is
# handed to a follow-up goal instead (the want persists; the goal doesn't loop).
_EPISTEMIC_BLOCK_MAX = 2


def _tier_closure_enabled() -> bool:
    """Flag gate (house pattern). OFF ⇒ legacy plan-completion gate only.

    Default ON since 2026-06-23 (GOALS_MASTER_PLAN Part I Phase 4): deliberate/core
    goals close on the underlying need being SATED, not only on plan-completion.
    Safe to default-on — satiety has a cycle-1 guard and mark_goal_completed still
    refuses hollow closure. Set ORRIN_TIER_CLOSURE=0 to restore the legacy gate."""
    return env_bool("ORRIN_TIER_CLOSURE", True)


def _survival_preempt_enabled() -> bool:
    # Default ON since 2026-06-23: Phase-1 wire + hysteresis verified by
    # test_survival_preempt_wire.py and a clean headless ORRIN_ONCE run (boots with
    # the preempt armed, normal cycle, exit 0). Set ORRIN_SURVIVAL_PREEMPT=0 to disable.
    return env_bool("ORRIN_SURVIVAL_PREEMPT", True)


def _raw_survival_critical(context: Dict[str, Any]) -> Tuple[bool, str]:
    """The instantaneous (un-hysteresis'd) survival-critical test: is a
    survival/homeostatic drive at a level that must PREEMPT goal pursuit *this
    cycle*? Strict thresholds (stricter than the new-goal `_under_load` gate): this
    overrides even an "urgent" stuck goal, enforcing "a never-ending goal can't get
    in the way of survival." Fail-safe: any error ⇒ not critical."""
    try:
        if context.get("_setpoint_critical") or context.get("health_critical"):
            return True, str(context.get("_setpoint_critical_reason") or "setpoint_critical")
        if float(context.get("health_score", 1.0) or 1.0) < 0.35:
            return True, "health<0.35"
        af = context.get("affect_state") or {}
        if float(af.get("resource_deficit", 0.0) or 0.0) > 0.85:
            return True, "resource_deficit>0.85"
    except (TypeError, ValueError):  # intentional: bad affect/health values → don't force-close
        return False, ""
    return False, ""


def _survival_critical(context: Dict[str, Any]) -> Tuple[bool, str]:
    """Fix 2 / §4.5 — hysteresis wrapper over `_raw_survival_critical`. Pursuit
    YIELDS for the cycle (transient, resumable — not a failure) only when the raw
    condition has held for ≥2 consecutive cycles; one clean cycle clears the streak.
    This stops a vital signal dithering at the threshold from ping-ponging the goal
    slot every cycle (Phase-1 hysteresis). The streak lives in `context`, which
    persists across cycles; this is the sole writer. Called once per cycle from
    goal_execution.pursue_committed_goal."""
    raw_crit, why = _raw_survival_critical(context)
    streak = int(context.get("_survival_crit_streak", 0) or 0)
    streak = streak + 1 if raw_crit else 0
    context["_survival_crit_streak"] = streak
    if raw_crit and streak >= 2:
        return True, why
    return False, ""


# Closed-loop-break tuning (SIGNAL_TO_ACTION_AUDIT §2 / R2).
_PREEMPT_OPEN_THRESHOLD = 10        # consecutive armed-but-preempted cycles before a break
_PREEMPT_BREAK_COOLDOWN_S = 60.0    # after a break, let survival precedence stand this long


def _closed_loop_break_enabled() -> bool:
    """Flag gate (house pattern). OFF ⇒ survival preempt always wins, even when a
    corrective is armed and stuck. Default ON — the break is bounded (one grounded
    pursuit, then a cooldown) and only fires on a *sustained* armed-but-preempted
    streak, which is pathological, not healthy regulation. Set
    ORRIN_CLOSED_LOOP_BREAK=0 to restore strict survival precedence."""
    return env_bool("ORRIN_CLOSED_LOOP_BREAK", True)


def _closed_loop_break(context: Dict[str, Any], why: str) -> bool:
    """R2 — detect and break a "closed loop running open": survival preemption
    yielding goal pursuit while a behavioral corrective is ARMED
    (``_force_action_next``, set by behavioral_adaptation on goal-avoidance /
    reflection-imbalance) and the impasse is not relieving. When that conjunction
    holds for _PREEMPT_OPEN_THRESHOLD consecutive cycles, return True to force ONE
    grounded pursuit — breaking the freeze the audit observed (212 cycles of
    "thinking but not doing"). Bounded by a cooldown so it can never thrash survival
    precedence: at most one forced pursuit per _PREEMPT_BREAK_COOLDOWN_S.

    Returns False (preemption should yield as normal) when the corrective is not
    armed, during the post-break cooldown, or before the streak fills — i.e. healthy
    survival precedence is untouched; only the pathological sustained-stall is broken.
    The streak lives in ``context`` (persists across cycles); this is its sole writer
    on the armed path. Reset on the not-critical path by the caller."""
    if not _closed_loop_break_enabled():
        return False
    if not bool(context.get("_force_action_next")):
        context["_preempt_open_streak"] = 0  # no corrective armed → ordinary regulation
        return False
    now = time.time()
    if now < float(context.get("_preempt_break_cooldown_until", 0) or 0):
        return False  # just broke — let survival precedence stand for the cooldown
    streak = int(context.get("_preempt_open_streak", 0) or 0) + 1
    context["_preempt_open_streak"] = streak
    if streak < _PREEMPT_OPEN_THRESHOLD:
        return False
    context["_preempt_open_streak"] = 0
    context["_preempt_break_cooldown_until"] = now + _PREEMPT_BREAK_COOLDOWN_S
    log_activity(
        f"[pursue_goal] closed-loop break: survival preempt ({why}) held "
        f"{_PREEMPT_OPEN_THRESHOLD} cycles with a corrective armed — forcing one "
        f"grounded pursuit to break the freeze (resumable)."
    )
    # Fix 3 (RUN6_FIX_PLAN §3): a sustained armed-but-preempted stall is the
    # strongest avoidance evidence there is — weight it so the frozen goal's
    # commitment rank drops (goal_io Fix 2) instead of only forcing action on it.
    try:
        _g = context.get("committed_goal")
        if isinstance(_g, dict):
            _gid = str(_g.get("id") or _g.get("title") or _g.get("name") or "")
            if _gid:
                from brain.cognition.planning.commitment_value import note_avoidance
                note_avoidance(_gid, weight=5.0)
    except Exception as _cve:
        record_failure("goal_closure.note_avoidance", _cve)
    try:
        update_working_memory({
            "content": (
                f"[impasse] Survival preemption held {_PREEMPT_OPEN_THRESHOLD} cycles while "
                f"action was armed ({why}) — broke the freeze with one grounded step."
            ),
            "event_type": "closed_loop_break",
            "importance": 3,
            "priority": 3,
        })
    except Exception as _e:
        record_failure("goal_closure._closed_loop_break", _e)
    return True


def _finalize_goal_completion(goal: Dict[str, Any], goal_title: str,
                              context: Dict[str, Any], reason: str = "plan complete") -> None:
    """Single, idempotent goal-completion path (Fix 1d). Fires the achievement
    reward, marks the goal completed through the GoalArbiter, clears the slot, and
    records the spawn cooldown. Shared by the plan-completion gate AND the Fix-1
    satiety/tier short-circuit so the reward can never double-fire.

    Honours mark_goal_completed's hollow-completion guard: if the objective is not
    actually met it does NOT persist/clear (the goal keeps going)."""
    if goal.get("status") in ("completed", "abandoned", "failed"):
        return  # idempotency guard — never reward/close twice
    # Cross-COPY idempotency (Fix 1d, hardened after live double-close): the same goal
    # can exist as several dicts at once — context["committed_goal"], the
    # context["committed_goals"] queue, and a fresh pull from the store — each still
    # "in_progress", so the per-dict status check above passes for each and the reward
    # double-fires. Guard on the goal ID across all copies within a short window.
    _gid = str(goal.get("id") or goal.get("title") or goal.get("name") or "")
    _nowt = time.time()
    # Keep finalized IDs for an hour (a completed goal re-appearing minutes later is
    # a stale copy still being pursued, observed live at 141s — well past a short
    # window). Cap the dict so it stays bounded.
    for _k in [k for k, t in _FINALIZED_IDS.items() if _nowt - t > 3600]:
        _FINALIZED_IDS.pop(_k, None)
    if len(_FINALIZED_IDS) > 256:
        for _k in sorted(_FINALIZED_IDS, key=lambda k: _FINALIZED_IDS[k])[:64]:
            _FINALIZED_IDS.pop(_k, None)
    if _gid and _gid in _FINALIZED_IDS:
        goal["status"] = "completed"   # reflect the already-done close on this stale copy
        context["committed_goal"] = None
        return
    if _gid:
        _FINALIZED_IDS[_gid] = _nowt

    # Phase 3 — survival "satiety" doesn't complete-and-vanish; it goes DORMANT and
    # re-fires when the deficit recurs (hunger returns). Stamp the satisfied time so
    # the Phase-2 recruiter can honour a minimum re-fire interval. No achievement
    # reward: survival pays restoration, not the production reward, so it can't become
    # a cheap reward source that crowds out real work.
    if str(goal.get("tier") or goal.get("kind") or "").lower() == "survival":
        goal["status"] = "dormant"
        goal["_satisfied_ts"] = _nowt
        try:
            from brain.cognition.planning.goals import merge_updated_goal_into_tree
            from brain.cognition.planning import goal_arbiter
            goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                               source="pursue_goal.survival_dormant")
        except Exception as _e:
            record_failure("pursue_goal.survival_dormant.persist", _e)
        context["committed_goal"] = None
        log_activity(f"[pursue_goal] survival goal '{goal_title[:50]}' satisfied → "
                     f"dormant (will re-fire if the deficit returns).")
        return

    try:
        from brain.cognition.planning.goals import mark_goal_completed, merge_updated_goal_into_tree
        from brain.cognition.planning import goal_arbiter
        # F-LN4a (Run 10): epistemic close-out stamps BEFORE mark_goal_completed —
        # the comp_goals archive append lives inside it, so stamping afterwards
        # left every scored record without question/answered (all 10 Run-10
        # close-out fires stamped an already-archived dict).
        answered: Optional[bool] = None
        try:
            from brain.cognition.epistemic_closeout import stamp_closeout
            answered = stamp_closeout(goal)
        except Exception as _ee:
            record_failure("pursue_goal.epistemic_closeout", _ee)
        # F-LN4b — the understanding-can't-close-on-satiety wall (rung 1). An
        # unanswered question blocks the satiety-close so pursuit keeps working
        # the actual gap; after _EPISTEMIC_BLOCK_MAX blocked attempts the close
        # proceeds but the question survives as a follow-up goal (spawned below)
        # — opposed, not clamped: the want persists until answered.
        if answered is False and reason.startswith("satiety"):
            _blocks = int(goal.get("_epistemic_blocks", 0) or 0)
            if _blocks < _EPISTEMIC_BLOCK_MAX:
                goal["_epistemic_blocks"] = _blocks + 1
                if _gid:
                    _FINALIZED_IDS.pop(_gid, None)   # not closed — stay closeable
                try:
                    goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                       source="pursue_goal.epistemic_block")
                except Exception as _e:
                    record_failure("pursue_goal.epistemic_block.persist", _e)
                log_activity(
                    f"[epistemic] satiety close of '{goal_title[:50]}' BLOCKED "
                    f"({_blocks + 1}/{_EPISTEMIC_BLOCK_MAX}) — its question is not "
                    f"answered yet: {str(goal.get('question') or '')[:80]}")
                return
        # completion_signal fires BEFORE mark_goal_completed so the achievement is
        # attributed to THIS goal, not the next one spawned by the continuity hook
        # inside mark_goal_completed (Berridge 1996 — liking at arrival).
        try:
            from brain.control_signals.reward_signals.reward_signals import release_reward_signal as _rrs
            from brain.cognition.planning.goals import achievement_significance as _achv
            _sig = _achv(goal)   # I17 — felt achievement ∝ significance, not flat
            _rrs(context, signal_type="completion_signal", actual_reward=round(1.0 * _sig, 3),
                 expected_reward=0.5, effort=0.8, mode="phasic", source="goal_completion")
        except Exception as _ee:
            log_activity(f"[pursue_goal] completion_signal release failed: {_ee}")
        # A satiety/tier close means the underlying need is sated — a legitimate
        # close reason for a directional goal, independent of the milestone gate
        # (T2.2). Pass it through so mark_goal_completed allows it for non-artifact
        # goals (artifact goals still require their artifact).
        mark_goal_completed(goal, context=context, satiety_close=reason.startswith("satiety"))
        # mark_goal_completed refuses hollow completion (goals.py:575). Only persist
        # and clear the slot if the close actually took.
        if goal.get("status") != "completed":
            # A refused close must stay closeable: leaving the id in
            # _FINALIZED_IDS made every later attempt short-circuit to
            # "already done" on a copy that was never archived.
            if _gid:
                _FINALIZED_IDS.pop(_gid, None)
            log_activity(f"[pursue_goal] '{goal_title}': close ({reason}) blocked — "
                         f"objective not met; continuing to pursue.")
            return
        # F-LN4b, second arm: the goal is genuinely closed but its question is
        # not — hand the question to a follow-up goal so the gap survives.
        if answered is False:
            try:
                from brain.cognition.epistemic_closeout import spawn_followup_goal
                spawn_followup_goal(goal)
            except Exception as _ee:
                record_failure("pursue_goal.epistemic_followup", _ee)
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="pursue_goal.completion")
        context["committed_goal"] = None
        context["_last_bootstrap_ts"] = 0.0
        log_activity(f"[pursue_goal] Goal '{goal_title}' closed ({reason}).")
        try:
            # F6: one chokepoint records both the cooldown stamp and the
            # per-life completion count (escalating-cooldown / respawn-cap input).
            from brain.cognition.intrinsic_helpers import note_title_completion
            note_title_completion(goal_title)
        except Exception as _e:
            record_failure("pursue_goal._finalize_goal_completion", _e)
    except Exception as _e:
        log_activity(f"[pursue_goal] Could not close goal '{goal_title}': {_e}")


def _maybe_close_on_tier(goal: Dict[str, Any], goal_title: str, next_step: str,
                         remaining: int, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fix 1: close a goal by its OBJECTIVE rather than its plan, scaled by tier.
      • trivial/minor  → close on met process-milestones (the act IS the goal).
      • growth/core/…  → close on SATIETY (novelty exhausted / info-gap closed, §4.2);
                          mark_goal_completed still gates on milestones, so this never
                          fakes a hollow success.
      • aspiration/long_term → never (and they're never committed anyway).
    Returns a result dict if it closed (caller should return it), else None.
    Flag-gated; only runs while steps remain (remaining != 0 is the legacy path)."""
    if not _tier_closure_enabled() or remaining == 0:
        return None
    if goal.get("status") in ("completed", "abandoned", "failed"):
        return None
    tier = str(goal.get("tier") or goal.get("kind") or "").lower()
    # (b) see just-met milestones before deciding.
    try:
        from brain.cognition.planning.env_snapshot import apply_milestone_updates
        apply_milestone_updates(context)
    except Exception as _e:
        record_failure("pursue_goal._maybe_close_on_tier", _e)
    _ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]

    close, why = False, ""
    if tier in ("trivial", "minor"):
        # (a) explicit milestones, all met — never empty (vacuous all([])).
        if _ms and all(m.get("met") for m in _ms):
            close, why = True, f"trivial objective met ({tier or 'trivial'})"
    elif tier in ("aspiration", "long_term"):
        pass   # directional/never-ending goals never close here (and aren't committed)
    else:
        # growth / core / exploratory / identity / existential / generic / "" AND any
        # legacy or unknown tier (e.g. the pre-existing "short_term" goals already in
        # the store) → satiety-gated. `growth` is the unknown-tier fallback (Fix 1
        # decision box), so anything not explicitly trivial/aspiration lands here.
        from brain.cognition.planning.goal_satiety import is_sated
        sated, sreason = is_sated(goal, context)
        if sated:
            # F6 (2026-07-05 findings): a real definition-of-done. 41 frontier
            # children completed as ~90 s single-research_topic loops — steps
            # 2-3 of their 3-step plans skipped as "goal completed" every time,
            # dragging median seconds-to-complete from 3,722 to 85.5. A goal
            # with a multi-step plan may not satiety-close before at least TWO
            # steps have actually completed (or a milestone was genuinely met).
            _plan_steps = [p for p in (goal.get("plan") or []) if isinstance(p, dict)]
            _steps_done = sum(1 for p in _plan_steps if p.get("status") == "completed")
            _ms_met = any(m.get("met") for m in _ms)
            if len(_plan_steps) >= 2 and _steps_done < 2 and not _ms_met:
                log_activity(
                    f"[pursue_goal] satiety close deferred for '{goal_title[:60]}' — "
                    f"only {_steps_done}/{len(_plan_steps)} plan steps done, no milestone met."
                )
            else:
                close, why = True, f"satiety:{sreason}"

    if not close:
        return None
    _finalize_goal_completion(goal, goal_title, context, reason=why)
    if goal.get("status") == "completed":
        # Run-5 meter bug (RUN6_FIX_PLAN §4): this is THE satiety close path, and
        # it never told outcome_metrics — S3 read 0 while 7 real satiety closes
        # happened. The maintenance sweep records its own; this records the
        # pursuit-path close so the gate reads honest numbers.
        if why.startswith("satiety"):
            try:
                from brain.cognition.planning.outcome_metrics import record_satiety_closure
                record_satiety_closure()
            except Exception as _e:
                record_failure("goal_closure.record_satiety_closure", _e)
        return {"status": "ok", "next_step": next_step, "goal": goal_title,
                "steps_remaining": remaining, "closed": True, "reason": why}
    return None  # close was blocked (hollow) — keep pursuing via the normal path


def _degrade_or_disengage(goal: Dict[str, Any], context: Dict[str, Any],
                          goal_title: str, reason: str) -> Optional[Dict[str, Any]]:
    """A goal that can't proceed — because a needed capability is down OR because it's
    making no progress. FIRST time: reduce it to a simpler achievable sub-goal that
    still serves the aspiration (means-ends — "go simpler"). If already reduced or no
    reduction exists: disengage (Wrosch — "abandon"). Never stub/fake. `reason` is a
    short human cue (e.g. "needs llm (unavailable)" or "no progress"). Returns a status
    dict, or None to fall through to normal handling."""
    try:
        from brain.cognition.planning.goal_types import reduced_goal_spec
        from brain.cognition.planning.goals import merge_updated_goal_into_tree, mark_goal_failed
        from brain.cognition.planning import goal_arbiter
    except ImportError:  # intentional: planning modules optional — fall through to normal
        return None

    if not goal.get("_degraded"):
        spec = reduced_goal_spec(goal)
        if spec:
            goal["_degraded"] = True
            goal["_original_title"] = goal.get("title")
            # Snapshot the full pre-degrade form so it can be restored verbatim when
            # the capability recovers (see _repromote_if_recovered). A degrade is a
            # TEMPORARY means-ends reduction, not a permanent demotion — without this
            # snapshot a transient outage converts the goal to a note for good.
            goal["_predegrade"] = {
                "title":      goal.get("title"),
                "name":       goal.get("name"),
                "type":       goal.get("type"),
                "milestones": copy.deepcopy(goal.get("milestones")),
            }
            goal["title"] = spec["title"]
            goal["name"]  = spec["title"]
            goal["type"]  = spec["type"]
            goal["milestones"] = spec["milestones"]
            goal["_needs_deliberate_action"] = None
            goal["_deliberate_rounds"] = 0
            goal["_last_progress_cycle"] = None   # fresh progress clock for the new form
            set_goal_plan(goal, [])   # force a fresh plan for the new, achievable form
            context["committed_goal"] = goal
            update_working_memory(
                f"[goal_degraded] '{(goal.get('_original_title') or goal_title)[:40]}' ({reason}) "
                f"— pursuing a simpler achievable step instead: {spec['title'][:50]}",
                event_type="goal_degraded", importance=3,
            )
            log_activity(f"[pursue_goal] Degraded goal ({reason}) → {spec['title'][:50]}")
            try:
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="pursue_goal.degrade")
            except Exception as _e:
                record_failure("pursue_goal.degrade.persist", _e)
            return {"status": "degraded", "goal": spec["title"]}

    # Phase 3 — survival goals are NON-DISENGAGEABLE (Wrosch disengagement is adaptive
    # for *chosen* goals; you don't "give up" on rest). A survival goal may degrade to
    # a simpler restoration above, but it must never abandon: keep the slot and fall
    # through to normal handling so pursuit retries rather than failing the goal.
    if str(goal.get("tier") or goal.get("kind") or "").lower() == "survival":
        log_activity(f"[pursue_goal] survival goal '{goal_title[:50]}' can't proceed "
                     f"({reason}) but is non-disengageable — holding, not abandoning.")
        return None

    # Already reduced (or no reduction available) → disengage honestly.
    mark_goal_failed(goal, reason=f"unworkable:{reason}", context=context)
    context["committed_goal"] = None
    update_working_memory(
        f"[goal_disengaged] Releasing '{(goal.get('_original_title') or goal_title)[:40]}' — "
        f"{reason}, and no simpler version left. Moving on.",
        event_type="goal_disengaged", importance=3,
    )
    log_activity(f"[pursue_goal] Disengaged goal ({reason}, no reduction): {goal_title[:40]}")
    return {"status": "disengaged", "goal": goal_title, "reason": reason}


def _repromote_if_recovered(goal: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Restore a degraded goal to its full form once the capability it needed is
    available again. A degrade (means-ends reduction → "Note what I know about X")
    is meant to be temporary; nothing else ever reverts it, so without this a single
    transient web/LLM outage permanently rewrites real goals into notes. Returns True
    if the goal was restored."""
    if not isinstance(goal, dict) or not goal.get("_degraded"):
        return False
    try:
        from brain.cognition.planning.goal_types import required_capability, capability_available
    except ImportError:  # intentional: goal_types optional — can't restore
        return False

    _pd = goal.get("_predegrade")
    snap: Dict[str, Any] = _pd if isinstance(_pd, dict) else {}
    orig_title = snap.get("title") or goal.get("_original_title")
    if not orig_title:
        return False

    # What did the ORIGINAL (full) form need? Probe with its title/type/description so
    # the classifier sees the real research goal, not the degraded note form.
    probe = {
        "title": orig_title,
        "name": snap.get("name") or orig_title,
        "type": snap.get("type"),
        "spec": goal.get("spec"),
        "description": goal.get("description"),
    }
    cap = required_capability(probe)
    if not capability_available(cap, context):
        return False  # still down → stay in the achievable degraded form

    # Restore the full form.
    goal["title"] = orig_title
    goal["name"]  = snap.get("name") or orig_title
    if snap.get("type") is not None:
        goal["type"] = snap["type"]
    else:
        goal.pop("type", None)           # let it re-derive from title/description
    if snap.get("milestones") is not None:
        goal["milestones"] = copy.deepcopy(snap["milestones"])
    else:
        # Legacy degrade (pre-snapshot): synthesise an honest acquire-knowledge
        # milestone so the restored goal closes on a real finding, not on a note.
        subj = orig_title.split(":", 1)[-1].strip() or orig_title
        goal["milestones"] = [
            {"text": f"A finding about {subj[:60]} was written to long memory.",
             "met": False, "met_at": None},
        ]
    goal["_degraded"] = False
    goal.pop("_predegrade", None)
    goal.pop("_original_title", None)
    goal["_last_progress_cycle"] = None   # fresh progress clock for the restored form
    goal["_needs_deliberate_action"] = None
    goal["_deliberate_rounds"] = 0
    set_goal_plan(goal, [])               # force a fresh plan for the full form
    context["committed_goal"] = goal
    update_working_memory(
        f"[goal_repromoted] '{orig_title[:50]}' — the capability it needs is back, "
        f"restoring the full goal instead of the note stand-in.",
        event_type="goal_repromoted", importance=3,
    )
    log_activity(f"[pursue_goal] Re-promoted recovered goal → {orig_title[:50]}")
    try:
        from brain.cognition.planning.goals import merge_updated_goal_into_tree
        from brain.cognition.planning import goal_arbiter
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="pursue_goal.repromote")
    except Exception as _e:
        record_failure("pursue_goal.repromote.persist", _e)
    return True
