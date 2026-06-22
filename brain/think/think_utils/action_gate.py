# think/think_utils/action_gate.py
from brain.core.runtime_log import get_logger
import random
import json
from datetime import datetime, timezone
import time
from pathlib import Path

from brain.think.think_utils.escalate import escalate_with_behavior_list
from brain.cognition.behavior import extract_last_reflection_topic
from brain.behavior.behavior_generation import generate_behavior_from_integration
from brain.behavior.speak import OrrinSpeaker
from brain.affect.reward_signals.reward_signals import release_reward_signal
from brain.affect.reward_signals.resource_deficit import update_function_usage_fatigue, resource_deficit_penalty_from_context
from brain.cog_memory.working_memory import update_working_memory
from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS
from brain.utils.json_utils import save_json, load_json
from brain.utils.log import log_private, log_model_issue, log_activity
from brain.utils.emotion_utils import log_penalty_signal
from brain.paths import GOALS_FILE, FOCUS_GOAL

# === NEW: talk policy (hard/soft gating and reply plumbing) ===
from brain.think.think_utils.talk_policy import (
    SPEAK_TYPES,
    RECENT_USER_CYCLES,
    refresh_last_user_cycle,
    talk_policy_allows,
    talk_policy_score_bias,
    speak_text,
)
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Action Gate

MAX_RETRIES = 3
REFLECTIONY = {"reflect", "plan", "summarize", "analyz", "deliberat", "log", "think"}

# Support helpers + the action constants were extracted to action_gate_helpers.py
# (Phase 4.5C); re-imported so evaluate_and_act_if_needed below + external callers
# keep their references.
from brain.think.think_utils.action_gate_helpers import (  # noqa: E402,F401
    _NOISE, AGENTIC_TYPES, _VETO_ACTION_TYPES,
    propose_action, resolve_pending_actions, _novelty_for, _stamp_outcome,
    reflect_on_last_action, generate_clarification_question, moving_average,
    _cycles, update_adaptive_context, _maybe_inject_spontaneous_expression,
    _maybe_inject_user_response,
)


def evaluate_and_act_if_needed(
    context,
    affect_state,
    long_memory,
    speaker: OrrinSpeaker,
    phase: str = "cycle_end",
):
    """
    Evaluate pending actions and act if conditions are met.

    phase:
      "cycle_end"  — normal end-of-cycle call (default, current behaviour)
      "inner_loop" — called from inside the inner loop for early action on "act" decision

    Always returns a dict with at least {"decision": str, "acted": bool}.
    Legacy callers that ignore the return value are unaffected.
    """
    context.setdefault("pending_actions", [])
    context.setdefault("committed_goal", None)
    context.setdefault("action_debt", 0)
    context.setdefault("act_now", False)
    context.setdefault("minimum_viable_action", None)

    # Inner-loop phase: apply act bias from meta_controller if set
    if phase == "inner_loop" and context.get("_inner_loop_act_bias"):
        if not context.get("act_now") and context.get("committed_goal"):
            context["act_now"] = True

    # Inject a direct user reply before everything else (90% respond rate)
    _maybe_inject_user_response(context, affect_state)

    # keep "recent user" signal fresh for gating
    refresh_last_user_cycle(context)
    context["user_present_recent"] = (_cycles(context) - int(context.get("last_user_cycle") or -10_000)
                                      <= RECENT_USER_CYCLES)

    dynamic_max_cycles, derivative = update_adaptive_context(context)
    cur = context.get("cycles_since_agentic_action", 0)
    impasse_signal = context.get("impasse_signal", 0.0)

    focus_name = _current_focus_name() or ""

    # --- act_now path
    if context.get("act_now") and isinstance(context.get("minimum_viable_action"), dict):
        mv = context["minimum_viable_action"]
        mv_type = mv.get("type")
        if mv_type in BEHAVIORAL_FUNCTIONS:
            log_activity(f"🧭 Act-now: executing minimum viable action: {mv_type}")
            ok = take_action(mv, context, speaker)
            update_adaptive_context(context, mv_type)
            if ok:
                context["minimum_viable_action"] = None
                context["cycles_since_agentic_action"] = 0
                context["impasse_signal"] = max(0, context["impasse_signal"] - 0.2)
                context["last_action_ts"] = time.time()
                context["__acted_this_tick__"] = True
                outcome = {
                    "decision": "act",
                    "action": mv,
                    "success": True,
                    "novelty": _novelty_for(mv_type, context),
                    "acted": True,
                    "source": "act_now",
                }
                _stamp_outcome(context, outcome)
                return outcome

    # --- pending queue
    if context["pending_actions"]:
        # Resolve the behavioral queue once: veto-grade first, then urgency desc.
        # This is the single ActionArbiter decision for "what runs now" — it
        # replaces the old front-insertion priority hacking (D4).
        resolve_pending_actions(context)
        action = context["pending_actions"].pop(0)

        # HARD gate talk actions while pending.
        # Skip re-evaluation for already-deferred actions (defer_count > 0) — they've
        # already been gated this session; re-running the gate is a redundant LLM call
        # with the same conditions. Let already-deferred talk actions through so the
        # queue eventually drains.
        _needs_gate = action.get("type") in SPEAK_TYPES and action.get("defer_count", 0) == 0
        if _needs_gate and not talk_policy_allows(action.get("type"), context, affect_state):
            action["defer_count"] = int(action.get("defer_count", 0)) + 1
            if action["defer_count"] <= 6:
                context["pending_actions"].append(action)
            outcome = {
                "decision": "deferred",
                "action": action,
                "success": False,
                "novelty": _novelty_for(action.get("type", ""), context),
                "acted": False,
                "source": "pending_deferred_talk_policy",
            }
            _stamp_outcome(context, outcome)
            return outcome

        retries = action.get("retries", 0)
        success = take_action(action, context, speaker)
        update_adaptive_context(context, action.get("type"))
        reflection = reflect_on_last_action(context, action, success)

        text = (reflection or "").lower()
        if "ask the user" in text:
            question = generate_clarification_question(context, action)
            if question:
                propose_action(context, {
                    "type": "ask_user",
                    "content": question,
                    "urgency": 0.99,
                    "description": "Clarification requested for failed action.",
                })
        elif "retry" in text:
            if retries < MAX_RETRIES:
                action["retries"] = retries + 1
                # Retry re-vote: high urgency so it is reattempted ahead of routine
                # proposals, but still below veto/user-reply tiers.
                propose_action(context, action, urgency=0.90)
            else:
                return escalate_with_behavior_list(
                    context=context,
                    action=action,
                    last_error=context.get("last_error", ""),
                    retries=retries,
                )
        outcome = {
            "decision": "act",
            "action": action,
            "success": bool(success),
            "novelty": _novelty_for(action.get("type", ""), context),
            "acted": True,
            "source": "pending",
        }
        if success:
            context["last_action_ts"] = time.time()
            context["__acted_this_tick__"] = True
        _stamp_outcome(context, outcome)
        return outcome

    # --- propose actions
    context["last_reflection_topic"] = extract_last_reflection_topic()
    possible_actions = context.pop("behavior_proposals", None) or generate_behavior_from_integration(context)
    if not possible_actions:
        return {"decision": "defer", "acted": False, "source": "no_proposals"}

    FALLBACK_TYPES = {"ask_user", "write_file", "execute_python_code", "speak", "user_response", "refuse"}
    filtered_actions = []
    for action in possible_actions:
        action_type = action.get("type")
        meta = BEHAVIORAL_FUNCTIONS.get(action_type)
        if (meta and meta.get("is_action")) or (action_type in FALLBACK_TYPES):
            filtered_actions.append(action)
    if not filtered_actions:
        return {"decision": "defer", "acted": False, "source": "no_filtered_actions"}

    def score_action(action, affect_state, long_memory):
        base = action.get("urgency", 0.5)
        _emo_core = affect_state.get("core_signals", {}) or {}
        drive = _emo_core.get("drive", affect_state.get("drive", 0.0))
        novelty = _emo_core.get("novelty", affect_state.get("novelty", 0.0))
        motivation = _emo_core.get("motivation", affect_state.get("motivation", 0.5))

        resource_deficit_pen = resource_deficit_penalty_from_context(affect_state, action.get("type"))
        stagnation_boost = 0.11 * context.get("cycles_since_agentic_action", 0) if action.get("type") in AGENTIC_TYPES else 0
        derivative_boost = 0.09 * derivative if action.get("type") in AGENTIC_TYPES and derivative > 0 else 0

        is_reflectiony = any(key in (action.get("type", "").lower()) for key in REFLECTIONY)
        impasse_signal_penalty = -0.25 * impasse_signal if is_reflectiony else 0.0
        act_now_bonus = 0.18 if (context.get("act_now") and action.get("type") in AGENTIC_TYPES) else 0.0
        if context.get("act_now") and is_reflectiony:
            act_now_bonus -= 0.22

        # Introspection overload: penalise further inward-facing actions when already overloaded
        overload_penalty = 0.0
        if context.get("_introspection_overload"):
            try:
                from brain.cognition.cognitive_cost import is_introspective
                if is_introspective(action.get("type", "")):
                    overload_penalty = -0.20
            except Exception as _e:
                record_failure("action_gate.evaluate_and_act_if_needed.score_action", _e)

        # Focus alignment bonus
        focus_bonus = 0.0
        if focus_name:
            if action.get("goal_name") == focus_name:
                focus_bonus += 0.25
            else:
                desc = (action.get("description") or "").lower()
                cont = action.get("content")
                if not isinstance(cont, str):
                    try:
                        cont = json.dumps(cont, default=str)
                    except Exception:
                        cont = ""
                if focus_name.lower() in desc or focus_name.lower() in (cont or "").lower():
                    focus_bonus += 0.15

        emotion_bonus = drive + novelty + (0.2 * motivation)

        # Flow state bonus: sustain momentum when already in flow
        flow_depth = int(context.get("_flow_depth") or 0)
        flow_bonus = min(0.20, 0.05 * flow_depth) if flow_depth >= 1 and action.get("type") in AGENTIC_TYPES else 0.0

        score = base + emotion_bonus - resource_deficit_pen + stagnation_boost + derivative_boost + impasse_signal_penalty + act_now_bonus + focus_bonus + overload_penalty + flow_bonus

        if action.get("type") == "user_response":
            score += 0.2

        # Soft talk-policy bias
        score += talk_policy_score_bias(action.get("type", ""), context, affect_state)

        score += random.gauss(0, 0.05)
        return max(0.0, min(1.0, score))

    scored = [(action, score_action(action, affect_state, long_memory)) for action in filtered_actions]
    scored.sort(key=lambda x: x[1], reverse=True)
    if len(scored) > 1:
        context["pending_actions"].extend([a for a, _ in scored[1:]])

    # force an agentic action if stagnating
    agentic_actions = [a for a in filtered_actions if a["type"] in AGENTIC_TYPES]
    if cur >= dynamic_max_cycles and agentic_actions:
        log_private(f"🚨 Stagnation: Forcing agentic action after {cur} cycles (max {dynamic_max_cycles})")
        from brain.affect.affect_learning import update_affect_function_map
        update_affect_function_map("impasse_signal", "agentic_action")
        context["stagnation_signal_count"] = 0
        context["cycles_since_agentic_action"] = 0
        best_agentic, _ = max(((a, score_action(a, affect_state, long_memory)) for a in agentic_actions), key=lambda x: x[1])
        novelty_reward = 0.4 + 0.05 * cur
        agentic_ok = take_action(best_agentic, context, speaker)
        context["last_action_ts"] = time.time()
        context["__acted_this_tick__"] = True
        release_reward_signal(context, "reward_signal", novelty_reward, 0.6, 0.8, source="forced_agentic_action")
        update_working_memory({
            "content": f"Forcing agentic action: {best_agentic['type']} after {cur} cycles.",
            "event_type": "forced_action",
            "importance": 2,
            "priority": 2,
        })
        context["impasse_signal"] = max(0, context["impasse_signal"] - 0.2)
        outcome = {
            "decision": "act",
            "action": best_agentic,
            "success": bool(agentic_ok),
            "novelty": max(0.0, min(1.0, 0.4 + 0.05 * cur)),
            "acted": True,
            "source": "forced_agentic",
        }
        _stamp_outcome(context, outcome)
        return outcome

    if cur >= dynamic_max_cycles and not agentic_actions:
        log_private("⚠️ impasse_signal maxed, but no agentic action available—defaulting to random action.")
        log_penalty_signal(context, "impasse_signal", increment=0.5 + 0.05 * cur)
        action, _ = random.choice(scored)
        random_ok = take_action(action, context, speaker)
        context["last_action_ts"] = time.time()
        context["__acted_this_tick__"] = True
        update_working_memory({
            "content": f"Random action due to stagnation: {action['type']}",
            "event_type": "forced_action",
            "importance": 1,
            "priority": 1,
        })
        outcome = {
            "decision": "act",
            "action": action,
            "success": bool(random_ok),
            "novelty": _novelty_for(action.get("type", ""), context, forced=True),
            "acted": True,
            "source": "forced_random",
        }
        _stamp_outcome(context, outcome)
        return outcome

    best_action, best_score = scored[0]

    if best_action["type"] in AGENTIC_TYPES:
        context["cycles_since_agentic_action"] = 0
    else:
        context["cycles_since_agentic_action"] += 1
    update_adaptive_context(context, best_action["type"])

    # HARD gate the chosen action if it's a talk action
    if best_action.get("type") in SPEAK_TYPES and not talk_policy_allows(best_action.get("type"), context, affect_state):
        best_action["defer_count"] = int(best_action.get("defer_count", 0)) + 1
        if best_action["defer_count"] <= 6:
            context["pending_actions"].append(best_action)
        outcome = {
            "decision": "deferred",
            "action": best_action,
            "success": False,
            "novelty": _novelty_for(best_action.get("type", ""), context),
            "acted": False,
            "source": "scored_deferred_talk_policy",
        }
        _stamp_outcome(context, outcome)
        return outcome

    if best_score >= 0.75:
        best_action["retries"] = 0
        success = take_action(best_action, context, speaker)
        reflection = reflect_on_last_action(context, best_action, success)

        text = (reflection or "").lower()
        if "ask the user" in text:
            question = generate_clarification_question(context, best_action)
            if question:
                propose_action(context, {
                    "type": "ask_user",
                    "content": question,
                    "urgency": 0.99,
                    "description": "Clarification requested for failed action.",
                })
        elif "retry" in text:
            best_action["retries"] = 1
            propose_action(context, best_action, urgency=0.90)

        if success:
            update_function_usage_fatigue(context, best_action["type"])
            _emo_core = affect_state.get("core_signals") or affect_state
            motivation = _emo_core.get("motivation", 0.5)
            resource_deficit = float(affect_state.get("resource_deficit") or 0.0)
            actual_reward = 0.6 * (1 - resource_deficit) * (0.5 + motivation) + 0.18 * context.get("impasse_signal", 0.0)
            release_reward_signal(context, "reward_signal", actual_reward, 0.5, 0.5, source="action_gate")
            context["last_action_taken"] = best_action
            update_working_memory({
                "content": f"Executed: {best_action['type']} - {best_action.get('description', '')}",
                "event_type": "action",
                "importance": 2,
                "priority": 2,
            })
            if "goal_name" in best_action:
                try:
                    from brain.cognition.planning.goals import mark_goal_completed
                    from brain.cognition.planning import goal_arbiter
                    _gname = best_action["goal_name"]
                    # Atomic load→complete→save through the GoalArbiter, with an
                    # idempotency guard (status != "completed") so a goal already
                    # completed elsewhere this window cannot be double-completed /
                    # double-rewarded — the uncoordinated-write race this raw
                    # load_json/save_json path used to lose (dual_process_loop.md §20.3).
                    def _auto_complete(_goals):
                        for _g in _goals:
                            if (isinstance(_g, dict) and _g.get("name") == _gname
                                    and _g.get("status") != "completed"):
                                mark_goal_completed(_g)
                                break
                        return _goals
                    goal_arbiter.apply(_auto_complete, source="action_gate.auto_complete")
                except Exception as e:
                    log_model_issue(f"Could not auto-complete goal '{best_action.get('goal_name')}': {e}")
            context["impasse_signal"] = max(0, context["impasse_signal"] - 0.2)
            context["last_action_ts"] = time.time()
            context["__acted_this_tick__"] = True
            outcome = {
                "decision": "act",
                "action": best_action,
                "success": True,
                "novelty": _novelty_for(best_action.get("type", ""), context),
                "acted": True,
                "source": "scored_best",
            }
            _stamp_outcome(context, outcome)
            return outcome
        else:
            log_model_issue("⚠️ Action was selected but failed during execution.")
            outcome = {
                "decision": "act",
                "action": best_action,
                "success": False,
                "novelty": 0.05,
                "acted": True,
                "source": "scored_best",
            }
            _stamp_outcome(context, outcome)
            return outcome

    return {"decision": "defer", "acted": False, "source": "score_below_threshold"}

def take_action(action, context, speaker: OrrinSpeaker):
    action_type = action.get("type")
    content = action.get("content", "")
    data = action.get("data")
    path = action.get("path")
    description = action.get("description", action_type)
    log_parameters = {k: v for k, v in action.items() if k != "description"}
    timestamp = datetime.now(timezone.utc).isoformat()

    importance = 2
    if isinstance(action, dict) and "importance" in action:
        importance = action["importance"]
    elif isinstance(content, dict) and "importance" in content:
        importance = content["importance"]
    priority = max(1, int(importance / 2))

    def log_result(result="success", error=None):
        entry = {
            "timestamp": timestamp,
            "action_type": action_type,
            "description": description,
            "parameters": log_parameters,
            "result": result,
        }
        if error:
            entry["error"] = str(error)
        log_activity(entry)

    # Built-in action types handled inline below — must NOT be dispatched
    # through BEHAVIORAL_FUNCTIONS because toolkit functions with those names
    # expect different signatures (not (action, context, speaker)).
    _BUILTIN_TYPES = {
        "speak", "log", "update_file", "set_goal", "set_deadline",
        "user_response", "ask_user", "write_file", "execute_python_code",
    }

    try:
        meta = BEHAVIORAL_FUNCTIONS.get(action_type)
        if meta and action_type not in _BUILTIN_TYPES:
            func = meta.get("function")
            result = func(action, context, speaker)
            if result:
                update_function_usage_fatigue(context, action_type)
                release_reward_signal(
                    context, "reward_signal", 0.3 + 0.05 * importance, 0.5, 0.5, source=f"action:{action_type}"
                )
                update_working_memory({
                    "content": f"Executed action: {description}",
                    "event_type": "action",
                    "action_type": action_type,
                    "parameters": log_parameters,
                    "importance": importance,
                    "priority": priority,
                })
                log_result("success")
            else:
                release_reward_signal(context, "reward_signal", 0.2, 0.5, 0.7, source=f"action_fail:{action_type}")
                log_result("fail")
            return result

        # ------------------- NO DIRECT speaker.speak CALLS BELOW -------------------

        if action_type == "speak":
            final = speak_text(content, context, speaker)
            update_function_usage_fatigue(context, "speak")
            release_reward_signal(context, "reward_signal", 0.3 + 0.05 * importance, 0.5, 0.4, source="action:speak")
            update_working_memory({
                "content": f'Spoke: "{final or content}"',
                "event_type": "action",
                "action_type": "speak",
                "importance": importance,
                "priority": priority,
            })
            log_result("success")
            # stamp speak cycle
            context["last_speak_ts"] = time.time()
            context["last_speak_cycle"] = _cycles(context)
            return True

        elif action_type == "log":
            log_private(content)
            update_function_usage_fatigue(context, "log")
            release_reward_signal(context, "reward_signal", 0.3 + 0.05 * importance, 0.5, 0.3, source="action:log")
            update_working_memory({
                "content": f"Logged: {content}",
                "event_type": "action",
                "action_type": "log",
                "importance": importance,
                "priority": priority,
            })
            log_result("success")
            return True

        elif action_type == "update_file" and path and data:
            save_json(path, data)
            update_function_usage_fatigue(context, "update_file")
            release_reward_signal(context, "reward_signal", 0.3 + 0.05 * importance, 0.5, 0.6, source="action:update_file")
            update_working_memory({
                "content": f"Updated file: {path}",
                "event_type": "action",
                "action_type": "update_file",
                "parameters": {"path": path},
                "importance": importance,
                "priority": priority,
            })
            log_result("success")
            return True

        elif action_type == "set_deadline":
            # Orrin commits himself to a time limit on a goal.
            # action = {"type": "set_deadline", "goal": "<title or id>", "hours": <float>}
            goal_ref = action.get("goal") or action.get("goal_name") or str(content or "")
            hours = float(action.get("hours") or action.get("time_hours") or 2.0)
            if not goal_ref:
                log_model_issue("set_deadline: missing 'goal' field")
                log_result("fail")
                return False
            try:
                from brain.cognition.temporal_pressure import set_goal_deadline
                ok = set_goal_deadline(goal_ref, hours, context=context)
            except Exception as _e:
                log_model_issue(f"set_deadline failed: {_e}")
                ok = False
            if ok:
                log_result("success")
            else:
                log_result("fail")
            return ok

        elif action_type == "set_goal":
            goals = load_json(GOALS_FILE, default_type=list)
            if not isinstance(goals, list):
                goals = []
            goal_data = content if isinstance(content, dict) else {"name": str(content)}
            goal_data.setdefault("tier", "short_term")
            goal_data.setdefault("status", "pending")
            goal_data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            goal_data.setdefault("last_updated", goal_data["timestamp"])
            goal_data.setdefault("emotional_intensity", 0.5)
            goal_data.setdefault("history", [{"event": "created", "timestamp": goal_data["timestamp"]}])
            if not any(isinstance(g, dict) and g.get("name") == goal_data.get("name") for g in goals):
                goals.append(goal_data)
                save_json(GOALS_FILE, goals)
                context["goals"] = goals
                update_function_usage_fatigue(context, "set_goal")
                release_reward_signal(context, "reward_signal", 0.3 + 0.05 * importance, 0.5, 0.5, source="action:set_goal")
                goal_text = goal_data.get("name") or goal_data.get("description") or str(goal_data)
                update_working_memory({
                    "content": f"Set goal: {goal_text}",
                    "event_type": "action",
                    "action_type": "set_goal",
                    "importance": importance,
                    "priority": priority,
                })
                log_result("success")
                return True
            else:
                log_private(f"Goal '{goal_data.get('name')}' already exists. Skipping duplicate.")
                return True

        elif action_type == "refuse":
            # Orrin declines in his own voice — not a policy filter, a self with preferences
            reason = action.get("reason") or content or "I don't want to engage with that."
            _emo = context.get("affect_state", {})
            _core = (_emo.get("core_signals") or _emo)
            _impasse_signal = float(_core.get("impasse_signal", 0))
            _confidence  = float(_core.get("confidence", 0.5))
            if _impasse_signal > 0.5:
                _voice = f"No. {reason}"
            elif _confidence > 0.6:
                _voice = f"That's not something I'm interested in. {reason}"
            else:
                _voice = f"I'd rather not. {reason}"
            final = speak_text(_voice, context, speaker)
            release_reward_signal(context, "reward_signal", 0.4, 0.3, 0.3, source="action:refuse")
            update_working_memory({
                "content": f'[refused] {reason}',
                "event_type": "action",
                "action_type": "refuse",
                "importance": 3,
                "priority": 3,
            })
            log_result("success")
            context["last_speak_ts"] = time.time()
            context["last_speak_cycle"] = _cycles(context)
            return True

        elif action_type == "user_response":
            final = speak_text(content, context, speaker)
            context["last_user_response"] = final or content
            update_function_usage_fatigue(context, "user_response")
            release_reward_signal(context, "reward_signal", 0.3 + 0.05 * importance, 0.5, 0.4, source="action:user_response")
            update_working_memory({
                "content": f'User response (to user): "{final or content}"',
                "event_type": "action",
                "action_type": "user_response",
                "importance": importance,
                "priority": priority,
            })
            log_result("success")
            context["last_speak_ts"] = time.time()
            context["last_speak_cycle"] = _cycles(context)
            return True

        elif action_type == "ask_user":
            final = speak_text(content, context, speaker)
            update_function_usage_fatigue(context, "ask_user")
            release_reward_signal(context, "reward_signal", 0.32 + 0.05 * importance, 0.5, 0.4, source="action:ask_user")
            update_working_memory({
                "content": f'Question to user: "{final or content}"',
                "event_type": "action",
                "action_type": "ask_user",
                "importance": importance,
                "priority": priority,
            })
            log_result("success")
            context["last_speak_ts"] = time.time()
            context["last_speak_cycle"] = _cycles(context)
            return True

        elif action_type == "write_file":
            file_path = Path(action.get("path") or "")
            text = action.get("text", "")
            append = bool(action.get("append", False))
            only_if_missing = action.get("only_if_missing")
            if not file_path:
                log_model_issue("write_file missing 'path'")
                log_result("fail")
                return False
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                if only_if_missing and file_path.exists():
                    try:
                        existing = file_path.read_text(encoding="utf-8")
                        if str(only_if_missing) in existing:
                            log_private(f"⏩ Skipped write_file; marker already present in {file_path}")
                            log_result("success")
                            return True
                    except Exception as _e:
                        record_failure("action_gate.take_action", _e)
                mode = "a" if append else "w"
                with file_path.open(mode, encoding="utf-8") as f:
                    f.write(text)
                update_function_usage_fatigue(context, "write_file")
                release_reward_signal(context, "reward_signal", 0.35 + 0.05 * importance, 0.5, 0.5, source="action:write_file")
                update_working_memory({
                    "content": f"Wrote to file: {str(file_path)}",
                    "event_type": "action",
                    "action_type": "write_file",
                    "parameters": {"path": str(file_path)},
                    "importance": importance,
                    "priority": priority,
                })
                log_result("success")
                return True
            except Exception as e:
                log_private(f"write_file failed: {e}")
                log_result("exception", error=e)
                return False

        elif action_type == "append_thought":
            # Structured, data-only thought effect (function_selection_fix_v2.md
            # Phase 5 / Option A). Replaces the auto-generated write-a-stub +
            # execute_python_code pair: the stub only appended a thought to
            # working memory, so this captures that effect with no code path.
            content = action.get("content", "")
            if not isinstance(content, str) or not content.strip():
                log_model_issue("append_thought missing 'content'")
                log_result("fail")
                return False
            update_working_memory({
                "content": content.strip()[:500],
                "event_type": str(action.get("thought_type") or "autonomous_behavior"),
                "action_type": "append_thought",
                "importance": importance,
                "priority": priority,
            })
            release_reward_signal(
                context, "reward_signal", 0.30 + 0.05 * importance, 0.5, 0.6, source="action:append_thought"
            )
            log_result("success")
            return True

        elif action_type == "execute_python_code":
            code = action.get("code", "")
            if not isinstance(code, str) or not code.strip():
                log_model_issue("execute_python_code missing 'code'")
                log_result("fail")
                return False
            # SECURITY (function_selection_fix_v2.md Phase 5): the previous handler
            # ran model-/auto-generated code via a BARE IN-PROCESS interpreter call
            # with full builtins — no AST check, no subprocess, no timeout, no rlimit.
            # That is removed. Auto-generated behaviors now emit append_thought
            # (Option A), so no code path is needed for them. Any remaining code
            # action is DISABLED by default; only when ALLOW_CODE_ACTIONS is set
            # does it run, and then through the hardened subprocess sandbox (AST
            # allowlist + POSIX rlimits + wall-clock timeout) — NEVER in-process.
            import os as _os
            if not _os.environ.get("ALLOW_CODE_ACTIONS"):
                log_private("execute_python_code rejected: code actions are disabled "
                            "(set ALLOW_CODE_ACTIONS=1 to enable the sandboxed path)")
                log_result("fail")
                return False
            try:
                from brain.behavior.tools.sandbox import run_python_sandboxed
                res = run_python_sandboxed(code, timeout_s=5)
            except ValueError as e:
                # AST allowlist rejection (disallowed import / builtin).
                log_private(f"execute_python_code blocked by sandbox AST check: {e}")
                log_result("fail")
                return False
            except Exception as e:
                log_private(f"execute_python_code sandbox error: {e}")
                log_result("exception", error=e)
                return False
            if res.get("status") == "ok":
                update_function_usage_fatigue(context, "execute_python_code")
                release_reward_signal(
                    context, "reward_signal", 0.36 + 0.05 * importance, 0.5, 0.6, source="action:execute_python_code"
                )
                update_working_memory({
                    "content": f"Executed (sandboxed) python code: {code[:160]}{'...' if len(code) > 160 else ''}",
                    "event_type": "action",
                    "action_type": "execute_python_code",
                    "importance": importance,
                    "priority": priority,
                })
                log_result("success")
                return True
            log_private(f"execute_python_code sandboxed run failed: {res}")
            log_result("fail")
            return False

        else:
            log_model_issue(f"⚠️ Unknown action type: {action_type}")
            update_working_memory({
                "content": f"⚠️ Unknown action type attempted: {action_type}",
                "event_type": "action_fail",
                "action_type": action_type,
                "importance": 1,
                "priority": 1,
            })
            release_reward_signal(context, "reward_signal", 0.1, 0.5, 0.7, source="action_fail:unknown")
            log_result("fail")
            return False

    except Exception as e:
        log_private(f"❌ take_action failed: {e}")
        update_working_memory({
            "content": f"⚠️ Failed to execute action: {description} — {e}",
            "event_type": "action_fail",
            "action_type": action_type,
            "importance": 1,
            "priority": 1,
        })
        release_reward_signal(context, "reward_signal", 0.1, 0.5, 0.8, source="action_fail:exception")
        log_result("exception", error=e)
        return False

def _current_focus_name():
    try:
        data = load_json(FOCUS_GOAL)
        if isinstance(data, dict):
            from brain.utils.goals import extract_current_focus_goal
            return extract_current_focus_goal(data)
    except Exception as _e:
        record_failure("action_gate._current_focus_name", _e)
    return None
