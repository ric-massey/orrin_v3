"""Cognitive-loop action/cognition execution stages (Phase 4A, extracted from
the ORRIN_loop entrypoint).

After think() returns a decision, the loop dispatches it. `execute_behavior_action`
runs a behavior `result["action"]` (Path A); `execute_cognition_function` runs a
selected cognition `result["next_function"]` (Path B) — the tier-1 critical
override, the dispatch via _invoke_cognition, outcome/grounding reward, the bandit
+ decision/evaluator-WAL accounting, and the failure/repair routing. Each returns
the cycle's (context, reward); feats/acted are internal. The if/elif that selects
the path stays in the loop.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
import time
from typing import Any, Dict, Tuple
from brain.think.think_utils.action_gate import take_action
from brain.think.loop_helpers import (
    reason_string,
    bandit_learn,
)
from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
from brain.cognition.planning.reflection import record_decision
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.json_utils import load_json
from brain.utils.log import log_error, log_activity, log_model_issue
from brain.utils.affect_signal_utils import log_penalty_signal
from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure
from brain.paths import (
    WORKING_MEMORY_FILE,
)

from brain.loop.telemetry import _push_event, _ui_memory, _bridge
from brain.loop.invoke import _invoke_cognition
from brain.loop.cognition_reward import shape_cognition_reward
from brain.utils.affect_signal_utils import log_uncertainty_spike
from brain.think.loop_helpers import execute_action_via_registries, compute_reward

_log = get_logger(__name__)
Context = Dict[str, Any]


def execute_behavior_action(
    context: Context, result: Any, _decision_id: Any, _evaluator: Any, BEH_NAMES: Any,
) -> Tuple[Context, Any, bool]:
    acted_this_cycle = False
    action = result["action"]
    speaker = context.get("speaker")
    action_type = action.get("type")
    try:
        from brain.cognition.metacog import metacog_note as _mn
        _mn(context, "action", f"chose action {action_type!r}")
    except Exception as e:
        record_failure("ORRIN_loop.metacog_note_action", e)

    if action_type not in BEH_NAMES:
        log_error(f"Unknown action type: {action_type}. Skipping.")
        log_model_issue(f"Unknown action type attempted: {action_type}")
        try:
            route_exception(RuntimeError(f"Unknown action {action_type}"),
                            phase="action", context=context, extra={"action": action_type})
        except Exception as e:
            record_failure("ORRIN_loop.route_exception_action", e)
        _ = try_auto_repair({"type": "UnknownAction", "msg": str(action_type),
                             "trace": "", "phase": "action"}, context)
        reward = -0.3
        feats = bandit_learn(str(action_type or "unknown_action"), context, reward, decision_id=_decision_id)
        record_decision(str(action_type or "unknown_action"),
                        reason_string({"error": "unknown_action"}, reward, feats, "think.action"),
                        reward=reward, context=context)
        if _evaluator:
            try:
                from brain.eval.evaluator_wal import append_pending as _ew_append_ua
                _ew_append_ua(_decision_id, str(action_type or "unknown_action"), feats, get_cycle_count(),
                              committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.11", _e)
    else:
        try:
            success = take_action(action, context, speaker)
            acted_this_cycle = bool(success)
            if success:
                context["last_action_ts"] = time.time()
                log_activity(f"Action Taken: {action_type}")
                _push_event("function_executed", fn=action_type, cycle=get_cycle_count())
            else:
                log_error("take_action returned False")
                log_penalty_signal(context, "impasse_signal", increment=0.3)
            # 0.8 for success; negative reward for failures so the bandit
            # can distinguish bad actions from neutral ones (floor was 0.0).
            base_reward = 0.8 if success else -0.3
            # For speak-family actions, modulate reward by ground truth
            # grounding score so the bandit learns from real outcomes, not
            # just whether the output pipe succeeded. Claim 3 fix: speak
            # failures should produce real penalty, not constant 0.8.
            if success and action_type in {"speak", "user_response", "ask_user"}:
                # ── Store conversation exchange in long-term memory ──
                # This is the most important write: every real exchange with
                # Ric needs to persist. Without this, Orrin has no history.
                try:
                    from brain.cog_memory.long_memory import update_long_memory as _ulm
                    _user_said  = (context.get("latest_user_input") or "").strip()
                    _orrin_said = (action.get("content") or context.get("_last_spoken") or "").strip()
                    if _user_said and _orrin_said:
                        _ulm(
                            f"[Conversation] Ric: {_user_said[:500]}\nOrrin: {_orrin_said[:500]}",
                            event_type="conversation",
                            importance=4,
                            context=context,
                        )
                    elif _orrin_said:
                        _ulm(
                            f"[Orrin said] {_orrin_said[:600]}",
                            event_type="orrin_speech",
                            importance=2,
                            context=context,
                        )
                except Exception as _lm_e:
                    log_error(f"[long_memory] conversation write failed: {_lm_e}")

                try:
                    from brain.symbolic.ground_truth import grounding_score as _gs
                    _gs_val = _gs(action_type)
                    # Blend: 60% base, 40% grounding signal so variance is real
                    # _gs_val=0.5 neutral → 0.8; _gs_val=0.2 poor → 0.56; _gs_val=0.8 good → 0.92
                    base_reward = 0.6 * base_reward + 0.4 * (0.4 + _gs_val * 0.8)
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.12", _e)
            # Weight by goal progress when a goal is active
            try:
                from brain.cognition.planning.goal_progress import goal_weighted_reward as _gwr
                reward = _gwr(base_reward, context, action_was_taken=acted_this_cycle, fn_name=action_type)
            except Exception:
                reward = base_reward
            # Set acceptance flag so finalize's bonus applies correctly
            context["last_acceptance_pass"] = bool(success)
            feats = bandit_learn(action_type, context, reward, decision_id=_decision_id)
            record_decision(action_type,
                            reason_string({"success": success}, reward, feats, "think.action"),
                            reward=reward, context=context)
            if _evaluator:
                try:
                    from brain.eval.evaluator_wal import append_pending as _ew_append_a
                    _ew_append_a(_decision_id, action_type, feats, get_cycle_count(),
                                 committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                except Exception as _ewa_e:
                    log_model_issue(f"[evaluator] Path A WAL append failed: {_ewa_e}")
        except Exception as e:
            route_exception(e, phase="action", context=context)
            _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                 "trace": "", "phase": "action"}, context)
            log_error(f"Action execution failed: {e}")
            log_penalty_signal(context, "impasse_signal", increment=0.3)
            reward = 0.0
            feats = bandit_learn(str(action_type or "unknown_action"), context, reward, decision_id=_decision_id)
            record_decision(str(action_type or "unknown_action"),
                            reason_string({"error": str(e)}, reward, feats, "think.action"),
                            reward=reward, context=context)
            if _evaluator:
                try:
                    from brain.eval.evaluator_wal import append_pending as _ew_append_ae
                    _ew_append_ae(_decision_id, str(action_type or "unknown_action"), feats or {}, get_cycle_count(),
                                  committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                except Exception as _ewa_e2:
                    log_model_issue(f"[evaluator] Path A WAL append (error branch) failed: {_ewa_e2}")

    # acted_this_cycle is set to bool(success) on the action path; return it so the
    # loop's action-debt accounting sees the same value the inline code did.
    return context, reward, acted_this_cycle

def execute_cognition_function(
    context: Context, result: Any, _decision_id: Any, _evaluator: Any, _mem_daemon: Any, affect_state: Any,
) -> Tuple[Context, Any, bool]:
    reward = 0.0
    feats = {}
    fn_name = result["next_function"]

    # Tier 1 critical override — survival beats the bandit.
    # If setpoint_regulation flagged a critical condition this cycle, replace
    # the bandit's choice with the suggested repair function — but only
    # if that function is actually registered and callable.
    #
    # Bounded, not absolute: a persistent alert used to re-fire this
    # override on EVERY cycle, which (a) made update_affect_state
    # ~23% of all decisions and (b) vetoed every ε-exploration pick,
    # so dormant functions never got trials. Two bounds fix that:
    #   • cooldown — the same repair fn runs at most once per
    #     _T1_COOLDOWN cycles; between firings the bandit's pick
    #     stands (the alert signal still reaches the router).
    #   • futility — if the alert survives _T1_FUTILE consecutive
    #     overrides, the repair clearly isn't repairing; stand down
    #     for _T1_BACKOFF cycles and let normal cognition (incl.
    #     problem_refocus) take a different angle.
    _T1_COOLDOWN, _T1_FUTILE, _T1_BACKOFF = 3, 5, 50
    try:
        if context.get("_tier1_critical") and context.get("_tier1_suggested_fn"):
            _t1_fn = context["_tier1_suggested_fn"]
            _t1_hist = context.setdefault("_t1_override_hist", {})
            _t1_h = _t1_hist.setdefault(_t1_fn, {"streak": 0, "last_cycle": -10**9, "backoff_until": 0})
            _t1_now = get_cycle_count()
            if _t1_h["streak"] >= _T1_FUTILE and _t1_now >= _t1_h["backoff_until"]:
                _t1_h["streak"] = 0  # backoff served — eligible again
            if (_t1_fn in COGNITIVE_FUNCTIONS
                    and _t1_now >= _t1_h["backoff_until"]
                    and (_t1_now - _t1_h["last_cycle"]) >= _T1_COOLDOWN):
                _t1_h["streak"] += 1
                _t1_h["last_cycle"] = _t1_now
                if _t1_h["streak"] >= _T1_FUTILE:
                    _t1_h["backoff_until"] = _t1_now + _T1_BACKOFF
                    log_activity(
                        f"[setpoint_regulation] override futile: {_t1_fn!r} ran "
                        f"{_T1_FUTILE}× without clearing the alert — standing down "
                        f"{_T1_BACKOFF} cycles")
                log_activity(f"[setpoint_regulation] critical override: {fn_name!r} → {_t1_fn!r}")
                fn_name = _t1_fn
        # Reset neglect counters when the suggested repair function runs —
        # the alarm has been answered; allostatic load begins to recover.
        _t1_sfn = context.get("_tier1_suggested_fn")
        if _t1_sfn and fn_name == _t1_sfn:
            _h1_ign = context.get("_h1_ignored_cycles", {})
            for _aid in list(_h1_ign.keys()):
                _h1_ign[_aid] = 0
        context.pop("_tier1_critical", None)
        context.pop("_tier1_suggested_fn", None)
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.13", _e)

    try:
        from brain.cognition.metacog import metacog_note as _mn
        _mn(context, "selection", f"selected function {fn_name!r}")
    except Exception as e:
        record_failure("ORRIN_loop.metacog_note_selection", e)
    meta_or_fn = COGNITIVE_FUNCTIONS.get(fn_name)
    fn = (meta_or_fn.get("function") if isinstance(meta_or_fn, dict) else meta_or_fn)

    try:
        if callable(fn):
            # Pre-step environment snapshot for delta-based reward.
            _snap: Any = None
            _tick_ms: Any = None
            _env_delta: Any = None
            try:
                from brain.cognition.planning.env_snapshot import (
                    take_snapshot as _snap,
                    apply_milestone_updates as _tick_ms,
                    delta_reward as _env_delta,
                )
            except Exception as e:
                record_failure("ORRIN_loop.import_env_snapshot", e)
            _pre_snap = _snap(context) if _snap else {}

            _emo_pre = dict(context.get("affect_state") or {})
            # Proactive-resource Phase 0 (OBSERVE-ONLY): time the act so
            # the interoceptive cost model can learn expected cost and
            # report prediction error / would-be EVC / τ candidate. No
            # behavior change. docs/proactive_resource_plan.md.
            _cost_t0 = time.perf_counter()
            fn_result = _invoke_cognition(
                fn, fn_name, context,
                args=result.get("args") if isinstance(result, dict) else None,
                kwargs=result.get("kwargs") if isinstance(result, dict) else None,
            )
            try:
                _lat_ms = (time.perf_counter() - _cost_t0) * 1000.0
                from brain.cognition.cost_prediction import observe as _cost_observe
                _io = _cost_observe(fn_name, _lat_ms, context)
                _tb_io = _bridge()
                if _tb_io is not None and _io:
                    try:
                        _tb_io.update(interoception=_io)  # frozen telemetry wire field
                    except (AttributeError, OSError, RuntimeError):  # best-effort cost telemetry — never block the loop
                        pass
            except Exception as _ioe:
                record_failure("ORRIN_loop.cost_observe", _ioe)
            _emo_post = dict(context.get("affect_state") or {})

            # Post-step: tick milestones, snapshot again, compute reward.
            _ticked_n = 0
            try:
                if _tick_ms is not None:
                    _ticked_n = _tick_ms(context)
                    context["_milestones_ticked_this_cycle"] = int(_ticked_n or 0)
                    # Complete the COMMITTED goal the moment its milestones
                    # are all genuinely met. It's excluded from the main-loop
                    # satiety sweep and the Executive's pursue is unreliable,
                    # so an all-met committed goal otherwise sits in_progress
                    # forever with impasse climbing. mark_goal_completed re-checks
                    # milestones (hollow guard), so this only closes a goal that
                    # is genuinely finished (milestones tick on real artifacts:
                    # note_written / research / production traces — env_snapshot).
                    _cgoal = context.get("committed_goal")
                    if isinstance(_cgoal, dict) and _cgoal.get("status") != "completed":
                        _gms = [m for m in (_cgoal.get("milestones") or []) if isinstance(m, dict)]
                        _cyc_now = get_cycle_count()
                        # Progress clock: reset whenever a milestone ticks (or first sight).
                        if _ticked_n or _cgoal.get("_last_progress_cycle") is None:
                            _cgoal["_last_progress_cycle"] = _cyc_now
                        if _gms and all(m.get("met") for m in _gms):
                            try:
                                from brain.cognition.planning.goals import (
                                    mark_goal_completed as _mgc,
                                    merge_updated_goal_into_tree as _mugit,
                                )
                                from brain.cognition.planning import goal_arbiter as _ga
                                _mgc(_cgoal, context=context)
                                if _cgoal.get("status") == "completed":
                                    _ga.apply((lambda _g: (lambda _t: _mugit(_t, _g)))(_cgoal),
                                              source="loop.milestones_all_met")
                                    if (context.get("committed_goal") or {}).get("id") == _cgoal.get("id"):
                                        context["committed_goal"] = None
                                    log_activity(f"[loop] Goal completed (milestones met): {(_cgoal.get('title') or '?')[:50]}")
                            except Exception as _mce:
                                record_failure("ORRIN_loop.complete_on_milestones", _mce)
                        else:
                            # Leave an unproductive goal when its local
                            # reward rate has fallen below Orrin's learned
                            # global background and the smooth leave hazard fires.
                            from brain.cognition.reward_rate import (
                                accrue_leave_pressure as _alp,
                                is_stagnating as _is_stag,
                                should_force_switch as _sfs,
                            )
                            _alp(context)
                            if _is_stag(context) and _sfs(context):
                                try:
                                    from brain.cognition.planning.pursue_goal import _degrade_or_disengage as _dod
                                    _dod(
                                        _cgoal,
                                        context,
                                        (_cgoal.get("title") or "?"),
                                        "local reward rate below background",
                                    )
                                except Exception as _sde:
                                    record_failure("ORRIN_loop.stall_degrade", _sde)
                _post_snap: Dict[str, Any] = _snap(context) if _snap else {}
                _env_r = _env_delta(_pre_snap, _post_snap) if _env_delta else 0.5
            except Exception:
                _env_r = 0.5
                _post_snap = {}

            # Detect dispatch-level failure: _invoke_cognition returns
            # {"status": "error", "error": "unsatisfiable_args: [...]"}
            # when a cognitive function's required args can't be filled
            # from context (e.g. add_goal(goal=), apply_signal_routing(fn_scores=)).
            # Without this the bandit was logging "Executed" for non-runs
            # and rewarding them at the 0.20 underperformer floor.
            _dispatch_failed = (
                isinstance(fn_result, dict)
                and fn_result.get("status") == "error"
            )
            if _dispatch_failed:
                log_activity(
                    f"Skipped: {fn_name} (dispatch failed: "
                    f"{fn_result.get('error', 'unknown')})"
                )
            else:
                log_activity(f"Executed: {fn_name}")
            _push_event("function_executed", fn=fn_name, cycle=get_cycle_count())
            _fn_str = str(fn_result or "")
            _is_failure = _dispatch_failed or (
                _fn_str.startswith("❌") or
                _fn_str.startswith("Failed") or
                "ERROR" in _fn_str[:30]
            )
            _status_r = 0.1 if _is_failure else 0.5
            try:
                from brain.cognition.action_accounting import mark_consequential_cognition
                _reach = context.get("_last_reach_outcome")
                mark_consequential_cognition(
                    context,
                    env_r=_env_r,
                    ticked_n=_ticked_n,
                    is_failure=_is_failure,
                    info_gain=(
                        getattr(_reach, "info_gain", None)
                        if _reach is not None else None
                    ),
                )
            except Exception as _e:
                record_failure("ORRIN_loop.mark_consequential_cognition", _e)

            # === Agency-based causal learning (Pearl Level 2) — stash ===
            # Learn what this action does to Orrin's felt state. The felt
            # consequence isn't visible yet: commit_affect (cycle end) only
            # QUEUES the cycle's affect changes, which drain at NEXT cycle's
            # update_affect_state. So stash (action, this cycle's pre-affect)
            # and attribute the change at the start of next cycle, once it
            # has actually landed. Gopnik (child-as-scientist) / Damasio
            # (somatic markers) / Thorndike (law of effect): you learn
            # causation by acting and noticing how you feel afterward.
            if not _is_failure:
                try:
                    _base_core = context.get("_emo_pre_cycle") or {}
                    if isinstance(_base_core, dict) and _base_core:
                        context["_iv_pending"] = {
                            "fn": fn_name,
                            "core": {k: float(v) for k, v in _base_core.items()
                                     if isinstance(v, (int, float))},
                        }
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.14", _e)

            # === Waking temporal causal discovery (booster) ===
            # discover_from_wm_sequence otherwise only runs during dreams,
            # so event→event regularities accrue too slowly. Run it on the
            # recent WM window periodically while awake too. Pure reuse.
            try:
                if get_cycle_count() % 20 == 0:
                    from brain.symbolic.causal_graph import discover_from_wm_sequence as _dfs
                    _recent_wm: list[Any] = load_json(WORKING_MEMORY_FILE, default_type=list) or []
                    _dfs([e for e in _recent_wm[-25:] if isinstance(e, dict)])
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.15", _e)

            reward = shape_cognition_reward(
                context, fn_name, _fn_str, _emo_pre, _emo_post,
                _env_r, _status_r, _is_failure,
            )

            # Expose for finalize.py's reward_signal signal.
            context["_step_delta_reward"] = reward
            # Feed env-delta reward back into the depth bandit when
            # pursue_committed_goal ran this cycle (it stashes its chosen depth).
            _pg_depth = context.pop("_pursue_goal_depth", None)
            if _pg_depth is not None:
                try:
                    from brain.cognition.planning.thinking_depth import update_depth as _ud
                    _ud(_pg_depth, reward)
                except Exception as e:
                    record_failure("ORRIN_loop.update_depth", e)
            # Mark acceptance: succeeded + (no goal OR goal was referenced in WM)
            try:
                _goal_title = ((context.get("committed_goal") or {}).get("title") or "").lower()
                _wm_refs = any(
                    _goal_title in str(e).lower()
                    for e in (context.get("working_memory") or [])[-3:]
                ) if _goal_title else True
                context["last_acceptance_pass"] = not _is_failure and _wm_refs
            except Exception:
                context["last_acceptance_pass"] = not _is_failure
            # Update emotion→function map with actual reward (not always 1.0).
            # think_module.py uses last_reward from the *previous* cycle as a
            # proxy; here we update with the real outcome for better accuracy.
            try:
                _core_pre = (_emo_pre.get("core_signals") or _emo_pre) or {}
                _dom_emo = max(
                    (_core_pre or {}),
                    key=lambda k: float(_core_pre.get(k) or 0.0),
                ) if _core_pre else ""
                if _dom_emo:
                    from brain.affect.affect_learning import update_affect_function_map as _uefm
                    _uefm(_dom_emo, fn_name, reward_signal=reward)
            except Exception as e:
                record_failure("ORRIN_loop.emotion_function_map", e)
            feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
            record_decision(fn_name, reason_string({"status": "ok", "fn_result": _fn_str[:80]}, reward, feats, "think.fn"),
                            reward=reward, context=context)
            # Tag memory write + append pending reward to WAL
            if _decision_id:
                try:
                    _cur_cycle = get_cycle_count()
                    _goal_id = str((context.get("committed_goal") or {}).get("id") or
                                   (context.get("committed_goal") or {}).get("title") or "")
                    if _mem_daemon:
                        import brain.memory_io as memory_io
                        memory_io.write(
                            _mem_daemon, "function_output", _fn_str[:200],
                            meta={
                                "decision_id": _decision_id,
                                "fn": fn_name,
                                "cycle": _cur_cycle,
                            },
                        )
                        _ui_memory("write",
                                   [{"id": fn_name, "summary": _fn_str[:140]}],
                                   store="long")
                    if _evaluator:
                        from brain.eval.evaluator_wal import append_pending as _ew_append
                        _ew_append(_decision_id, fn_name, feats, _cur_cycle,
                                   committed_goal_id=_goal_id or None)
                except Exception as _ew_e:
                    log_model_issue(f"[evaluator] WAL append failed: {_ew_e}")
        else:
            log_model_issue(f"Unknown function requested: {fn_name}")
            try:
                route_exception(RuntimeError(f"Unknown function {fn_name}"),
                                phase="cognition", context=context, extra={"fn": fn_name})
            except Exception as e:
                record_failure("ORRIN_loop.route_exception_cognition", e)
            _ = try_auto_repair({"type": "UnknownFunction", "msg": str(fn_name),
                                 "trace": "", "phase": "cognition"}, context)
            reward = -0.3
            feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
            record_decision(fn_name, reason_string({"error": "unknown_fn"}, reward, feats, "think.fn"),
                            reward=reward, context=context)
            if _evaluator:
                try:
                    from brain.eval.evaluator_wal import append_pending as _ew_append_ufn
                    _ew_append_ufn(_decision_id, fn_name, feats, get_cycle_count(),
                                   committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.24", _e)
    except Exception as e:
        route_exception(e, phase="cognition", context=context, extra={"fn": fn_name})
        _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                             "trace": "", "phase": "cognition"}, context)
        log_error(f"Function {fn_name} crashed: {e}")
        log_penalty_signal(context, "impasse_signal", increment=0.3 + 0.3 * float(affect_state.get("conflict_signal") or 0.4))
        reward = 0.0
        feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
        record_decision(fn_name, reason_string({"error": str(e)}, reward, feats, "think.fn"),
                        reward=reward, context=context)

    # Path B never set acted_this_cycle inline — it relies on the loop recovering
    # the action via context["__acted_this_tick__"] (set by take_action /
    # action_accounting). Return False so that recovery is unchanged.
    return context, reward, False


def execute_fallback(context: Context, _evaluator: Any, COG_MAP: Any) -> Tuple[Context, Any, bool]:
    reward = 0.0
    feats = {}
    acted_this_cycle = False
    log_model_issue("No valid instruction from think(). Fallback to selector.")
    log_uncertainty_spike(context, increment=0.1)
    import uuid as _uuid_fb
    _fb_decision_id = str(_uuid_fb.uuid4())
    sel = None
    try:
        from brain.think.think_utils.select_function import select_function
        sel = select_function(context)
    except Exception as _e:
        log_model_issue(f"select_function failed: {_e}")

    if not sel or not isinstance(sel, str):
        fb_meta_or_fn = COGNITIVE_FUNCTIONS.get("reflect_on_self_beliefs")
        fb_fn = (fb_meta_or_fn.get("function") if isinstance(fb_meta_or_fn, dict) else fb_meta_or_fn)
        if callable(fb_fn):
            try:
                fb_fn()
                log_activity("Fallback executed: reflect_on_self_beliefs")
                reward = 0.5
            except Exception as e:
                route_exception(e, phase="cognition", context=context,
                                extra={"fn": "reflect_on_self_beliefs"})
                _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                     "trace": "", "phase": "cognition"}, context)
                log_error(f"Fallback function crashed: {e}")
                reward = 0.0
        else:
            log_model_issue("No fallback function available.")
            reward = 0.0
        feats = bandit_learn("reflect_on_self_beliefs", context, reward, decision_id=_fb_decision_id)
        record_decision("reflect_on_self_beliefs",
                        reason_string({"status": "fallback"}, reward, feats, "fallback.fn"),
                        reward=reward, context=context)
        if _evaluator:
            try:
                from brain.eval.evaluator_wal import append_pending as _ew_append_c1
                _ew_append_c1(_fb_decision_id, "reflect_on_self_beliefs", feats or {}, get_cycle_count(),
                              committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
            except Exception as _ewc1_e:
                log_model_issue(f"[evaluator] Path C WAL append failed: {_ewc1_e}")
    else:
        exec_result = execute_action_via_registries(sel, context, COG_MAP)
        reward = compute_reward(exec_result)
        feats = bandit_learn(sel, context, reward, decision_id=_fb_decision_id)
        record_decision(sel, reason_string(exec_result, reward, feats, "fallback.sel"),
                        reward=reward, context=context)
        if _evaluator:
            try:
                from brain.eval.evaluator_wal import append_pending as _ew_append_c2
                _ew_append_c2(_fb_decision_id, sel, feats or {}, get_cycle_count(),
                              committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
            except Exception as _ewc2_e:
                log_model_issue(f"[evaluator] Path C (sel) WAL append failed: {_ewc2_e}")
        if isinstance(exec_result, dict) and exec_result.get("success"):
            acted_this_cycle = True
            context["last_action_ts"] = time.time()

    return context, reward, acted_this_cycle
