from brain.core.runtime_log import get_logger
from datetime import datetime, timezone
from statistics import mean
from typing import Any
import random

from brain.utils.load_utils import load_all_known_json
from brain.utils.log import log_private
from brain.utils.log_reflection import log_reflection
from brain.utils.coerce_to_string import coerce_to_string
from brain.control_signals.discovery import discover_new_emotion
from brain.control_signals.reward_signals.reward_signals import release_reward_signal
from brain.control_signals.reflect_on_signal_model import reflect_on_emotion_model
from brain.control_signals.signals import investigate_unexplained_emotions, detect_signal
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

def reflect_on_affect(context: Any, self_model: Any, memory: Any) -> Any:
    from brain.cog_memory.working_memory import update_working_memory

    data = load_all_known_json()
    affect_state = data.get("affect_state", {}) or {}
    sensitivity = data.get("emotion_sensitivity", {}) or {}
    attachment = affect_state.get("attachment", {}) or {}
    core = affect_state.get("core_signals", {}) or {}
    triggers = affect_state.get("recent_triggers", [])[-10:] or []

    # type guards
    if not isinstance(core, dict): core = {}
    if not isinstance(sensitivity, dict): sensitivity = {}
    if not isinstance(attachment, dict): attachment = {}
    if not isinstance(triggers, list): triggers = []

    stability = float(affect_state.get("signal_stability", 0.5) or 0.5)
    resource_deficit = float(affect_state.get("resource_deficit", 0.0) or 0.0)
    motivation = float(affect_state.get("motivation", 0.5) or 0.5)
    excitement = float(affect_state.get("excitement", 0.0) or 0.0)

    # === Emotion Summary ===
    emotion_events = {}
    for trig in triggers:
        if not isinstance(trig, dict):  # guard malformed entries
            continue
        emo = trig.get("emotion")
        intensity = trig.get("intensity", 0)
        if emo and isinstance(intensity, (int, float)):
            emotion_events.setdefault(emo, []).append(abs(float(intensity)))

    emotion_summary = [
        f"- {emo} triggered {len(vals)}x (avg intensity: {round(mean(vals), 3)})"
        for emo, vals in emotion_events.items() if vals
    ]

    # strongest emotions — only include meaningfully elevated values (> 0.1)
    try:
        elevated = [(k, float(v)) for k, v in core.items() if isinstance(v, (int, float)) and float(v) > 0.1]
        strongest = sorted(elevated, key=lambda x: x[1], reverse=True)[:5]
    except Exception:
        strongest = []
    emotion_variability = [abs(v - 0.5) for _, v in strongest] if strongest else []

    # === Trigger emotion model expansion if emotion range is flat ===
    if strongest and all(val < 0.2 for val in emotion_variability):  # flat affect
        discover_new_emotion(context=context)  # pass context for rewards
        reflect_on_emotion_model(context, self_model, memory)

    # === Occasional reflection on emotion model (1%) ===
    if random.random() < 0.01:
        reflect_on_emotion_model(context, self_model, memory)

    # === Trigger introspection if strong emotion lacks known cause (70%) ===
    threshold = 0.4
    unexplained = {
        emo: val for emo, val in core.items()
        if isinstance(val, (int, float))
        and val >= threshold
        and not any(isinstance(t, dict) and t.get("emotion") == emo for t in triggers)
    }
    if unexplained and random.random() < 0.7:
        investigate_unexplained_emotions(context, self_model, memory)

    # === Build reflection context ===
    # Felt language for the LLM prompt — the introspection contract says raw
    # core_signals are "NEVER directly reported to the LLM" (felt_lexicon membrane).
    from brain.utils.felt_lexicon import felt_label as _felt
    top_emotions = ", ".join(dict.fromkeys(_felt(k) for k, _v in strongest)) if strongest else "none"

    context_for_llm = {
        **data,
        "emotions": core,
        "recent_triggers": triggers,
        "emotion_summary": emotion_summary,
        "strongest_emotions": strongest,
        "signal_stability": stability,
        "instructions": coerce_to_string(
            "I am currently experiencing these strong emotions: "
            f"{top_emotions}\n"
            "My recent emotional triggers:\n" + "\n".join(emotion_summary) + "\n\n"
            "Reflect honestly on my emotional state. Use all available knowledge:\n"
            "- What patterns are forming?\n"
            "- Am I feeling more reactive or stable?\n"
            "- Am I stuck in an emotion loop?\n"
            "- Do my emotions match my values and self-beliefs?\n"
            "- Is there decay or dysregulation pulling me away from balance?\n"
            "Be honest, not performative. Tell the emotional truth."
        )
    }

    # Symbolic-first gate: check if symbolic engine can surface emotional patterns
    response = None
    trigger_data = [{"emotion": e, "intensity": vals[-1] if vals else 0}
                    for e, vals in emotion_events.items()]
    try:
        from brain.symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
        _sym = _sfr("emotion", context=None, data=trigger_data)
        if _sym:
            response = _sym["text"]
            log_private(f"[symbolic] Emotion reflection ({_sym['source']}): {response[:80]}")
    except Exception as _e:
        record_failure("reflect_on_affect.reflect_on_affect", _e)

    if not response:
        try:
            from brain.symbolic.llm_gate import gated_generate
            prompt = context_for_llm.get("instructions", "")
            response = gated_generate(prompt, caller="reflect_on_affect", outcome=0.65)
            if response and isinstance(response, str):
                try:
                    from brain.symbolic.crystallization import crystallize as _cryst
                    prompt_summary = f"emotional reflection: {top_emotions}"
                    _cryst(prompt_summary, response, outcome=0.65, caller="reflect_on_affect")
                except Exception as _e:
                    record_failure("reflect_on_affect.reflect_on_affect.2", _e)
        except Exception as _e:
            record_failure("reflect_on_affect.reflect_on_affect.3", _e)

    now = datetime.now(timezone.utc).isoformat()

    if isinstance(response, str) and response.strip():
        text = response.strip()
        det = detect_signal(text) or {"emotion": "neutral", "intensity": 0.0}
        wm_emotion_name = det["emotion"] if isinstance(det, dict) else str(det)

        update_working_memory({
            "content": "emotional reflection: " + text,
            "event_type": "affective_reflection",
            "emotion": wm_emotion_name,  # store just the name
            "timestamp": now,
            "importance": 2,
            "priority": 2,
            "referenced": 1,
            "recall_count": 0,
            "related_memory_id": None,
            "decay": 1.0,
            "tags": ["reflection", "emotion"]
        })
        log_private(f"[emotional reflection - {now}]\n{text}")
        log_reflection(f"Self-belief reflection: {text}")

        # --- Calculate reward parameters dynamically ---
        base_actual_reward = 0.6 + min(0.4, 1.0 - stability)
        modulated_actual_reward = base_actual_reward * (1 - resource_deficit * 0.4) * (1 + 0.3 * (motivation + excitement))
        modulated_actual_reward = max(0.0, min(modulated_actual_reward, 1.0))

        base_effort = 0.5 + (0.5 if (strongest and all(val < 0.2 for val in emotion_variability)) else 0.0)
        modulated_effort = base_effort * (1 - resource_deficit * 0.5) * (1 + 0.2 * motivation)
        modulated_effort = max(0.1, min(modulated_effort, 1.0))

        release_reward_signal(
            context=context,
            signal_type="reward_signal",
            actual_reward=modulated_actual_reward,
            expected_reward=0.7,
            effort=modulated_effort,
            mode="phasic"
        )
    else:
        update_working_memory({
            "content": "⚠️ Emotional reflection failed or returned nothing.",
            "event_type": "affective_reflection",
            "emotion": "neutral",
            "timestamp": now,
            "importance": 2,
            "priority": 1,
            "referenced": 0,
            "recall_count": 0,
            "related_memory_id": None,
            "decay": 1.0,
            "tags": ["reflection", "emotion", "error"]
        })
        release_reward_signal(
            context=context,
            signal_type="reward_signal",
            actual_reward=0.1,
            expected_reward=0.7,
            effort=0.6,
            mode="phasic"
        )