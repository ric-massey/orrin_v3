from brain.utils.json_utils import load_json, extract_json, save_json
from brain.utils.log import log_model_issue
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.utils.self_model import get_self_model
from brain.cog_memory.working_memory import update_working_memory
from brain.affect.reflect_on_affect_model import reflect_on_emotion_model
from brain.affect.reward_signals.reward_signals import release_reward_signal
from brain.paths import WORKING_MEMORY_FILE, AFFECT_MODEL_FILE, CUSTOM_EMOTION, LONG_MEMORY_FILE

def discover_new_emotion(context=None):
    try:
        # === Load memory ===
        wm = load_json(WORKING_MEMORY_FILE, default_type=list)
        memories = wm[-10:] if isinstance(wm, list) else []
        memory_text = "\n".join(m.get("content", "") for m in memories if isinstance(m, dict) and m.get("content"))
        if not memory_text.strip():
            return

        # === Load known emotions ===
        emotion_model = load_json(AFFECT_MODEL_FILE, default_type=dict)
        if not isinstance(emotion_model, dict):
            emotion_model = {}
        custom_emotions = load_json(CUSTOM_EMOTION, default_type=list)
        if not isinstance(custom_emotions, list):
            custom_emotions = []

        known_emotions = set()
        known_emotions.update(str(k).lower().strip() for k in emotion_model.keys())
        for e in custom_emotions:
            if isinstance(e, dict):
                nm = str(e.get("name", "")).lower().strip()
                if nm:
                    known_emotions.add(nm)

        # === Prompt ===
        # Cap the visible known list so the prompt doesn’t explode
        known_list = ", ".join(sorted(list(known_emotions))[:80]) or "none"
        prompt = (
            "You are Orrin, reflecting on recent experiences and thoughts.\n"
            "Recent memory snippets:\n"
            f"{memory_text}\n\n"
            "Is there a felt emotion that does NOT fit any of the following known emotions?\n"
            f"Known emotions: {known_list}\n\n"
            "If YES, respond in JSON with a single *real* English word name (no spaces), "
            "a brief description, and an example thought:\n"
            '{ "name": "", "description": "", "example_thought": "" }\n'
            'If NO, respond ONLY with: { "name": "NO_NEW_EMOTION" }'
        )

        response = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "discovery")
        if not response:
            return

        # === Parse and validate ===
        data = extract_json(response)
        if not isinstance(data, dict) or "name" not in data:
            return

        name = str(data.get("name", "")).strip()
        desc = str(data.get("description", "")).strip()
        example = str(data.get("example_thought", "")).strip()

        if name.upper() == "NO_NEW_EMOTION":
            update_working_memory({
                "content": "No new emotion discovered — all feelings fit current vocabulary.",
                "event_type": "affect_discovery",
                "importance": 1,
                "priority": 1,
                "emotion": "neutral"
            })
            if context:
                es = context.get("affect_state", {}) or {}
                resource_deficit = float(es.get("resource_deficit", 0.0) or 0.0)
                motivation = float(es.get("motivation", 0.5) or 0.5)
                effort_mod = 0.2 * (1 - resource_deficit) * (0.5 + motivation)
                release_reward_signal(context, signal_type="reward_signal",
                                      actual_reward=0.3, expected_reward=0.5,
                                      effort=effort_mod, mode="phasic")
            return

        lower_name = name.lower()
        # Basic validity checks
        if (
            lower_name in known_emotions or
            not name.isalpha() or         # letters only; avoids hyphens/spaces/gibberish
            len(name) < 3 or
            " " in name
        ):
            update_working_memory({
                "content": f"⚠️ LLM proposed invalid or duplicate emotion: '{name}' — ignored.",
                "event_type": "affect_discovery",
                "importance": 2,
                "priority": 2,
                "emotion": "neutral"
            })
            return

        # === Save new emotion ===
        update_working_memory({
            "content": f"Orrin discovered a new emotion: {name} — {desc}. Example: '{example}'",
            "event_type": "affect_discovery",
            "importance": 2,
            "priority": 2,
            "emotion": name
        })

        # Dedup before appending to custom emotions
        if not any(isinstance(e, dict) and str(e.get("name", "")).lower() == lower_name for e in custom_emotions):
            custom_emotions.append({"name": name, "description": desc, "example_thought": example})
            save_json(CUSTOM_EMOTION, custom_emotions)

        # Build detection keywords from description + example
        raw_words = (desc + " " + example).lower().split()
        # strip punctuation and keep length >= 4
        cleaned = []
        for w in raw_words:
            w = w.strip(".,!?;:\"'()[]{}")
            if len(w) >= 4:
                cleaned.append(w)
        keywords = sorted(set(cleaned))

        # Update emotion model entry
        emotion_model[name] = keywords
        save_json(AFFECT_MODEL_FILE, emotion_model)

        # --- Reward for novelty ---
        if context:
            es = context.get("affect_state", {}) or {}
            resource_deficit = float(es.get("resource_deficit", 0.0) or 0.0)
            motivation = float(es.get("motivation", 0.5) or 0.5)
            novelty_effort = 0.6 * (1 - resource_deficit) * (0.5 + motivation)
            reward_signal_effort = 0.7 * (1 - resource_deficit) * (0.5 + motivation)
            release_reward_signal(context, signal_type="novelty", actual_reward=0.9, expected_reward=0.5, effort=novelty_effort)
            release_reward_signal(context, signal_type="reward_signal", actual_reward=0.8, expected_reward=0.5, effort=reward_signal_effort)

        # --- Reflect on vocabulary model ---
        self_model = get_self_model()
        lm = load_json(LONG_MEMORY_FILE, default_type=list)
        memory = lm[-20:] if isinstance(lm, list) else []
        reflect_on_emotion_model(context, self_model, memory)

    except Exception as e:
        if context:
            es = context.get("affect_state", {}) or {}
            resource_deficit = float(es.get("resource_deficit", 0.0) or 0.0)
            motivation = float(es.get("motivation", 0.5) or 0.5)
            effort_mod = 0.4 * (1 - resource_deficit) * (0.5 + motivation)
            release_reward_signal(context, signal_type="reward_signal",
                                  actual_reward=0.2, expected_reward=0.5,
                                  effort=effort_mod, mode="phasic")
        log_model_issue(f"❌ Failed to parse new emotion discovery: {e}\nRaw: {response if 'response' in locals() else 'No response'}")