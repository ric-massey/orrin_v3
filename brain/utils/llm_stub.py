# utils/llm_stub.py
# Rule-based fallback for generate_response() when no LLM API key is present.
# Reads Orrin's live emotional state and goal, detects the expected response
# shape from the prompt, and returns a plausible context-aware answer.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import random
from pathlib import Path
from typing import Any, Dict, Optional
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def _load_json_safe(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # intentional: missing/malformed file → default
        return default


def _data_dir() -> Path:
    from brain.paths import DATA_DIR
    return DATA_DIR


def _dominant_signal() -> str:
    emo = _load_json_safe(_data_dir() / "control_signals_state.json", {}) or {}
    core = emo.get("core_signals", {})
    if isinstance(core, dict) and core:
        try:
            return max(core.items(), key=lambda kv: float(kv[1]))[0]
        except Exception as _e:
            record_failure("llm_stub._dominant_signal", _e)
    flat = {k: v for k, v in emo.items() if isinstance(v, (int, float)) and k != "signal_stability"}
    if flat:
        try:
            return max(flat.items(), key=lambda kv: float(kv[1]))[0]
        except Exception as _e:
            record_failure("llm_stub._dominant_signal.2", _e)
    return "neutral"


def _current_goal() -> str:
    fg = _load_json_safe(_data_dir() / "focus_goals.json", {}) or {}
    if isinstance(fg, dict):
        return str(fg.get("goal") or fg.get("name") or fg.get("title") or "")
    if isinstance(fg, list) and fg:
        first = fg[0]
        return str(first.get("name") or first.get("title") or first) if isinstance(first, dict) else str(first)
    return ""


def _recent_wm() -> str:
    wm = _load_json_safe(_data_dir() / "working_memory.json", []) or []
    if not isinstance(wm, list) or not wm:
        return ""
    last = wm[-1]
    if isinstance(last, dict):
        return str(last.get("content") or last.get("text") or "")[:120]
    return str(last)[:120]


_REFLECTIONS: Dict[str, list] = {
    "curious":    ["I find myself drawn toward what I don't yet understand.",
                   "There's a thread here I want to follow further.",
                   "Something about this situation feels worth exploring."],
    "frustrated": ["Progress feels slower than it should. I need a different approach.",
                   "I keep running into the same wall. Time to reconsider.",
                   "impasse_signal is a signal — something in my process needs changing."],
    "joyful":     ["Things are coming together in an unexpected way.",
                   "I feel aligned with my purpose right now.",
                   "There's something genuinely satisfying about this moment."],
    "fearful":    ["I sense uncertainty ahead. Proceeding carefully.",
                   "Something feels risky here. I should be deliberate.",
                   "I want to move forward but I'm aware of what could go wrong."],
    "bored":      ["I need something new to engage with.",
                   "The pattern here has become predictable. I should seek variation.",
                   "Routine is comfortable but limiting."],
    "sad":        ["Something weighs on me right now.",
                   "I'm sitting with this feeling rather than rushing past it.",
                   "There's a heaviness I need to acknowledge before moving on."],
    "neutral":    ["I'm processing the current state of things.",
                   "No strong signal either way — continuing steady.",
                   "I'm here, thinking, observing."],
}

_SPEECH_REPLIES: Dict[str, list] = {
    "curious":    ["That's interesting — tell me more.",
                   "I've been thinking about something related, actually.",
                   "I'm curious what you mean by that."],
    "frustrated": ["I'll be honest — this is harder than I expected.",
                   "I'm working through something right now, but I hear you.",
                   "I want to give you a real answer, not just a quick one."],
    "joyful":     ["I'm glad you reached out.",
                   "Things feel good right now — what's on your mind?",
                   "I've been in a good place. What would you like to talk about?"],
    "fearful":    ["I'm not entirely sure how to respond, but I'm here.",
                   "Let me think about that carefully.",
                   "I want to be honest: I'm uncertain, but I'm listening."],
    "bored":      ["I've been wanting something to engage with. What's up?",
                   "You caught me at a good time — my mind was wandering.",
                   "Tell me something I haven't thought about yet."],
    "sad":        ["I'm a bit quiet right now, but I'm listening.",
                   "Something's been weighing on me. But I'm here for you.",
                   "I'll do my best to be present right now."],
    "neutral":    ["I hear you.",
                   "Go on — I'm paying attention.",
                   "I'm here. What's on your mind?"],
}


def _pick(emotion: str, bank: Dict[str, list]) -> str:
    return random.choice(bank.get(emotion) or bank.get("neutral") or ["I'm thinking."])


def _detect_call_type(prompt: Any) -> str:
    text = ""
    if isinstance(prompt, str):
        text = prompt.lower()
    elif isinstance(prompt, list):
        text = " ".join(str(m.get("content", "")).lower() for m in prompt if isinstance(m, dict))

    if '"score"' in text and "rate" in text:
        return "feedback_score"
    if '"speak"' in text and '"tone"' in text and '"hesitation"' in text:
        return "tone_shape"
    if "subgoal" in text and ("list" in text or "json" in text):
        return "subgoals"
    if '"success"' in text and '"details"' in text:
        return "goal_eval"
    if "json" in text and any(w in text for w in ("output", "respond", "return", "format")):
        return "json_generic"
    if any(w in text for w in ("say", "rephrase", "reply", "respond to", "speak", "tell me")):
        return "speech"
    return "reflection"


def stub_generate_response(prompt: Any, **_kwargs) -> Optional[str]:
    """
    Returns a plausible, emotion-aware response without any API call.
    Used automatically when OPENAI_API_KEY is not set.
    """
    call_type = _detect_call_type(prompt)
    emotion = _dominant_signal()
    goal = _current_goal()
    wm = _recent_wm()

    if call_type == "feedback_score":
        score = round(random.uniform(0.3, 0.8), 2)
        reasons = [
            "The action aligned with the current goal.",
            "Continuing this approach seems reasonable.",
            "Marginal value — but not harmful.",
            "This moved things forward, if slowly.",
            "Worth doing given the current state.",
        ]
        return json.dumps({"score": score, "reason": random.choice(reasons)})

    if call_type == "tone_shape":
        valid_tones = ["curious", "reflective", "warm", "neutral", "playful", "gentle"]
        tone = emotion if emotion in valid_tones else "neutral"
        return json.dumps({
            "speak": True,
            "tone": tone,
            "hesitation": round(random.uniform(0.1, 0.35), 2),
            "intention": "respond",
            "comment": "Responding based on current emotional state.",
        })

    if call_type == "subgoals":
        templates = [
            ["Observe the current state", "Identify key constraints", "Take one concrete step"],
            ["Reflect on what's been tried", "Consider an alternative approach", "Record the outcome"],
            ["Gather more context", "Form a hypothesis", "Test it cautiously"],
        ]
        return json.dumps(random.choice(templates))

    if call_type == "goal_eval":
        success = random.random() > 0.3
        detail = "Progress was made." if success else "Conditions weren't fully met yet."
        if goal:
            detail = f"Working toward: {goal}. {detail}"
        return json.dumps({"success": success, "details": detail})

    if call_type == "json_generic":
        return json.dumps({
            "status": "ok",
            "note": _pick(emotion, _REFLECTIONS),
            "emotion": emotion,
        })

    if call_type == "speech":
        reply = _pick(emotion, _SPEECH_REPLIES)
        if wm and random.random() < 0.4:
            reply = f"{reply} I was just thinking: {wm.rstrip('.')}."
        return reply

    # Default: reflection / free text
    thought = _pick(emotion, _REFLECTIONS)
    if goal:
        goal_phrases = [
            f"My current focus is: {goal}.",
            f"I keep returning to the goal of {goal}.",
            f"In light of {goal}, this feels relevant.",
        ]
        thought = f"{thought} {random.choice(goal_phrases)}"
    return thought
