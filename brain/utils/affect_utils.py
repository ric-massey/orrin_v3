# utils/affect_utils.py
# Pure, dependency-light affect helpers (Layer L1).
#
# This module imports ONLY from utils/ and paths/ (plus stdlib). It must never
# import from affect/ or any higher layer — that is precisely what lets the
# storage layer (cog_memory/) tag entries with an emotion label without creating
# the affect ↔ cog_memory import cycle.
#
# The keyword-detection logic here was extracted verbatim from the keyword path
# of affect.affect.detect_affect, which now delegates to it (single source of
# truth — no duplication).
import re

from utils.json_utils import load_json
from brain.paths import AFFECT_MODEL_FILE, CUSTOM_EMOTION


def detect_affect_keyword(text) -> dict:
    """Keyword-only emotion detection (no LLM, no side effects).

    Scores ``text`` against the keyword lists in AFFECT_MODEL_FILE and
    CUSTOM_EMOTION and returns ``{"emotion": <str>, "intensity": <float>}``,
    or ``{"emotion": "neutral", "intensity": 0.0}`` when nothing matches.
    """
    text = (text or "").strip()
    if not isinstance(text, str) or not text:
        return {"emotion": "neutral", "intensity": 0.0}
    text_lc = text.lower()

    # Load models defensively
    emotion_model = load_json(AFFECT_MODEL_FILE, default_type=dict)
    if not isinstance(emotion_model, dict):
        emotion_model = {}

    custom_emotions = load_json(CUSTOM_EMOTION, default_type=list)
    if not isinstance(custom_emotions, list):
        custom_emotions = []

    # Build dynamic keyword map (dedupe, keep words >= 3 chars)
    emotion_keywords = {}
    for k, v in emotion_model.items():
        if not isinstance(k, str):
            continue
        kws = [str(w).lower().strip() for w in (v or []) if isinstance(w, (str, int, float))]
        kws = [w for w in kws if len(w) >= 3]
        if kws:
            emotion_keywords[k] = list(dict.fromkeys(kws))  # dedupe

    for emo in custom_emotions:
        if not isinstance(emo, dict):
            continue
        name = emo.get("name")
        desc = emo.get("description", "")
        if isinstance(name, str) and name.strip():
            words = re.findall(r'\b\w+\b', str(desc).lower())
            words = [w for w in words if len(w) >= 3]
            if words:
                emotion_keywords.setdefault(name, []).extend(words)

    # Keyword-based detection
    scores = {}
    for emotion, keywords in emotion_keywords.items():
        if not keywords:
            continue
        count = sum(1 for word in keywords if word in text_lc)
        scores[emotion] = count / max(len(keywords), 1)

    if scores:
        top_emotion = max(scores, key=scores.get)
        intensity = min(scores.get(top_emotion, 0.0), 1.0)
        if intensity > 0.0:
            return {
                "emotion": str(top_emotion).lower(),
                "intensity": round(float(intensity), 2),
            }

    return {"emotion": "neutral", "intensity": 0.0}
