"""Cognitive-loop action accounting (Phase 4A, extracted from the ORRIN_loop
entrypoint).

`account_action()` runs right after the cycle's decision is dispatched: fold any
late `__acted_this_tick__` signal into acted_this_cycle, run the unconscious
emotion-drift check, update the committed goal's action-debt, fire the stall
watchdog (force a minimum-viable action when a goal has gone too long without
one), and emit the transparency trace. Mutates context in place; fail-safe.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
import time
from typing import Any, Dict
from brain.think.think_utils.action_gate import take_action
from brain.think.loop_helpers import (
    emit_trace,
    bandit_learn,
)
from brain.control_signals.signal_drift import check_affect_drift
from brain.cognition.planning.reflection import record_decision
from brain.utils.log import log_activity, log_model_issue
from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)
Context = Dict[str, Any]


def account_action(
    context: Context,
    result: Any,
    acted_this_cycle: bool,
    BEH_NAMES: Any,
) -> Context:
    acted_this_cycle = acted_this_cycle or bool(context.pop("__acted_this_tick__", False))

    # Emotion drift check always runs — it's unconscious monitoring, not conscious thought
    try:
        check_affect_drift(context)
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.25", _e)

    try:
        if context.get("committed_goal"):
            context["action_debt"] = 0 if acted_this_cycle else int(context.get("action_debt", 0)) + 1
    except Exception as _e:
        log_model_issue(f"Guardrail accounting issue: {_e}")

    # Stall watchdog (raised from 90→180 because inner-loop cycles are longer)
    try:
        STALL_SEC = 180
        now = time.time()
        if context.get("committed_goal"):
            last_ts = float(context.get("last_action_ts", 0.0) or 0.0)
            if (now - last_ts) > STALL_SEC:
                goal = context.get("committed_goal") or {}
                mv = goal.get("next_action")
                if isinstance(mv, dict):
                    mv_type = mv.get("type")
                    if mv_type in BEH_NAMES:
                        try:
                            ok = take_action(mv, context, context.get("speaker"))
                            if ok:
                                acted_this_cycle = True
                                context["last_action_ts"] = time.time()
                                context["action_debt"] = 0
                                log_activity(f"Watchdog executed MV action: {mv_type}")
                            else:
                                log_model_issue("Watchdog tried MV action; take_action returned False.")
                            _wd_reward = 0.8 if ok else 0.0
                            import uuid as _uuid_wd
                            _wd_decision_id = str(_uuid_wd.uuid4())
                            # Learn from the watchdog action; the returned feats
                            # are not consumed here (record_decision below omits
                            # them), so don't bind them.
                            bandit_learn(str(mv_type), context, _wd_reward, decision_id=_wd_decision_id)
                            record_decision(str(mv_type), "watchdog minimum viable action",
                                            reward=_wd_reward, context=context)
                        except Exception as _e:
                            route_exception(_e, phase="action", context=context,
                                            extra={"mv_type": mv_type})
                            _ = try_auto_repair({"type": _e.__class__.__name__, "msg": str(_e),
                                                 "trace": "", "phase": "action"}, context)
                            log_model_issue(f"Watchdog MV action failed: {_e}")
    except Exception as _e:
        log_model_issue(f"Watchdog error: {_e}")

    # Transparency trace
    try:
        chosen = None
        if isinstance(result, dict):
            if "action" in result:
                a = result["action"]
                chosen = f"ACTION:{a.get('type', 'unknown')}"
            elif "next_function" in result:
                chosen = f"FN:{result.get('next_function')}"
        emit_trace(
            chosen=chosen,
            debt=context.get("action_debt", 0),
            mode=context.get("mode"),
            emotions=context.get("affect_state", {}),
            committed=bool(context.get("committed_goal")),
            last_action_ts=context.get("last_action_ts"),
        )
    except Exception as _e:
        log_model_issue(f"Trace emit failed: {_e}")

    return context
