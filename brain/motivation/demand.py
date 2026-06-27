# brain/motivation/demand.py
import random
from datetime import datetime, timezone
from brain.utils.log import log_private, log_error
from brain.cog_memory.working_memory import update_working_memory
from brain.affect.threat_detector import process_affective_signals

# Affect → preferred function when affectively dysregulated
_EMO_DRIVE_MAP = {
    "exploration_drive":    ["look_outward", "seek_novelty", "generate_concepts_from_memories"],
    "motivation":   ["pursue_committed_goal", "generate_intrinsic_goals", "plan_next_step"],
    "stagnation_signal":      ["seek_novelty", "look_outward", "search_own_files"],
    "impasse_signal":  ["reflection", "self_review", "assess_goal_progress"],
    "social_deficit":   ["generate_intrinsic_goals", "look_around"],
    "uncertainty":  ["reflection", "update_world_model"],
    "threat_level":         ["self_soothing", "reflection"],
    "negative_valence":      ["self_soothing", "reflection"],
    "risk_estimate":      ["self_soothing", "check_affect_drift", "reflection"],
}


def _symbolic_drive_choice(context: dict, available_functions: dict) -> str:
    """Pick a function based on dominant emotion and recent choice history."""
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    dominant = "exploration_drive"
    if isinstance(core, dict):
        candidates = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
        if candidates:
            dominant = max(candidates, key=candidates.get)

    preferred = _EMO_DRIVE_MAP.get(dominant, ["reflection", "look_outward", "seek_novelty"])
    recent = [c.get("choice", "") for c in (context.get("cognition_log") or [])[-3:] if isinstance(c, dict)]

    for fn in preferred:
        if fn not in recent and fn in available_functions:
            return fn

    available_list = [f for f in available_functions if f not in recent]
    if available_list:
        return random.choice(available_list)

    return list(available_functions.keys())[0] if available_functions else "reflection"


def persistent_drive_loop(context, self_model, memory):
    try:
        # === 1. Affective threat check — the reflex is a spike-WEIGHTED proposal,
        # not a hard binary flip at the threshold (V3_AUDIT D7). It competes against
        # the drive's symbolic baseline pick through the ActionArbiter, with
        # hysteresis against the last choice: an acute spike still dominates, a
        # moderate spike blends, and a boundary crossing no longer flip-flops the
        # whole loop. Mirrors the live select_function threat lane.
        context, threat_detector_response = process_affective_signals(context)
        if threat_detector_response.get("threat_detected"):
            shortcut = threat_detector_response.get("shortcut_function", "self_soothing")
            tags = threat_detector_response.get("threat_tags", [])
            spike = float(threat_detector_response.get("spike_intensity", 0.0) or 0.0)
            available_functions = context.get("available_functions", {}) or {}
            chosen = shortcut
            try:
                from brain.think.action_arbiter import ActionProposal, resolve as _resolve
                baseline = _symbolic_drive_choice(context, available_functions)
                recent = [c.get("choice", "") for c in (context.get("cognition_log") or [])[-3:]
                          if isinstance(c, dict)]
                props = [
                    ActionProposal(name=baseline, vote=0.55, weight=1.0, source="drive"),
                    ActionProposal(name=shortcut, vote=min(1.0, spike), weight=1.2,
                                   urgency=min(1.0, spike), source="threat_detector"),
                ]
                _winner, _info = _resolve(props, incumbent=(recent[-1] if recent else None),
                                          margin=0.10)
                if _winner:
                    chosen = _winner
            except Exception as _e:
                log_error(f"[drive] threat arbiter failed, using reflex shortcut: {_e}")
            update_working_memory({
                "content": f"⚠️ threat_detector reflex: {tags[0] if tags else 'unknown'} threat "
                           f"(spike {spike:.2f}) → {chosen}.",
                "event_type": "threat_detector_override",
                "intensity": spike,
                "priority": 3,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return chosen

        # === 2. Stable → hand off to bandit (the right tool for function selection)
        stability = context.get("affect_state", {}).get("affect_stability", 1.0)
        if stability > 0.60:
            update_working_memory({
                "content": "✅ Affectively grounded — handing off to bandit.",
                "event_type": "security_check",
                "priority": 1,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return "choose_next_cognition"

        # === 3. Dysregulated → symbolic affect-driven choice, no LLM
        # The LLM is a tool for cognitive functions to USE, not for deciding which one runs.
        available_functions = context.get("available_functions", {}) or {}
        choice = _symbolic_drive_choice(context, available_functions)
        log_private(f"[drive] Dysregulated (stability={stability:.2f}), symbolic choice: {choice}")
        update_working_memory({
            "content": f"🧭 Demand: affective instability ({stability:.2f}), routing to {choice}.",
            "event_type": "drive_choice",
            "priority": 2,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        return choice

    except Exception as e:
        log_error(f"persistent_drive_loop ERROR: {e}")
        update_working_memory({
            "content": "⚠️ Persistent drive loop failed.",
            "event_type": "error",
            "priority": 3,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        return "introspective_planning"
