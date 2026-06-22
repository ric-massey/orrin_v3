# brain/think/think_utils/action_gate_execute.py
# Action execution for the action gate (Phase 4.5C, from action_gate.py):
# take_action dispatches a chosen behavioral action — speaking, behavior-registry
# functions, reward/fatigue bookkeeping, and failure handling — and is the half
# evaluate_and_act_if_needed calls once it has decided WHAT to run. Imports the
# helpers leaf (_cycles); action_gate re-exports take_action.
from brain.core.runtime_log import get_logger
from datetime import datetime, timezone
import time
from pathlib import Path

from brain.behavior.speak import OrrinSpeaker
from brain.affect.reward_signals.reward_signals import release_reward_signal
from brain.affect.reward_signals.resource_deficit import update_function_usage_fatigue
from brain.cog_memory.working_memory import update_working_memory
from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS
from brain.utils.json_utils import save_json, load_json
from brain.utils.log import log_private, log_model_issue, log_activity
from brain.paths import GOALS_FILE
from brain.think.think_utils.talk_policy import (
    speak_text,
)
from brain.utils.failure_counter import record_failure
from brain.think.think_utils.action_gate_helpers import _cycles

_log = get_logger(__name__)

MAX_RETRIES = 3


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
