# brain/affect/model.py
#
# Affect model loader — maps affect labels to keyword lists for detection.
#
# SCIENTIFIC BASIS:
#   Russell (1980) — "A circumplex model of affect." Journal of Personality
#   and Social Psychology, 39(6), 1161–1178.
#   Russell & Barrett (2000) — "Core affect, prototypical emotional episodes,
#   and other things called emotion." Psychological Review, 106(3), 631–657.
#   The keyword lists operationalize discrete affect categories as textual
#   surface forms of underlying core affect (valence × activation_level) states.

from typing import Dict, List, Any
from utils.json_utils import load_json, save_json
from utils.log import log_error, log_activity
from brain.paths import AFFECT_MODEL_FILE

# Packaged default keyword lists, one per core-affect category used in
# affect_state.json core_signals. These are the seed model: if the on-disk
# affect_model.json is missing or empty, boot reseeds it from here so keyword
# detection never silently degrades to all-neutral.
DEFAULT_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "positive_valence": [
        "happy", "glad", "great", "joy", "joyful", "love", "wonderful",
        "excited", "exciting", "awesome", "delighted", "pleased", "fantastic",
        "enjoy", "grateful", "thankful", "proud", "cheerful",
    ],
    "negative_valence": [
        "frustrated", "frustrating", "frustration", "angry", "anger",
        "annoyed", "annoying", "upset", "terrible", "awful", "hate", "mad",
        "irritated", "furious", "miserable", "unhappy", "disappointed",
        "disgusted",
    ],
    "melancholy": [
        "sad", "sadness", "lonely", "gloomy", "grief", "grieving",
        "heartbroken", "somber", "wistful", "melancholy", "depressed",
        "tearful", "mourning", "hopeless",
    ],
    "jealousy": [
        "jealous", "jealousy", "envy", "envious", "resentful", "resentment",
        "covet",
    ],
    "surprise": [
        "surprised", "surprising", "surprise", "unexpected", "astonished",
        "astonishing", "shocked", "shocking", "startled", "amazed", "amazing",
        "whoa", "wow",
    ],
    "wonder": [
        "wonder", "wondering", "curious", "curiosity", "fascinated",
        "fascinating", "intrigued", "intriguing", "marvel", "awe",
        "mystery", "mysterious",
    ],
    "contentment": [
        "content", "calm", "peaceful", "relaxed", "relaxing", "serene",
        "satisfied", "satisfying", "comfortable", "cozy", "ease", "soothing",
    ],
    "compassion": [
        "sorry", "sympathy", "sympathetic", "empathy", "empathetic", "caring",
        "comfort", "comforting", "kind", "kindness", "gentle", "support",
        "supportive", "console",
    ],
    "uncertainty": [
        "unsure", "uncertain", "uncertainty", "confused", "confusing",
        "doubt", "doubtful", "unclear", "puzzled", "puzzling", "ambiguous",
        "hesitant", "unsettled",
    ],
    "confidence": [
        "confident", "confidence", "certain", "certainty", "definitely",
        "absolutely", "convinced", "assured", "sure",
    ],
    "threat_level": [
        "danger", "dangerous", "threat", "threatening", "scared", "afraid",
        "fear", "fearful", "terrified", "terrifying", "anxious", "anxiety",
        "worried", "worry", "alarmed", "unsafe", "panic",
    ],
    "impasse_signal": [
        "stuck", "blocked", "impasse", "dead end", "going nowhere",
        "no progress", "hopelessly stuck", "spinning my wheels",
    ],
    "stagnation_signal": [
        "bored", "boring", "boredom", "stagnant", "stagnation", "monotonous",
        "tedious", "dull", "rut", "restless",
    ],
    "conflict_signal": [
        "conflict", "argument", "arguing", "fight", "fighting", "disagree",
        "disagreement", "clash", "quarrel", "feud",
    ],
    "rejection_signal": [
        "rejected", "rejection", "dismissed", "unwanted", "excluded",
        "shunned", "abandoned", "ignored",
    ],
    "social_deficit": [
        "lonely", "loneliness", "isolated", "isolation", "alone", "miss you",
        "missing you", "left out", "disconnected",
    ],
    "motivation": [
        "motivated", "motivation", "eager", "determined", "driven",
        "ambitious", "energized", "keen", "inspired", "inspiring",
    ],
    "exploration_drive": [
        "explore", "exploring", "discover", "discovery", "adventure",
        "adventurous", "investigate", "experiment", "novelty",
    ],
}


def seed_default_emotion_keywords(force: bool = False) -> bool:
    """Seed AFFECT_MODEL_FILE from DEFAULT_EMOTION_KEYWORDS when it is missing
    or empty (or unconditionally with force=True). Returns True if it wrote.

    Called once at boot — logs once there instead of warning per-utterance.
    """
    try:
        current = load_json(AFFECT_MODEL_FILE, default_type=dict)
        if force or not isinstance(current, dict) or not current:
            save_json(AFFECT_MODEL_FILE, DEFAULT_EMOTION_KEYWORDS)
            log_activity(
                "[boot] affect_model.json was empty — seeded from packaged "
                f"DEFAULT_EMOTION_KEYWORDS ({len(DEFAULT_EMOTION_KEYWORDS)} categories)."
            )
            return True
    except Exception as e:
        log_error(f"⚠️ Failed to seed default emotion keywords: {e}")
    return False


def load_emotion_keywords() -> Dict[str, List[str]]:
    """Load emotion->keywords map, normalized to {str: [str, ...]}."""
    try:
        raw: Any = load_json(AFFECT_MODEL_FILE, default_type=dict)
        if not isinstance(raw, dict):
            log_error("⚠️ Emotion model was not a dictionary. Returning empty model.")
            return {}

        normalized: Dict[str, List[str]] = {}
        for k, v in raw.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, list):
                # keep only strings, strip whitespace
                keywords = [str(x).strip() for x in v if isinstance(x, str) and x.strip()]
            elif isinstance(v, str):
                keywords = [v.strip()] if v.strip() else []
            else:
                keywords = []
            if keywords:
                normalized[k] = keywords
        if not normalized:
            # Empty on-disk model: fall back to the packaged defaults so
            # detection keeps working (boot reseeds the file separately).
            return {k: list(v) for k, v in DEFAULT_EMOTION_KEYWORDS.items()}
        return dict(normalized)  # shallow copy
    except Exception as e:
        log_error(f"⚠️ Failed to load emotion model: {e}")
        return {k: list(v) for k, v in DEFAULT_EMOTION_KEYWORDS.items()}