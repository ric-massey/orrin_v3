"""
cognition/comprehension.py

Comprehension layer: parses what the user said into structured state events.

The LLM here is a parser, not a responder. It answers:
  - What emotion is this carrying?
  - What is this person trying to express?
  - What concept is at the center?

That structured result feeds Orrin's internal state directly — emotion updates,
working memory events, goal relevance signals. He doesn't understand words.
He feels what they do to him.
"""
from __future__ import annotations
from core.runtime_log import get_logger

from typing import Any, Dict

from utils.log import log_private
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)


_PARSE_PROMPT = """Parse this message. Return ONLY valid JSON, nothing else.

Message: {text}

Return exactly this structure:
{{
  "emotion_carried": "<dominant emotion or 'neutral'>",
  "intensity": <0.0 to 1.0>,
  "intent": "<question|statement|request|sharing|challenge|greeting|other>",
  "concept": "<core topic in 3-5 words>",
  "urgency": <0.0 to 1.0>
}}"""


def comprehend(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse user input into structured state events.
    Returns parsed signals. Side-effects: updates Orrin's state.
    """
    if not user_text or not user_text.strip():
        return {}

    parsed = _parse(user_text)
    _apply_to_state(parsed, user_text, context)
    log_private(f"[comprehension] {parsed}")
    return parsed


def _parse(user_text: str) -> Dict[str, Any]:
    if not llm_callable_by("comprehension"):
        return _fallback(user_text)
    try:
        from utils.llm_router import routed_response
        from utils.json_utils import extract_json
        raw = (routed_response(
            _PARSE_PROMPT.format(text=user_text[:500]),
            "comprehension/parse",
            complexity="simple",
        ) or "").strip()
        parsed = extract_json(raw)
        if isinstance(parsed, dict) and "emotion_carried" in parsed:
            return parsed
    except Exception as _e:
        record_failure("comprehension._parse", _e)
    return _fallback(user_text)


def _apply_to_state(parsed: Dict, user_text: str, context: Dict[str, Any]) -> None:
    """
    Feed parsed comprehension into Orrin's state.
    This is what "understanding" means — not language comprehension but state change.
    """
    emotion   = str(parsed.get("emotion_carried") or "neutral").lower()
    intensity = float(parsed.get("intensity") or 0.0)
    urgency   = float(parsed.get("urgency") or 0.3)
    concept   = str(parsed.get("concept") or user_text[:40])
    intent    = str(parsed.get("intent") or "statement")

    # Store for state_processor and expression layer
    context["_input_urgency"]      = urgency
    context["_input_intent"]       = intent
    context["_last_comprehension"] = {**parsed, "concept": concept}

    # Emotional contagion from parsed emotion (more precise than raw keyword detection)
    if emotion not in ("neutral", "unknown", "") and intensity > 0.05:
        try:
            from cognition.contagion import apply_emotional_contagion
            apply_emotional_contagion(user_text, context)
        except Exception as _e:
            record_failure("comprehension._apply_to_state", _e)

    # Integration lag: high-intensity input doesn't fully land immediately —
    # split the emotional delta into an immediate portion and a deferred portion
    # that arrives 5-8 cycles later. Below threshold: contagion handles it directly.
    if emotion not in ("neutral", "unknown", "") and intensity > 0.05:
        try:
            from affect.integration_lag import maybe_apply_integration_lag
            maybe_apply_integration_lag(
                emotion, intensity, user_text[:80], context
            )
        except Exception as _e:
            record_failure("comprehension._apply_to_state.2", _e)

    # Working memory event — what arrived, as a structured signal not English narration
    try:
        from cog_memory.working_memory import update_working_memory
        update_working_memory({
            "content":    f"[input/{intent}] {concept}",
            "event_type": "user_input",
            "emotion":    emotion,
            "importance": 2 + int(urgency > 0.6),
            "priority":   2,
        })
    except Exception as _e:
        record_failure("comprehension._apply_to_state.3", _e)

    # Goal relevance signal
    try:
        goal       = context.get("committed_goal") or {}
        goal_title = (goal.get("title") or "").lower()
        if concept and goal_title:
            c_words = set(concept.lower().split())
            g_words = {w for w in goal_title.split() if len(w) > 3}
            if c_words & g_words:
                context["_input_goal_relevant"] = True
    except Exception as _e:
        record_failure("comprehension._apply_to_state.4", _e)


def _fallback(user_text: str) -> Dict[str, Any]:
    """Rule-based fallback when LLM parse fails."""
    from affect.affect import detect_affect
    result    = detect_affect(user_text, use_gpt=False)
    emotion   = "neutral"
    intensity = 0.0
    if isinstance(result, dict):
        emotion   = result.get("emotion", "neutral")
        intensity = float(result.get("intensity") or 0.0)
    elif isinstance(result, str):
        emotion   = result
        intensity = 0.2 if emotion != "neutral" else 0.0

    t = user_text.lower().strip()
    if t.endswith("?"):
        intent = "question"
    elif any(w in t for w in ("please", "can you", "could you", "i need")):
        intent = "request"
    elif any(w in t for w in ("hi", "hello", "hey")):
        intent = "greeting"
    else:
        intent = "statement"

    return {
        "emotion_carried": emotion,
        "intensity":       intensity,
        "intent":          intent,
        "concept":         user_text[:40],
        "urgency":         0.3,
    }
