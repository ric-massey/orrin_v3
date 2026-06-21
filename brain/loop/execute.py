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
from typing import Any, Dict
from brain.think.think_utils.action_gate import take_action
from brain.think.loop_helpers import (
    emotional_delta_reward,
    blend_reward,
    reason_string,
    bandit_learn,
)
from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
from brain.cognition.planning.reflection import record_decision
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.json_utils import load_json
from brain.utils.log import log_error, log_activity, log_model_issue
from brain.utils.emotion_utils import log_penalty_signal
from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure
from brain.paths import (
    WORKING_MEMORY_FILE,
)

from brain.loop.telemetry import _push_event, _ui_memory, _bridge
from brain.loop.invoke import _invoke_cognition
from brain.loop.constants import _OUTWARD_FNS

_log = get_logger(__name__)
Context = Dict[str, Any]


def execute_behavior_action(context, result, _decision_id, _evaluator, BEH_NAMES):
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

    return context, reward

def execute_cognition_function(context, result, _decision_id, _evaluator, _mem_daemon, affect_state):
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
            _snap = None
            _tick_ms = None
            _env_delta = None
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
            _intero_t0 = time.perf_counter()
            fn_result = _invoke_cognition(
                fn, fn_name, context,
                args=result.get("args") if isinstance(result, dict) else None,
                kwargs=result.get("kwargs") if isinstance(result, dict) else None,
            )
            try:
                _lat_ms = (time.perf_counter() - _intero_t0) * 1000.0
                from brain.cognition.interoception import observe as _intero_observe
                _io = _intero_observe(fn_name, _lat_ms, context)
                _tb_io = _bridge()
                if _tb_io is not None and _io:
                    try:
                        _tb_io.update(interoception=_io)
                    except Exception:
                        pass
            except Exception as _ioe:
                record_failure("ORRIN_loop.interoception_observe", _ioe)
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
                _post_snap = _snap(context) if _snap else {}
                _env_r = _env_delta(_pre_snap, _post_snap) if _env_delta else 0.5
            except Exception:
                _env_r = 0.5
                _post_snap = {}

            # Detect dispatch-level failure: _invoke_cognition returns
            # {"status": "error", "error": "unsatisfiable_args: [...]"}
            # when a cognitive function's required args can't be filled
            # from context (e.g. add_goal(goal=), apply_emotion_routing(fn_scores=)).
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
                    _recent_wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
                    _dfs([e for e in _recent_wm[-25:] if isinstance(e, dict)])
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.15", _e)

            # Blend: env-delta (40%) + status (20%) + emotional delta (40%).
            # emotional_delta_reward captures how the function actually moved
            # Orrin's internal state — the reward signal the bandit was missing.
            _emo_r = emotional_delta_reward(_emo_pre, _emo_post)
            base_reward = blend_reward(0.6 * _env_r + 0.4 * _status_r, _emo_r)
            _blended_reward = base_reward
            try:
                from brain.cognition.reward_rate import update_reward_rate
                update_reward_rate(
                    context,
                    reward=float(_blended_reward),
                    committed_goal_id=(
                        (context.get("committed_goal") or {}).get("id")
                    ),
                )
                context["_reward_rate_updated_this_cycle"] = True
            except Exception as _e:
                record_failure("ORRIN_loop.update_reward_rate", _e)
            if _is_failure:
                base_reward = min(base_reward - 0.4, -0.1)
            # Apply goal-weighted reward on the cognition path, matching
            # the action path — so the bandit learns that cognition which
            # doesn't advance the committed goal is worth less.
            try:
                from brain.cognition.planning.goal_progress import goal_weighted_reward as _gwr_cog
                reward = _gwr_cog(base_reward, context, action_was_taken=not _is_failure, fn_name=fn_name)
            except Exception:
                reward = base_reward
            # Regulation discharge bonus — reward regulation when distress
            # was actually present at execution time.
            # Aldao et al. (2010) meta-analysis of emotion regulation:
            # strategy effectiveness is highly context-dependent; the critical
            # learning event is selecting the right strategy given the current
            # emotional state, not a measurable downstream state change.
            # Emotional state does not update within a single cognitive cycle —
            # update_affect_state() runs at cycle start, not inside functions.
            # Measuring pre/post delta within one cycle produces a spurious zero
            # because the comparison window is too narrow. Sheppes et al. (2014):
            # the bandit must learn that regulation during high-distress states
            # pays — the bonus must be conditioned on distress-at-execution, with
            # magnitude scaled to distress severity to create the correct gradient.
            _REGULATION_FNS = frozenset({
                "attempt_regulation", "reflect_on_affect",
                "investigate_unexplained_emotions", "check_affect_drift",
                "reflect_on_emotion_model", "apply_affective_feedback",
            })
            if fn_name in _REGULATION_FNS and not _is_failure:
                try:
                    _pre_neg = sum(
                        float((_emo_pre.get("core_signals") or _emo_pre).get(k) or 0)
                        for k in ["impasse_signal", "threat_level", "risk_estimate", "conflict_signal", "negative_valence"]
                    )
                    if _pre_neg > 0.45:
                        reward += min(0.18, 0.08 + _pre_neg * 0.15)
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.16", _e)
            # Dopaminergic novelty gate for outward perception reads
            # (Schultz 1997: dopamine signals prediction error / novelty,
            # not repetition). look_outward & friends previously farmed
            # standing bonuses 100+ times regardless of whether the glance
            # surfaced anything new — the reward leak. An empty or repeated
            # outward result is not a reward event.
            _OUTWARD_READ_FNS = frozenset({
                "look_outward", "look_around", "seek_novelty",
                "read_rss", "survey_environment",
            })
            _outward_low_novelty = False
            if fn_name in _OUTWARD_READ_FNS:
                try:
                    import hashlib as _hashlib
                    _norm = _fn_str.strip().lower()
                    _digest = (
                        _hashlib.sha1(_norm.encode("utf-8", "ignore")).hexdigest()
                        if _norm else ""
                    )
                    if not _norm or _digest == context.get("_last_outward_digest"):
                        _outward_low_novelty = True
                    context["_last_outward_digest"] = _digest
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.17", _e)
                if _outward_low_novelty:
                    # No novelty → no dopamine. Pull reward to the low end.
                    reward = min(reward, 0.1)

            # Outward-debt discharge bonus (FINDINGS 2026-06-12 data
            # sweep §11): look_outward was the worst-paid action in the
            # stats table while the metacog objective demanded outward
            # action — suppression can't beat a standing reward gap, so
            # pay the discharge itself. An outward act landing after a
            # long internal-only stretch earns a bonus scaled by the
            # debt it clears; the novelty gate above keeps a repeated
            # empty glance from farming it.
            try:
                if (fn_name in _OUTWARD_FNS and not _is_failure
                        and not _outward_low_novelty):
                    _od_pay = int(context.get("_outward_debt", 0) or 0)
                    if _od_pay >= 8:
                        reward += min(0.25, 0.10 + (_od_pay - 8) * 0.01)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.17b", _e)

            # Dopaminergic habituation — LEARNING-AWARE (Schultz 1997:
            # dopamine tracks prediction error / novelty, not repetition).
            # This is the natural pressure that replaces the old hard
            # anti-repeat cap: repeating the SAME function gets boring
            # (reward decays) ONLY when it isn't paying off — i.e. when his
            # reward EMA for it is flat or falling. If repeating it keeps
            # IMPROVING reward (he's trying it differently and learning), it
            # is NOT habituated and he's free to keep going. So mindless
            # loops fade on their own; productive iteration continues.
            try:
                _rp8 = context.get("recent_picks", [])[-8:]
                _rep_n = max(0, _rp8.count(fn_name) - 1)
                _improving = float((context.get("_fn_ema_delta") or {}).get(fn_name, 0.0)) > 0.0
                if _rep_n > 0 and not _improving:
                    # Bored: steeper, deeper decay so a stale loop reliably
                    # loses to alternatives (down toward ~0 instead of a 0.2 floor).
                    if fn_name in _OUTWARD_READ_FNS:
                        _habituation = max(0.05, 1.0 - _rep_n * 0.32)
                    else:
                        _habituation = max(0.1, 1.0 - _rep_n * 0.22)
                    reward *= _habituation
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.18", _e)

            # Social baseline penalty — absence of user dampens intrinsic reward.
            # Based on Coan & Beckes (2010) social baseline theory: internal
            # rewards are calibrated against social presence. Extended silence
            # (>30 min) progressively reduces reward for all non-social functions,
            # creating a real pull toward engagement. Floor at 80% so Orrin
            # doesn't collapse into chronic risk_estimate during long autonomous runs.
            try:
                _sil_s = float((context.get("social_presence") or {}).get("silence_s") or 0.0)
                if _sil_s > 1800:
                    _absence_mod = max(0.80, 1.0 - (_sil_s / 3600.0) * 0.10)
                    reward *= _absence_mod
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.19", _e)

            # Solo-mode introvert bonus — deep internal work earns more
            # reward during absence, not merely less penalty.
            # Aron & Aron (1997) sensory-processing sensitivity: introverted
            # systems show heightened processing depth during low-stimulation
            # periods; solitary reflection produces genuine positive affect, not
            # just absence of overstimulation. Kaplan & Kaplan (1989) attention
            # restoration theory: directed attention (scanning, searching)
            # depletes; fascination-driven internal processing (integration,
            # symbolic reasoning) restores. The social baseline above correctly
            # penalizes look_outward as a connection substitute; this bonus
            # creates the opposing pull toward genuine restorative solo work.
            _INTROVERT_FNS = frozenset({
                "run_symbolic_dream", "run_rule_compression",
                "run_forgetting_cycle", "run_symbolic_prediction_cycle",
                "reflect_on_affect", "narrative_update",
                "update_latent_identity", "propose_value_revision",
                "audit_reflective_claims", "run_self_improvement",
                "reflect_on_cognition_rhythm", "run_active_experiment",
                "detect_memory_contradictions", "repair_contradictions",
            })
            try:
                _sil_s_solo = float((context.get("social_presence") or {}).get("silence_s") or 0.0)
                if _sil_s_solo > 1800 and fn_name in _INTROVERT_FNS:
                    reward += 0.15
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.20", _e)

            # Tier 2: SDT value alignment bonus.
            # Functions that match Orrin's stated core values earn a
            # standing reward boost. Based on Deci & Ryan (2000): intrinsic
            # motivation produces deeper, more stable learning than extrinsic
            # reward alone. Value-aligned behavior should be self-reinforcing.
            # One value match per function (cap 0.12) — enough to tilt the
            # bandit over many cycles without overwhelming the signal.
            try:
                _sm   = context.get("self_model") or {}
                _vals = [
                    str((v.get("value") if isinstance(v, dict) else v) or "").lower()
                    for v in (_sm.get("core_values") or [])
                ]
                _fn_l = fn_name.lower()
                _V2KW = {
                    "exploration_drive":  {"search","look","investigate","wiki","rss","explore","perception","outward"},
                    "growth":     {"improve","learn","write","discover","synthesis","dream","compress","self_improv","extension"},
                    "honesty":    {"audit","detect","repair","reflect","contradict","verify","integrity","rhythm"},
                    "connection": {"note","speak","social","user","thread","leave","person"},
                    "depth":      {"symbolic","dream","compress","rule","reason","introspect","predict","analogy","emotion"},
                }
                _val_bonus = 0.0
                for _val in _vals:
                    if any(_kw in _fn_l for _kw in _V2KW.get(_val, set())):
                        _val_bonus = 0.10
                        break
                # Don't pay the value-alignment standing bonus to an outward
                # read that surfaced nothing new — that was the leak that let
                # look_outward accrue +0.10 every cycle regardless of outcome.
                if _outward_low_novelty:
                    _val_bonus = 0.0
                reward += _val_bonus
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.21", _e)

            # Growth-orientation standing bonus.
            # Functions that expand capability or deepen self-understanding
            # earn an additional baseline reward independent of value matching.
            # Based on Ryan & Deci (2000): intrinsic motivation toward mastery
            # and growth is qualitatively distinct from task-completion reward —
            # it needs its own signal or it loses to easier, more frequent wins.
            _GROWTH_FNS = frozenset({
                "write_cognitive_function", "write_tool", "discover_new_emotion",
                "run_self_improvement", "reflect_on_affect", "reflect_on_emotion_model",
                "update_latent_identity", "narrative_update", "propose_value_revision",
                "run_symbolic_dream", "run_rule_compression", "audit_reflective_claims",
                "investigate_unexplained_emotions", "detect_memory_contradictions",
                "repair_contradictions", "run_symbolic_prediction_cycle",
                "run_forgetting_cycle", "run_benchmark", "reflect_on_cognition_rhythm",
                "research_topic", "fetch_and_read",
            })
            if fn_name in _GROWTH_FNS:
                reward += 0.12

            # Competence legibility: write a visible completion record to
            # working memory — but only for significant accomplishments.
            # Bandura (1977) self-efficacy theory: mastery experiences are
            # constituted by challenging tasks; feedback on routine execution
            # does not build efficacy and risks diluting the signal value of
            # genuine achievement. Locke & Latham (2002) goal-setting theory:
            # performance feedback must be proximal to meaningful accomplishment
            # to be effective — indiscriminate positive feedback creates noise
            # that erodes the discriminability of real completion signals.
            # White (1959) effectance motivation: the intrinsic drive is toward
            # producing effects that matter, not toward any effect whatsoever.
            # Trigger: growth functions, regulation functions, or substantive
            # output (>120 chars) — not every successful call.
            _is_significant_completion = (
                fn_name in _GROWTH_FNS
                or fn_name in _REGULATION_FNS
                or (not _is_failure and len(_fn_str) > 120)
            )
            if not _is_failure and _is_significant_completion and _fn_str:
                try:
                    from brain.cog_memory.working_memory import update_working_memory as _uwm_comp
                    _uwm_comp(f"[done] {fn_name}: {_fn_str[:80].strip().rstrip('.')}")
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.22", _e)

            # Outcome coupling — introspection can't outpay reality.
            # The standing bonuses above (value alignment, growth,
            # regulation, emotional delta) summed to ~0.55–0.73 for
            # introspective picks even on cycles where env_snapshot
            # measured zero observable change (delta_reward=0.000,
            # thrash=True) — which is how assess_goal_progress +
            # update_affect_state became 60% of all decisions while
            # outward action paid less. If a self-inspection function
            # produced no observable change (no milestone, no memory
            # write, no tool resolution, WM unchanged), its reward is
            # capped below what productive work earns. Introspection
            # that DOES move something external (env_r ≥ 0.35) still
            # pays in full.
            _INTROSPECTIVE_FNS = frozenset({
                "assess_goal_progress", "update_affect_state",
                "search_own_files", "reflect_on_internal_agents",
                "reflect_on_affect", "reflect_on_emotion_model",
                "check_affect_drift", "audit_reflective_claims",
                "reflect_on_outcomes", "reflect_on_self_beliefs",
                "detect_memory_contradictions",
                "reflect_on_cognition_patterns", "reflect_on_internal_voices",
                "summarize_relationships", "periodic_self_review",
                "reflect_on_effectiveness", "reflect_on_opinions",
                "reflect_on_growth_history", "process_regret",
                "read_vitals", "check_user_presence",
            })
            try:
                if (not _is_failure
                        and fn_name in _INTROSPECTIVE_FNS
                        and float(_env_r) < 0.35):
                    reward = min(reward, 0.35)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.23", _e)

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

# Path C: fallback (skipped entirely on silent/unconscious cycles)

    return context, reward
