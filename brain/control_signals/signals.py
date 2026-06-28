from datetime import datetime, timezone
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.utils.json_utils import load_json, save_json, extract_json
from brain.utils.log import log_error
from brain.utils.coerce_to_string import coerce_to_string
from brain.utils.signal_lexicon_utils import detect_signal_keyword

from brain.paths import (
    SIGNAL_STATE_FILE,
    LONG_MEMORY_FILE,
    MODEL_CONFIG_FILE,
    AFFECT_MODEL_FILE,
)


def _llm_available() -> bool:
    """True when an LLM is enabled and reachable; mirrors the guard used at the
    other symbolic-first call sites (cf. self_model_conflicts._llm_ready)."""
    try:
        from brain.utils.llm_gate import llm_available
        return bool(llm_available())
    except ImportError:  # intentional: llm_gate optional → treat LLM as unavailable
        return False


def investigate_unexplained_emotions(context, self_model, memory):
    from brain.cog_memory.working_memory import update_working_memory
    from brain.control_signals.reward_signals.reward_signals import release_reward_signal

    affect_state = load_json(SIGNAL_STATE_FILE, default_type=dict)
    if not isinstance(affect_state, dict):
        affect_state = {}

    long_memory = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(long_memory, list):
        long_memory = []

    config = load_json(MODEL_CONFIG_FILE, default_type=dict)
    if not isinstance(config, dict):
        config = {}

    threshold = float(config.get("emotion_analysis_threshold", 0.4))

    core_signals = affect_state.get("core_signals", {})
    if not isinstance(core_signals, dict):
        core_signals = {}

    recent_triggers = affect_state.get("recent_triggers", [])
    if not isinstance(recent_triggers, list):
        recent_triggers = []
    recent_triggers = recent_triggers[-10:]

    # Emotions explained by a recent causal attribution are not "unexplained"
    recent_causes = affect_state.get("recent_emotion_causes", [])
    if not isinstance(recent_causes, list):
        recent_causes = []
    explained_by_cause = {
        c["emotion"]
        for c in recent_causes
        if isinstance(c, dict) and c.get("emotion")
    }

    unexplained = {
        emotion: value
        for emotion, value in core_signals.items()
        if isinstance(value, (int, float))
        and value >= threshold
        and emotion not in explained_by_cause
        and not any(
            isinstance(trigger, dict) and trigger.get("emotion") == emotion
            for trigger in recent_triggers
        )
    }

    now = datetime.now(timezone.utc).isoformat()

    if not unexplained:
        update_working_memory({
            "content": "All current strong emotions are accounted for.",
            "event_type": "affect_analysis",
            "emotion": "neutral",
            "timestamp": now,
            "importance": 1,
            "priority": 1,
            "referenced": 0,
            "recall_count": 0,
            "related_memory_id": None,
            "decay": 1.0,
            "tags": ["emotion", "reflection"],
        })
        release_reward_signal(
            context=context,
            signal_type="reward_signal",
            actual_reward=0.2,
            expected_reward=0.3,
            effort=0.2,
            mode="tonic",
        )
        return

    past_reflections = [
        entry.get("content", "")
        for entry in long_memory[-20:]
        if isinstance(entry, dict) and entry.get("content")
    ]
    context_block = "\n".join(f"- {item}" for item in past_reflections)
    emotional_summary = "\n".join(f"{k}: {v}" for k, v in unexplained.items())

    prompt = (
        "I am Orrin, reflecting on unexplained emotional intensities.\n"
        f"Unexplained emotions:\n{emotional_summary}\n\n"
        "Here are recent memories and reflections:\n"
        f"{context_block}\n\n"
        "Try to hypothesize what could be causing these emotional patterns. "
        "If I cannot explain them, say so."
    )

    reflection = llm_ok(generate_response(coerce_to_string(prompt)), "emotion")

    if reflection:
        update_working_memory({
            "content": "Unexplained emotion reflection:\n" + reflection,
            "event_type": "unexplained_affect_reflection",
            "emotion": "uncertain",
            "timestamp": now,
            "importance": 2,
            "priority": 2,
            "referenced": 1,
            "recall_count": 0,
            "related_memory_id": None,
            "decay": 1.0,
            "tags": ["emotion", "reflection", "unexplained"],
        })

        # Append the reflection's trigger metadata onto the LIVE in-context
        # affect_state when present, so update_signal_state (the sole writer)
        # persists it — no direct affect-file write, no race. Fall back to a
        # direct write only for genuinely context-less callers.
        _ctx_state = context.get("affect_state") if isinstance(context, dict) else None
        _target_state = _ctx_state if isinstance(_ctx_state, dict) else affect_state
        for emo in unexplained:
            _target_state.setdefault("recent_triggers", []).append({
                "event": "unexplained emotion reflection",
                "emotion": emo,
                "intensity": core_signals.get(emo, 0.0),
                "timestamp": now,
            })

        if not isinstance(_ctx_state, dict):
            save_json(SIGNAL_STATE_FILE, affect_state)

        # Modulate reward by resource_deficit and motivation for consistency
        resource_deficit = float(affect_state.get("resource_deficit", 0.0))
        motivation = float(affect_state.get("motivation", 0.5))

        base_actual_reward = 0.75
        modulated_actual_reward = base_actual_reward * (1 - resource_deficit * 0.4) * (1 + 0.3 * motivation)
        modulated_actual_reward = max(0.0, min(modulated_actual_reward, 1.0))

        release_reward_signal(
            context=context,
            signal_type="reward_signal",
            actual_reward=modulated_actual_reward,
            expected_reward=0.5,
            effort=0.6,
            mode="phasic",
        )
    else:
        update_working_memory({
            "content": "⚠️ Failed to generate a reflection on unexplained emotions.",
            "event_type": "unexplained_affect_reflection",
            "emotion": "neutral",
            "timestamp": now,
            "importance": 1,
            "priority": 1,
            "referenced": 0,
            "recall_count": 0,
            "related_memory_id": None,
            "decay": 1.0,
            "tags": ["emotion", "reflection", "unexplained", "error"],
        })
        release_reward_signal(
            context=context,
            signal_type="reward_signal",
            actual_reward=0.1,
            expected_reward=0.4,
            effort=0.5,
            mode="phasic",
        )


def detect_signal(text, use_gpt=True):
    # Keyword path — pure logic shared with the storage layer via
    # utils.signal_lexicon_utils (single source of truth; no duplication).
    kw = detect_signal_keyword(text)
    if kw.get("intensity", 0.0) > 0.0:
        return kw

    # GPT fallback — only when an LLM is actually reachable. In symbolic-first
    # mode generate_response() returns symbolic narrative prose, not JSON, so
    # the extract_json path below can never succeed and would silently degrade
    # every unclassified text to "neutral" while spamming JSON-salvage failures.
    if use_gpt and _llm_available():
        prompt = (
            "Analyze the following message and infer the emotion and its strength.\n"
            f"Message: \"{text}\"\n\n"
            "Respond ONLY with a JSON object:\n"
            "{ \"emotion\": \"emotion_name\", \"intensity\": 0.0 to 1.0 }"
        )
        try:
            result = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "emotion")
            data = extract_json(result.strip()) if result and "{" in result else {}
            if isinstance(data, dict) and "emotion" in data:
                return {
                    "emotion": str(data.get("emotion", "neutral")).lower(),
                    "intensity": round(float(data.get("intensity", 0.5)), 2),
                }
        except Exception as e:
            log_error(f"❌ detect_signal GPT fallback failed: {e}")

    return {"emotion": "neutral", "intensity": 0.0}


def deliver_signal_based_rewards(context, core_signals, stability):
    from brain.control_signals.reward_signals.reward_signals import release_reward_signal

    if not core_signals or not isinstance(core_signals, dict):
        return

    numeric = {k: v for k, v in core_signals.items() if isinstance(v, (int, float))}
    if not numeric:
        return

    dominant = max(numeric, key=numeric.get)
    intensity = float(numeric[dominant])

    # Base effort and mode for rewards
    base_effort = 0.5
    phasic_mode = "phasic"
    tonic_mode = "tonic"

    if dominant == "reward_positive":
        release_reward_signal(
            context,
            "reward_signal",
            actual_reward=intensity,
            expected_reward=0.5,
            effort=base_effort,
            mode=phasic_mode,
        )
    elif dominant in ["threat_level", "reward_negative"]:
        release_reward_signal(
            context,
            "reward_signal",
            actual_reward=0.1,
            expected_reward=0.5,
            effort=base_effort,
            mode=tonic_mode,
        )
    elif float(stability) < 0.4:
        release_reward_signal(
            context,
            "stability_signal",  # supported signal
            actual_reward=1.0,
            expected_reward=0.0,
            effort=base_effort,
            mode=phasic_mode,
        )

    if 0.8 < intensity < 0.96:
        release_reward_signal(
            context,
            "novelty",
            actual_reward=intensity,
            expected_reward=0.3,
            effort=base_effort,
            mode=phasic_mode,
        )


def get_all_signal_names():
    """Load emotion names from emotion model JSON."""
    data = load_json(AFFECT_MODEL_FILE, default_type=dict)
    return list(data.keys()) if isinstance(data, dict) else []