from typing import Dict, Any, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_model_issue, log_activity, utc_now as _utc_now_iso
from cog_memory.working_memory import update_working_memory
from cog_memory.long_memory import update_long_memory
from paths import GOALS_FILE
from utils.self_model import get_self_model, save_self_model, ensure_self_model_integrity
from affect.reward_signals.reward_signals import release_reward_signal
# Canonical reward emitter — single shared wrapper (was a byte-identical private
# duplicate of finalize.py's _reward).
from affect.reward_signals.reward_signals import release_reward as _reward



def _safe_load_list(path: str) -> list:
    data = load_json(path, default_type=list)
    return data if isinstance(data, list) else []


def _append_long_memory(content: str, event_type: str) -> None:
    update_long_memory(content, event_type=event_type, importance=2, priority=1)


def execute_cognitive_action(action_dict: Dict[str, Any], context: Optional[dict] = None) -> Dict[str, Any]:
    """
    Handle cognitive-level actions that do not trigger behavioral output.
    Includes modifying goals, internal beliefs, or the self-model.
    Returns a result dictionary for telemetry/testing.
    """
    if not isinstance(action_dict, dict):
        log_model_issue("❌ execute_cognitive_action() received non-dict input.")
        return {"ok": False, "reason": "invalid_input"}

    action_type = str(action_dict.get("action", "")).lower().strip()
    ts = _utc_now_iso()

    # === 1. Add Goal ===
    if action_type == "add_goal":
        goal = action_dict.get("goal")
        if not isinstance(goal, dict):
            log_model_issue("⚠️ Invalid goal format in add_goal action.")
            return {"ok": False, "reason": "invalid_goal"}

        goals = _safe_load_list(GOALS_FILE)

        # Normalize goal
        name = goal.get("name") or goal.get("description") or f"goal_{len(goals)+1}"
        goal_norm = {
            "name": name,
            "description": goal.get("description", name),
            "status": goal.get("status", "pending"),
            "origin": goal.get("origin", "cognitive_action"),
            "timestamp": goal.get("timestamp", ts),
            "last_updated": goal.get("last_updated", ts),
            **{k: v for k, v in goal.items() if k not in {"name", "description", "status", "origin", "timestamp", "last_updated"}},
        }

        # De-dup by name
        if any(isinstance(g, dict) and g.get("name") == goal_norm["name"] for g in goals):
            log_activity(f"[execute_cognitive_action] Goal already exists: {goal_norm['name']}")
            return {"ok": True, "action": "add_goal", "deduped": True, "goal": goal_norm}

        goals.append(goal_norm)
        save_json(GOALS_FILE, goals)

        update_working_memory({
            "content": f"🧠 New goal added: {goal_norm['description']}",
            "event_type": "add_goal",
            "agent": "orrin",
            "importance": 2,
            "priority": 2,
            "referenced": 1,
            "timestamp": ts
        })
        log_activity(f"[execute_cognitive_action] Added goal: {goal_norm}")

        _reward(context, signal="reward_signal", actual=0.6, expected=0.4, effort=0.5, mode="phasic", source="add_goal")
        return {"ok": True, "action": "add_goal", "goal": goal_norm}

    # === 2. Update Belief ===
    if action_type == "update_belief":
        belief = action_dict.get("belief")
        if not isinstance(belief, str) or not belief.strip():
            log_model_issue("⚠️ Invalid belief format in update_belief action.")
            return {"ok": False, "reason": "invalid_belief"}

        _append_long_memory(f"Belief updated: {belief}", event_type="update_belief")

        update_working_memory({
            "content": f"🧠 Updated belief: {belief}",
            "event_type": "update_belief",
            "agent": "orrin",
            "importance": 2,
            "priority": 1,
            "referenced": 1,
            "timestamp": ts
        })
        log_activity(f"[execute_cognitive_action] Updated belief: {belief}")

        _reward(context, signal="reward_signal", actual=0.5, expected=0.4, effort=0.6, mode="phasic", source="update_belief")
        return {"ok": True, "action": "update_belief", "belief": belief}

    # === 3. Revise Self Model ===
    if action_type == "revise_self_model":
        patch = action_dict.get("patch")
        if not isinstance(patch, dict) or not patch:
            log_model_issue("⚠️ Invalid patch format in revise_self_model action.")
            return {"ok": False, "reason": "invalid_patch"}

        model = get_self_model()
        if not isinstance(model, dict):
            model = {}
        model.update(patch)
        model = ensure_self_model_integrity(model)
        save_self_model(model)

        update_working_memory({
            "content": "🧠 Self-model revised.",
            "event_type": "revise_self_model",
            "agent": "orrin",
            "importance": 2,
            "priority": 2,
            "referenced": 1,
            "timestamp": ts
        })
        log_activity(f"[execute_cognitive_action] Self-model updated with patch: {patch}")

        _reward(context, signal="reward_signal", actual=0.7, expected=0.5, effort=0.8, mode="tonic", source="revise_self_model")
        return {"ok": True, "action": "revise_self_model", "patch_applied": patch}

    # === 4. Log Thought ===
    if action_type == "log_thought":
        content = action_dict.get("content")
        if not isinstance(content, str) or not content.strip():
            log_model_issue("⚠️ No content provided for log_thought.")
            return {"ok": False, "reason": "empty_content"}

        _append_long_memory(content, event_type="log_thought")

        update_working_memory({
            "content": f"🧠 Thought logged: {content}",
            "event_type": "log_thought",
            "agent": "orrin",
            "importance": 1,
            "priority": 1,
            "referenced": 0,
            "timestamp": ts
        })
        log_activity(f"[execute_cognitive_action] Thought logged to long-term memory.")

        _reward(context, signal="reward_signal", actual=0.3, expected=0.4, effort=0.2, mode="phasic", source="log_thought")
        return {"ok": True, "action": "log_thought"}

    # === Unknown Action ===
    log_model_issue(f"❓ Unknown cognitive action type: {action_type}")
    return {"ok": False, "reason": "unknown_action", "action": action_type}