"""Active goal execution (Phase 4D, from pursue_goal.py).

pursue_committed_goal() — the Executive's per-tick goal advance: read the stored
plan, run the next pending step, replan on drift/exhaustion, handle survival
preempt + tier/satiety closure + degrade/disengage, and pace itself via the
refractory cooldown. The plan/closure/planning helpers are imported downward
(no cycle); pursue_goal re-exports pursue_committed_goal and _STEP_MAX_ATTEMPTS.
"""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger

import json as _json
import time
from typing import Any, Dict, List, Optional

from brain.utils.generate_response import generate_response, generate_reasoning_chain, llm_ok
from brain.utils.log import log_activity, log_error
from brain.cog_memory.working_memory import update_working_memory
from brain.cog_memory.long_memory import update_long_memory
from brain.cognition.planning.thinking_depth import choose_depth
from brain.cognition.planning.goals import (
    get_goal_plan, get_next_pending_step, advance_goal_plan,
    set_goal_plan, prune_satisfied_steps,
)
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
from brain.cognition.planning.goal_closure import (
    _tier_closure_enabled, _survival_preempt_enabled, _survival_critical,
    _closed_loop_break,
    _finalize_goal_completion, _maybe_close_on_tier, _degrade_or_disengage,
    _repromote_if_recovered,
)
from brain.cognition.planning.plan_versioning import (
    _save_plan_version,
)
from brain.cognition.planning.goal_planning import (
    _symbolic_plan, _generate_plan, _bootstrap_goal_plan,
)

_log = get_logger(__name__)

_last_pursuit_ts: float = 0.0
_COOLDOWN_S: float = 30.0
_pursuit_call_count: int = 0
# Give a recognised-but-ineffective step this many tries before advancing past it.
_STEP_MAX_ATTEMPTS: int = 3
# Conscious cycles allowed for a deliberate/generative step before disengagement.
_DELIBERATE_MAX_ROUNDS: int = 30


def pursue_committed_goal(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Advance the active committed goal by one concrete step.

    Flow:
      1. Check cooldown
      2. Load or generate the goal's step plan
      3. Execute the next pending step (no LLM call if plan exists)
      4. If plan exhausted → replan
      5. If drift detected → replan
      6. Update depth bandit with dual-signal reward
    """
    global _last_pursuit_ts
    context = context or {}

    now = time.time()
    # Publish the cooldown window so the SELECTOR can yield the turn to other
    # cognition instead of repeatedly picking pursue only to no-op here — that
    # spinning is ~1/3 of his pursue picks (the low-reward ones).
    context["_pursue_cooldown_until"] = _last_pursuit_ts + _COOLDOWN_S
    if now - _last_pursuit_ts < _COOLDOWN_S:
        return {"status": "ok", "skipped": True, "reason": "cooldown"}

    goal = bound_goal(context)
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"status": "ok", "skipped": True, "reason": "no_committed_goal"}

    # Release a goal that was already completed/abandoned/failed elsewhere
    # (e.g. goal_io/GoalsAPI marked it done but context still holds the old dict).
    if goal.get("status") in ("completed", "abandoned", "failed"):
        context["committed_goal"] = None
        log_activity(f"[pursue_goal] Released '{goal.get('title', '')[:60]}' — status={goal.get('status')}.")
        update_working_memory(
            f"[goal_released] '{goal.get('title', '')}' was already {goal.get('status')} — clearing active slot."
        )
        return {"status": "ok", "skipped": True, "reason": "goal_already_done"}

    # A goal that was degraded to a note while a capability was down is restored to
    # its full form as soon as that capability is back — before we plan/act, so we
    # pursue the real goal, not the leftover note stand-in.
    if goal.get("_degraded"):
        _repromote_if_recovered(goal, context)

    goal_title  = goal.get("title") or goal.get("name", "")

    # ── Survival preemption (Fix 2 / §4.5) ───────────────────────────────────
    # Survival is strict precedence: when a homeostatic/survival drive is critical,
    # YIELD this cycle's pursuit — even for an "urgent" goal — so a long-running or
    # never-ending goal can't crowd out staying alive. Transient and resumable: it
    # does NOT fail or pause the goal, just declines to advance it now; next cycle,
    # if the drive has cleared, pursuit proceeds. Checked BEFORE _last_pursuit_ts is
    # stamped so yielding doesn't consume the pursue cooldown. Flag-gated.
    if _survival_preempt_enabled():
        _crit, _why = _survival_critical(context)
        if _crit:
            # R2 — "closed loop running open": if a behavioral corrective has been
            # armed but survival preemption has overridden it for a full window,
            # force ONE grounded pursuit (bounded by a cooldown) rather than yield
            # again. Otherwise yield as normal — survival precedence is untouched.
            if not _closed_loop_break(context, _why):
                log_activity(f"[pursue_goal] survival preemption ({_why}) — yielding pursuit "
                             f"of '{goal_title[:60]}' this cycle (resumable).")
                return {"status": "ok", "skipped": True, "reason": "survival_preempt",
                        "detail": _why, "goal": goal_title}
        else:
            context["_preempt_open_streak"] = 0  # not preempting → clear the open-loop streak

    _last_pursuit_ts = now
    context["_pursue_cooldown_until"] = now + _COOLDOWN_S

    # ── Energy-aware gate ────────────────────────────────────────────────────
    # High energy → pursue eagerly (shorter effective cooldown).
    # Rest / low energy → soften pursuit unless there's an urgent flag
    # (drift detected, goal stalled, or imminent deadline).
    energy_state = str(context.get("energy_state") or "medium")
    rest_mode    = bool(context.get("_rest_mode"))
    if energy_state == "high":
        pass   # no gate; proceed immediately
    elif rest_mode or energy_state == "low":
        _urgent = (
            bool(goal.get("_drift_detected"))
            or bool(goal.get("_stalled"))
            or bool((context.get("_temporal_pressure") or {}).get("deadline_alerts"))
        )
        if not _urgent:
            log_activity(
                "[pursue_goal] rest_mode/low-energy: no urgent signal — "
                "softening pursuit to allow reflection"
            )
            return {
                "status": "ok",
                "skipped": True,
                "reason":  "rest_mode_soft",
                "goal":    goal_title,
            }

    # ── Milestone gate: goals must have a plan before any step executes ──────
    # If this goal was just adopted with no plan, generate one immediately and
    # write a prominent WM note so the adoption is visible and auditable. The
    # gate body lives in goal_planning (alongside _generate_plan); it sets the
    # plan as a side effect and returns a blocked dict only when planning fails.
    _gate_blocked = _bootstrap_goal_plan(goal, goal_title, context)
    if _gate_blocked is not None:
        return _gate_blocked

    # ── Drift check: replan if last assessment flagged off-track ────────────
    if goal.get("_drift_detected"):
        goal.pop("_drift_detected", None)
        drift_score   = float(goal.pop("_drift_score", 0.55))
        replan_count  = int(goal.get("_replan_count") or 0) + 1
        goal["_replan_count"] = replan_count

        if replan_count >= 3:
            goal["_stalled"] = True
            context["committed_goal"] = goal
            try:
                update_long_memory(
                    f"[goal_stalled] '{goal_title}' has been replanned {replan_count}× "
                    "without convergence. Needs genuine reconsideration.",
                    emotion="impasse_signal",
                    event_type="goal_stalled",
                    importance=4,
                    context=context,
                )
            except Exception as _e:
                record_failure("pursue_goal.pursue_committed_goal", _e)
            log_activity(f"[pursue_goal] '{goal_title[:60]}' stalled after {replan_count} replans.")
            return {"status": "stalled", "goal": goal_title, "replan_count": replan_count}

        log_activity(
            f"[pursue_goal] Drift detected (score={drift_score:.2f}) — "
            f"replan #{replan_count} for '{goal_title[:60]}'"
        )

        # Version the current plan before discarding it
        _save_plan_version(goal, reason=f"drift_replan_{replan_count}")

        if drift_score > 0.40:
            # Deep drift: use inner_loop for a reasoned replan
            try:
                from brain.think.inner_loop import run_inner_loop as _ril
                from brain.think.scratchpad import scratchpad_init as _sci
                _sci(context)

                goal_desc = (goal.get("spec") or {}).get("description", goal.get("description", ""))
                wm_tail   = (context.get("working_memory") or [])[-4:]
                wm_block  = "\n".join(
                    str(e.get("content", e) if isinstance(e, dict) else e)[:80]
                    for e in wm_tail
                ) or "(none)"
                il_result = _ril(
                    topic=(
                        f"Revise the plan for goal: {goal_title}\n"
                        f"Description: {goal_desc or '(none)'}\n"
                        f"This plan has drifted (severity {drift_score:.2f}). "
                        f"Recent steps:\n{wm_block}"
                    ),
                    context_text=(
                        f"Goal driven by: {goal.get('driven_by', 'exploration_drive')}\n"
                        f"Previous plan version archived. Produce a fresh 3-5 step plan."
                    ),
                    context=context,
                    max_rounds=4,
                )
                # inner_loop either deferred (no llm, symbolic mode off) or ran in
                # symbolic mode — in both cases its output is NOT JSON plan steps:
                # a typed defer is empty, and symbolic deliberation yields reasoning
                # text / KG facts, not a plan. Either way, drop to the lightweight
                # symbolic replan below rather than misparsing it into a bad plan.
                _typed_defer = (il_result.get("meta_decision") == "defer"
                                and il_result.get("reason") == "deliberation requires llm tool")
                if _typed_defer or il_result.get("mode") == "symbolic":
                    log_activity(
                        f"[pursue_goal] inner_loop {'deferred' if _typed_defer else 'symbolic'} "
                        f"(no llm) — using symbolic replan for '{goal_title[:60]}'"
                    )
                    goal["plan"] = []
                    revised_text = ""
                else:
                    revised_text = il_result.get("content", "")
                # Try to parse as JSON steps
                deep_steps: List[str] = []
                try:
                    maybe = _json.loads(revised_text)
                    if isinstance(maybe, list):
                        deep_steps = [str(s) for s in maybe if isinstance(s, str) and s.strip()]
                except Exception:
                    # Split by newline/period if JSON parse fails
                    for line in revised_text.split("\n"):
                        clean = line.strip().lstrip("0123456789.-) ")
                        if len(clean) > 10:
                            deep_steps.append(clean)

                if deep_steps:
                    set_goal_plan(goal, deep_steps)
                    context["committed_goal"] = goal
                    log_activity(
                        f"[pursue_goal] Deep replan via inner_loop: "
                        f"{len(deep_steps)} steps for '{goal_title[:60]}'"
                    )
                    update_working_memory(
                        f"[goal_replan_deep] '{goal_title}' replanned (drift={drift_score:.2f}) "
                        f"via inner_loop: " + " → ".join(s[:50] for s in deep_steps[:3])
                    )
                    # Don't fall through — execute fresh plan below
                    next_step_dict = get_next_pending_step(goal)
                    if next_step_dict is not None:
                        # jump straight to execution
                        pass  # falls through to the step execution block
                    else:
                        goal["plan"] = []   # still empty → lightweight replan below
                else:
                    goal["plan"] = []  # inner_loop parse failed → lightweight replan
            except Exception as _ile:
                log_error(f"[pursue_goal] inner_loop replan failed: {_ile}")
                goal["plan"] = []
        else:
            goal["plan"] = []  # mild drift → lightweight replan below

    # ── Passive subgoal adaptation ──────────────────────────────────────────
    # Never re-execute a step whose outcome was already achieved (its milestone
    # ticked as a side effect of earlier work). Cheap, symbolic, progress-
    # preserving — the heavier reshaping lives in adapt_subgoals().
    try:
        _pruned = prune_satisfied_steps(goal, context)
        if _pruned:
            context["committed_goal"] = goal
            log_activity(
                f"[pursue_goal] Skipped {_pruned} already-satisfied step(s) "
                f"for '{goal_title[:60]}'"
            )
    except Exception as _e:
        record_failure("pursue_goal.pursue_committed_goal.2", _e)

    # ── Plan: load existing or generate new ─────────────────────────────────
    next_step_dict = get_next_pending_step(goal)

    if next_step_dict is None:
        # Plan exhausted or missing — generate a new one
        steps = _generate_plan(goal, context)
        if not steps:
            # Fallback: single-step shallow plan (symbolic when LLM is down OR the
            # caller demands symbolic-only — the background Executive daemon).
            if not llm_callable_by("pursue_goal/fallback") or context.get("_symbolic_only"):
                concept_text = context.get("_concept_text", "")
                fallback_step = f"{goal_title}: {next_step_dict['step'] if next_step_dict else 'reflect and take one concrete action'}{(' — ' + concept_text[:100]) if concept_text else ''}".strip()[:300]
            else:
                depth = choose_depth()
                if depth >= 3:
                    result_chain = generate_reasoning_chain(
                        topic=goal_title,
                        context_text=f"Goal driven by: {goal.get('driven_by', 'exploration_drive')}",
                        caller="pursue_goal",
                    )
                    fallback_step = (result_chain.get("content") or "").strip()[:300]
                else:
                    prompt = (
                        f"You are Orrin.\n\nActive goal: \"{goal_title}\"\n\n"
                        "What is the SINGLE most concrete, actionable next step? "
                        "One sentence. Start with an action verb."
                    )
                    fallback_step = (llm_ok(generate_response(prompt, caller="pursue_goal/fallback"), "pursue_goal") or "").strip()[:300]
            if not fallback_step:
                return {"status": "error", "error": "could not generate plan or fallback step"}
            steps = [fallback_step]

        set_goal_plan(goal, steps)
        context["committed_goal"] = goal
        log_activity(f"[pursue_goal] Generated {len(steps)}-step plan for '{goal_title[:60]}'")
        next_step_dict = get_next_pending_step(goal)

    if next_step_dict is None:
        return {"status": "error", "error": "plan empty after generation"}

    next_step = next_step_dict["step"]

    # ── Discharge the step as a real act (ideomotor execution) ───────────────
    # A plan step is an intention. Pursuing the goal means firing the act that
    # realises it and checking the world afterward — not narrating the intention
    # and marking it done. James (1890) ideomotor; Powers (1973) perceptual
    # control: the step is satisfied only if the act produced an effect.
    global _pursuit_call_count
    from brain.cognition.planning.step_execution import recognise_step_action, execute_step_action

    _act_fn = recognise_step_action(next_step_dict)
    _executed = False
    _result_text = ""
    if _act_fn:
        # Pass the step text + owning goal so a person-facing act composes to
        # serve the reason it was triggered (EXPRESSION_MEMBRANE_FIX_PLAN E6).
        _executed, _result_text = execute_step_action(
            _act_fn, context, step_text=next_step, goal=goal)

    # ── Honest hand-off: a step the Executive must NOT run (generative / outward /
    # self-modifying — execute_step_action returns a "deferred" marker). Do NOT
    # advance it (no fake completion) and do NOT treat it as a throttled procedural
    # retry. Surface it to the conscious workspace so the deliberate mind can see
    # and act on it (the impasse signal biases the selector toward it), and count
    # conscious opportunities so a genuinely un-doable goal disengages adaptively
    # (Wrosch) instead of nagging forever.
    if _act_fn and not _executed and str(_result_text).lower().startswith("deferred"):
        # Feasibility first: if the capability this goal needs is unavailable right
        # now, don't nag the conscious mind toward an impossible act — reduce to an
        # achievable sub-goal (go simpler) or disengage (abandon). Never stub.
        try:
            from brain.cognition.planning.goal_types import required_capability, capability_available
            _cap = required_capability(goal)
            if _cap and not capability_available(_cap, context):
                _handled = _degrade_or_disengage(goal, context, goal_title, f"needs {_cap} (unavailable)")
                if _handled is not None:
                    return _handled
        except Exception as _fe:
            record_failure("pursue_goal.feasibility", _fe)

        cc = context.get("cycle_count") or {}
        _cyc = int(cc.get("count", 0) if isinstance(cc, dict) else cc or 0)
        if goal.get("_last_deliberate_cycle") != _cyc:
            goal["_last_deliberate_cycle"] = _cyc
            _rounds = int(goal.get("_deliberate_rounds", 0) or 0) + 1
        else:
            _rounds = int(goal.get("_deliberate_rounds", 0) or 0)
        goal["_deliberate_rounds"] = _rounds
        goal["_needs_deliberate_action"] = _act_fn   # e.g. "decide_to_write_code"
        context["committed_goal"] = goal

        if _rounds >= _DELIBERATE_MAX_ROUNDS:
            from brain.cognition.planning.goals import mark_goal_failed
            mark_goal_failed(goal, reason=f"unmet_after_{_rounds}_deliberate_rounds", context=context)
            context["committed_goal"] = None
            update_working_memory(
                f"[goal_disengaged] '{goal_title}' — the deliberate action it needs "
                f"({_act_fn}) never happened after {_rounds} cycles. Letting it go so I can move on.",
                event_type="goal_disengaged", importance=3,
            )
            log_activity(f"[pursue_goal] Disengaged '{goal_title[:60]}' — {_act_fn} unmet after {_rounds} rounds.")
            return {"status": "disengaged", "goal": goal_title, "rounds": _rounds}

        update_working_memory(
            f"[goal_needs_deliberate_action] '{goal_title}' is blocked on a step my "
            f"background mind can't do: {next_step[:80]}. The deliberate mind needs to "
            f"run {_act_fn} to move it forward (round {_rounds}/{_DELIBERATE_MAX_ROUNDS}).",
            event_type="goal_needs_deliberate_action", importance=3,
        )
        try:
            from brain.cognition.planning.goals import merge_updated_goal_into_tree
            from brain.cognition.planning import goal_arbiter
            goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                               source="pursue_goal.awaiting_deliberate")
        except Exception as _e:
            record_failure("pursue_goal.pursue_committed_goal.deferred", _e)
        return {"status": "awaiting_deliberate", "goal": goal_title,
                "next_step": next_step, "needs": _act_fn, "round": _rounds}

    _attempts_map = goal.setdefault("_step_attempts", {})
    _step_key = next_step[:120]

    if _act_fn and not _executed:
        # The act was recognised but produced no effect (throttled, no URL,
        # nothing found). Leave the step pending and retry — unless we have tried
        # enough times, in which case advance with an honest blocker note so
        # adapt_subgoals / drift can route around the unreachable step.
        _n = int(_attempts_map.get(_step_key, 0)) + 1
        _attempts_map[_step_key] = _n
        context["committed_goal"] = goal
        if _n < _STEP_MAX_ATTEMPTS:
            update_working_memory(
                f"[goal_blocked] '{goal_title}': step did not take hold "
                f"(attempt {_n}/{_STEP_MAX_ATTEMPTS}) — {next_step[:80]}"
            )
            try:
                from brain.cognition.planning.goals import merge_updated_goal_into_tree
                from brain.cognition.planning import goal_arbiter
                # Atomic load→merge→save through the GoalArbiter (no uncoordinated
                # load_goals/save_goals race; daemon-ready). dual_process_loop.md Phase 1.
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="pursue_goal.blocked_retry")
            except Exception as _e:
                record_failure("pursue_goal.pursue_committed_goal.3", _e)
            return {"status": "retry", "goal": goal_title, "next_step": next_step, "attempt": _n}
        update_working_memory(
            f"[goal_blocked] '{goal_title}': could not execute after {_n} "
            f"attempts — {next_step[:80]}. Moving on."
        )

    # ── Advance: the act took hold, OR the step is internal, OR we gave up ────
    log_activity(f"[pursue_goal] Executing step: {next_step[:80]}")
    advance_goal_plan(goal, next_step_dict)
    _attempts_map.pop(_step_key, None)
    # Real progress resets the stall/replan state so a future drift doesn't
    # inherit a stale counter from an unrelated earlier replan cycle. A GIVE-UP
    # advance is not progress — resetting on it blinded the metacog watchdog to
    # the 2026-07-02 stuck-step loop (regenerated plans failing the same two
    # steps for 1.7 h while the stall counter kept going back to zero).
    if _executed:
        goal.pop("_replan_count", None)
        goal.pop("_stalled", None)
    context["committed_goal"] = goal

    # Sense of agency (efference copy): a real act discharged this cycle. This is
    # the signal that tells the loop "I acted" — it resets action_debt and earns
    # agentic reward. Internal/deliberative steps (no act fired) deliberately do
    # NOT set it, so narrating a thought never counts as doing.
    if _executed:
        context["__acted_this_tick__"] = True

    # Persist mid-pursuit step progress to disk so it survives restarts.
    try:
        from brain.cognition.planning.goals import merge_updated_goal_into_tree
        from brain.cognition.planning import goal_arbiter
        # Atomic load→merge→save through the GoalArbiter (daemon-ready). Phase 1.
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="pursue_goal.step_progress")
    except Exception as _pg_e:
        log_activity(f"[pursue_goal] Could not persist step progress: {_pg_e}")

    # Working-memory record: the real result when an act fired, else narration.
    if _executed:
        update_working_memory(f"[Goal pursuit] {goal_title}: {next_step} → {_result_text[:200]}")
    elif not llm_callable_by("pursue_goal"):
        _concept_text = context.get("_concept_text", "")
        _step_output = (
            f"{goal_title} | {next_step}"
            + (f" | {_concept_text[:120]}" if _concept_text else "")
        )
        update_working_memory(f"[Goal pursuit] {_step_output}")
        _step_lower = next_step.lower()
        _WRITE_KEYWORDS = ("write", "record", "note", "observ", "document", "jot", "log")
        if any(k in _step_lower for k in _WRITE_KEYWORDS):
            try:
                from brain.cognition.leave_note import leave_note as _ln
                _note_result = _ln(context) or ""
                # A note actually written to the outbox is an external act — it
                # must discharge action_debt like any other act, or symbolic-mode
                # goal work registers as "thinking but not doing" forever and
                # debt grows without bound (FINDINGS 2026-06-12 data sweep §7).
                if _note_result.startswith("Left a note"):
                    context["__acted_this_tick__"] = True
            except Exception as _e:
                record_failure("pursue_goal.pursue_committed_goal.4", _e)
    else:
        update_working_memory(f"[Goal pursuit] {goal_title}: {next_step}")

    # Choose depth for this step and stash it; ORRIN_loop will call
    # update_depth(depth, env_delta_reward) after the env snapshot is taken.
    depth = choose_depth()
    context["_pursue_goal_depth"] = depth

    _pursuit_call_count += 1

    # Record to long memory every 3rd successful pursuit call
    # Fix 5 (explore_loop_fix_plan.md §5): a plan step that maps to no tool — a
    # "thought, not an act" (e.g. "Reflect on what I found") — never completes, so it
    # used to deadlock the plan-completion gate forever (E2). For goals WITHOUT
    # milestones (which can't satiety-close via Fix 1), don't count such thought-steps
    # toward `remaining`, so the plan can still finish. Goals WITH milestones keep
    # counting them (Fix 1's tier/satiety path governs their closure, not the plan
    # gate — excluding here would let them close on raw process-milestones). Flag-gated.
    _has_ms = any(isinstance(m, dict) for m in (goal.get("milestones") or []))
    if _tier_closure_enabled() and not _has_ms:
        remaining = sum(
            1 for s in get_goal_plan(goal)
            if s.get("status") == "pending" and recognise_step_action(s.get("step")) is not None
        )
    else:
        remaining = sum(1 for s in get_goal_plan(goal) if s.get("status") == "pending")

    # Fix 1 (explore_loop_fix_plan.md §5): before the legacy plan-completion gate,
    # check whether the OBJECTIVE is already satisfied (tier-scaled) even though plan
    # steps remain — the case that trapped the live "Explore" goal (E1). Flag-gated.
    _tier_close = _maybe_close_on_tier(goal, goal_title, next_step, remaining, context)
    if _tier_close is not None:
        return _tier_close

    if _pursuit_call_count % 3 == 0:
        update_long_memory(
            f"[goal_pursuit] Working on '{goal_title}' — step: {next_step} "
            f"({remaining} steps remaining)",
            emotion="motivation",
            event_type="goal_pursuit",
            importance=3,
            context=context,
        )

    # When all plan steps are done, only close the goal if its OBJECTIVE (its success
    # milestones) was actually met — finishing the steps is necessary but NOT
    # sufficient. The old code marked goals "completed" the moment steps ran, so 12/12
    # completed goals had unmet objectives. Steps done + milestones met → complete;
    # steps done + milestones unmet → re-plan once, then mark FAILED (which feeds the
    # self-repair loop) — never a false success.
    if remaining == 0:
        try:
            from brain.cognition.planning.env_snapshot import apply_milestone_updates
            apply_milestone_updates(context)
        except Exception as _e:
            record_failure("pursue_goal.pursue_committed_goal.5", _e)
        _ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
        if _ms and not all(m.get("met") for m in _ms):
            _attempts = int(goal.get("_completion_attempts", 0)) + 1
            goal["_completion_attempts"] = _attempts
            _unmet = [m.get("text", "?") for m in _ms if not m.get("met")]
            try:
                # NB: set_goal_plan is already a module-level import (top of file) —
                # don't re-import it here or it becomes a function-local and shadows
                # the earlier uses (UnboundLocalError).
                from brain.cognition.planning.goals import merge_updated_goal_into_tree, mark_goal_failed
                from brain.cognition.planning import goal_arbiter
                if _attempts < 2:
                    set_goal_plan(goal, _symbolic_plan(goal_title, context))
                    log_activity(f"[pursue_goal] '{goal_title}': steps done but {len(_unmet)} "
                                 f"milestone(s) unmet — re-planning (attempt {_attempts}).")
                else:
                    mark_goal_failed(goal, reason=f"objective unmet after {_attempts} attempts: {_unmet[:2]}", context=context)
                    context["committed_goal"] = None
                    context["_last_bootstrap_ts"] = 0.0
                    log_activity(f"[pursue_goal] '{goal_title}': objective unmet after "
                                 f"{_attempts} attempts — FAILED (feeds self-repair).")
                # Atomic load→merge→save through the GoalArbiter (failure/objective-
                # unmet persist). dual_process_loop.md Phase 1.
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="pursue_goal.milestone_gate")
            except Exception as _e:
                log_activity(f"[pursue_goal] milestone-gate failed: {_e}")
            return {"status": "ok", "next_step": next_step, "goal": goal_title,
                    "steps_remaining": 0, "objective_met": False}

        # Objective genuinely met (or no milestones) → close the goal so Signal B
        # fires. Single idempotent path shared with the Fix-1 satiety short-circuit.
        _finalize_goal_completion(goal, goal_title, context, reason="plan complete")

    return {
        "status":          "ok",
        "next_step":       next_step,
        "goal":            goal_title,
        "steps_remaining": remaining,
    }
