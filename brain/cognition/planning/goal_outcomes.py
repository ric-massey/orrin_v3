# brain/cognition/planning/goal_outcomes.py
# Goal outcome handling, extracted from goals.py (Phase 4.5C): scoring a
# completion's significance (achievement_significance) and the completion /
# failure transitions — mark_goal_completed (reward, memory, aspiration credit,
# self-belief revision, intake->output laddering), mark_goal_failed, and the
# deadline sweep fail_overdue_artifact_goals. Imports the store + criteria + belief
# leaves directly; goals.py re-exports these names for its many external callers.
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import List, Dict, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.cog_memory.working_memory import update_working_memory
from brain.affect.reward_signals.reward_signals import release_reward_signal
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
from brain.paths import COMPLETED_GOALS_FILE
from brain.cognition.planning.goal_store import load_goals, save_goals
from brain.cognition.planning.goal_plan_ops import TERMINAL_STEP_STATUSES
from brain.cognition.planning.goal_criteria import (
    _is_artifact_gated, PRODUCTION_DEADLINE_CYCLES,
)
from brain.cognition.planning.goal_belief import _revise_weak_area_beliefs

_log = get_logger(__name__)


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


