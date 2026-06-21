"""Cognitive-loop action/cognition execution stages (Phase 4A, extracted from
the ORRIN_loop entrypoint).

After think() returns a decision, the loop dispatches it: `execute_behavior_action`
runs a behavior `result["action"]` (Path A) — take_action, success/grounding-blended
reward, the bandit + decision/WAL accounting, and the conversation long-memory
write. It returns the cycle's (context, reward); feats/acted are internal. The
`if/elif` that selects Path A vs Path B (cognition function) stays in the loop.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
import time
from typing import Any, Dict
from brain.think.think_utils.action_gate import take_action
from brain.think.loop_helpers import (
    reason_string,
    bandit_learn,
)
from brain.cognition.planning.reflection import record_decision
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.log import log_error, log_activity, log_model_issue
from brain.utils.emotion_utils import log_penalty_signal
from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure

from brain.loop.telemetry import _push_event

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
