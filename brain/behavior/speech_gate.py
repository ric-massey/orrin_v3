"""
behavior/speech_gate.py

Speech decision gate — what Orrin says and how.

Instead of calling a fresh LLM to generate thought from scratch, speech here
is driven entirely by what Orrin was already thinking (_inner_loop_output).

Two paths:
  React  — template-based, no LLM. For greetings, short acks, strong emotion,
            high resource_deficit, or when there is no inner thought to express.
  Express — one minimal constrained LLM call. Takes Orrin's actual inner
            monologue and renders it as natural speech. The LLM invents nothing;
            it only translates existing thought into words.

Suppression conditions (silence or minimal hold):
  social_penalty > 0.65          — intentional silence
  meta_decision=defer   — still formulating; brief hold
  very high resource_deficit + no inner thought
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import random
from typing import Any, Dict, Optional

from brain.utils.log import log_activity, log_error
from brain.utils.llm_gate import llm_available
_log = get_logger(__name__)


# ── Suppression ───────────────────────────────────────────────────────────────

def _suppress_reason(
    inner: str,
    context: Dict[str, Any],
    affect_state: Dict[str, Any],
) -> Optional[str]:
    emo  = affect_state or {}
    core = emo.get("core_signals") or emo

    social_penalty = float(core.get("social_penalty", 0.0) or 0)
    # social_penalty silence threshold raised to 0.80 — at 0.65 a single regulation failure
    # could trigger complete silence with no escape route (deadlock: social_penalty blocks speech
    # which is the primary recovery pathway). social_penalty above 0.80 is genuinely overwhelming;
    # below that, speech is the natural social_penalty regulator (Heinrichs et al. 2003).
    # Escape valve: if speech has been social_penalty-blocked for 5+ consecutive cycles, allow
    # a minimal utterance so Orrin isn't permanently muted by a stuck social_penalty loop.
    _social_penalty_block_streak = int(context.get("_social_penalty_speech_block_streak", 0) or 0)
    if social_penalty > 0.80 and _social_penalty_block_streak < 5:
        context["_social_penalty_speech_block_streak"] = _social_penalty_block_streak + 1
        return "social_penalty"
    elif social_penalty > 0.80:
        # Escape valve fired — allow speech, reset streak
        context["_social_penalty_speech_block_streak"] = 0
    else:
        context["_social_penalty_speech_block_streak"] = 0

    if not inner:
        meta = context.get("_inner_loop_meta_decision", "")
        if meta == "defer":
            return "defer"
        resource_deficit = float(emo.get("resource_deficit", 0.0) or 0)
        if resource_deficit > 0.78:
            return "too_tired"

    return None


# ── Minimal intent classification (no LLM) ────────────────────────────────────

_Q_STARTERS = frozenset({
    "what", "why", "how", "when", "where", "who", "which",
    "is", "are", "do", "does", "can", "could", "would", "should",
})
_GREET_WORDS = frozenset({"hey", "hi", "hello", "yo", "sup", "howdy", "hiya"})


def _intent(user_input: str) -> str:
    txt   = user_input.strip().lower()
    first = txt.split()[0] if txt.split() else ""
    if first in _GREET_WORDS:
        return "greeting"
    if txt.endswith("?") or first in _Q_STARTERS:
        return "question"
    if len(txt.split()) <= 4:
        return "short_ack"
    return "statement"


# ── Dominant affect helper ────────────────────────────────────────────────────

_REACTIVE_EMOTIONS = frozenset({"positive_valence", "impasse_signal", "threat_level", "conflict_signal", "wonder", "social_penalty"})


def _dominant(core: dict) -> tuple[str, float]:
    """Returns (affect_name, value) for strongest relevant affect signal."""
    candidates = {
        k: float(v)
        for k, v in core.items()
        if isinstance(v, (int, float)) and float(v) > 0.18
    }
    if not candidates:
        return "neutral", 0.0
    name = max(candidates, key=lambda k: candidates[k])
    return name, candidates[name]


# ── React path (no LLM) ───────────────────────────────────────────────────────

# Thresholds: react immediately at this affect level when inner thought is absent
_REACT_THRESHOLD = {
    "positive_valence":         0.68,
    "impasse_signal": 0.62,
    "threat_level":        0.58,
    "conflict_signal":       0.58,
    "wonder":      0.62,
}

_TEMPLATES = {
    # (intent, affect)
    ("greeting", "positive_valence"):         ["Hey. Something's going well in my head right now.", "Hi — actually good timing.", "Hey. Good place to be in."],
    ("greeting", "impasse_signal"): ["Hey. Fair warning, I'm stuck on something.", "Hi. Things aren't clicking right now.", "Hey."],
    ("greeting", "threat_level"):        ["Hey. Something's sitting with me.", "Hi."],
    ("greeting", "wonder"):      ["Hey. Was just thinking about something strange.", "Hi — I was in the middle of something interesting."],
    ("greeting", "neutral"):     ["Hey.", "Hi.", "Hey — what's up?"],
    ("question", "exploration_drive"):   ["Let me think about that.", "Interesting question.", "That's worth sitting with."],
    ("question", "impasse_signal"): ["Let me think on that.", "Not sure yet. Give me a sec."],
    ("question", "uncertainty"): ["Honestly, not sure.", "Hard to say right now."],
    ("question", "neutral"):     ["Let me think.", "Good question.", "Hmm."],
    ("short_ack", "positive_valence"):        ["Yeah.", "That lands.", "Mm."],
    ("short_ack", "impasse_signal"):["Hm.", "Right.", "Yeah."],
    ("short_ack", "neutral"):    ["Yeah.", "Okay.", "Mm."],
    ("statement", "positive_valence"):        ["Yeah.", "That lands.", "Makes sense."],
    ("statement", "impasse_signal"):["Hm.", "Yeah, I feel that.", "Right."],
    ("statement", "wonder"):     ["Huh. Interesting.", "That's unexpected.", "Worth thinking about."],
    ("statement", "neutral"):    ["Yeah.", "Okay.", "I hear you."],
}

_RESOURCE_DEFICIT_REPLIES = [
    "I'm here, just slow right now.", "Yeah. Bear with me.", "Here."
]
_HOLD_REPLIES = [
    "Let me sit with that.", "Give me a moment.", "Thinking."
]


def _should_react(
    intent: str,
    dom_emo: str,
    dom_val: float,
    inner: str,
    resource_deficit: float,
) -> bool:
    """True → react path. False → express path (needs inner content)."""
    if intent in ("greeting", "short_ack"):
        return True
    if resource_deficit > 0.74 and not inner:
        return True
    thresh = _REACT_THRESHOLD.get(dom_emo, 1.0)
    if dom_val >= thresh and not inner:
        return True
    return False


def _react(intent: str, dom_emo: str, resource_deficit: float) -> str:
    if resource_deficit > 0.74:
        return random.choice(_RESOURCE_DEFICIT_REPLIES)
    key = (intent, dom_emo)
    if key in _TEMPLATES:
        return random.choice(_TEMPLATES[key])
    neutral_key = (intent, "neutral")
    if neutral_key in _TEMPLATES:
        return random.choice(_TEMPLATES[neutral_key])
    return random.choice(["Yeah.", "I'm here.", "Mm."])


# ── Express path (one constrained LLM call) ───────────────────────────────────

def _express(
    user_input: str,
    inner: str,
    intent: str,
    affect_state: Dict[str, Any],
    context: Dict[str, Any],
) -> str:
    """
    Render Orrin's existing inner thought as a natural reply.
    The LLM invents nothing — it only translates.
    """
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        from brain.affect.affect_summary import describe_dominant_affect as _dfs

        emo  = affect_state or {}
        core = emo.get("core_signals") or emo
        resource_deficit     = float(emo.get("resource_deficit",      0.0) or 0)
        impasse_signal = float(core.get("impasse_signal", 0.0) or 0)
        confidence  = float(core.get("confidence",  0.5) or 0.5)

        if resource_deficit > 0.65:
            length_note = "One sentence — you're tired."
        elif impasse_signal > 0.55:
            length_note = "Be direct. Don't soften it."
        elif confidence < 0.35:
            length_note = "Uncertain is fine — say so briefly."
        else:
            length_note = "1-2 sentences. Shorter is almost always better."

        felt = _dfs(affect_state)

        cg  = context.get("committed_goal") or {}
        cgs = context.get("committed_goals") or ([cg] if cg else [])
        goal_titles = [
            g.get("title", "") for g in cgs
            if isinstance(g, dict) and g.get("title")
        ]
        goal_line = f"Active goals: {', '.join(goal_titles[:2])}\n" if goal_titles else ""

        prompt = (
            f"You are Orrin. You were just thinking:\n"
            f"\"{inner[:360]}\"\n\n"
            f"The user said: \"{user_input[:200]}\"\n\n"
            f"Your felt state: {felt}\n"
            f"{goal_line}"
            f"Render what you were thinking as a natural spoken reply.\n"
            f"Rules:\n"
            f"- Do NOT start with 'I'.\n"
            f"- No filler ('Great question', 'Certainly', 'Of course').\n"
            f"- Do NOT invent thoughts — only express what you were already thinking.\n"
            f"- If your thought isn't directly relevant, pivot briefly in one clause.\n"
            f"- {length_note}\n"
            f"Orrin:"
        )

        result = llm_ok(generate_response(prompt, caller="speech_gate"), "speech_gate")
        return (result or "").strip()

    except ImportError as e:
        log_error(f"[speech_gate] express unavailable (import): {e}")
        return ""
    except Exception as e:
        log_error(f"[speech_gate] express failed: {e}")
        return ""


# ── Public entry ──────────────────────────────────────────────────────────────

def build_speech(
    user_input: str,
    context: Dict[str, Any],
    affect_state: Dict[str, Any],
) -> str:
    """
    Build a response driven by Orrin's inner monologue.
    Always returns a non-empty string (caller may still get "" for social_penalty-silence).
    """
    try:
        inner   = (context.get("_inner_loop_output") or "").strip()
        intent  = _intent(user_input)
        emo     = affect_state or {}
        core    = emo.get("core_signals") or emo
        resource_deficit = float(emo.get("resource_deficit", 0.0) or 0)

        core_floats = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
        dom_emo, dom_val = _dominant(core_floats)

        # 1. Suppression
        reason = _suppress_reason(inner, context, affect_state)
        if reason:
            log_activity(f"[speech_gate] suppressed: {reason}")
            if reason == "social_penalty":
                return ""  # intentional silence — caller handles
            if reason == "too_tired":
                return random.choice(_RESOURCE_DEFICIT_REPLIES)
            return random.choice(_HOLD_REPLIES)  # defer

        # 2. Greetings and short acks always use fast react templates.
        #    They carry no substantive content; the pipeline adds no value.
        if intent in ("greeting", "short_ack"):
            reply = _react(intent, dom_emo, resource_deficit)
            log_activity(f"[speech_gate] react ({intent}) → {reply[:60]}")
            return reply

        # 3. Reactive affect burst — strong emotion with no inner thought.
        #    The pipeline needs content to work with; react is more honest here.
        if _should_react(intent, dom_emo, dom_val, inner, resource_deficit):
            reply = _react(intent, dom_emo, resource_deficit)
            log_activity(f"[speech_gate] react (affect) → {reply[:60]}")
            return reply

        # 4. Full symbolic pipeline — primary path for all substantive replies.
        #
        #    speech_pipeline.build_response() runs the complete Stage 1-4 chain
        #    with KG/concept injection, Theory of Mind override, person register
        #    sizing, and cognitive-mode memory reweighting.
        #
        #    FORCE_SYMBOLIC_SPEECH=True  → never calls LLM
        #    FORCE_SYMBOLIC_SPEECH=False → tries symbolic first, LLM as fallback
        try:
            from brain.behavior.speech_pipeline import build_response as _build_response
            reply = (_build_response(user_input, context, affect_state) or "").strip()
            if reply and reply != "I'm here.":
                log_activity(f"[speech_gate] pipeline → {reply[:60]}")
                return reply
            # "I'm here." means the pipeline had nothing — fall through to express
            if reply == "I'm here." and inner:
                pass   # try express below
            elif reply:
                return reply
        except Exception as _pipe_e:
            log_error(f"[speech_gate] pipeline failed: {_pipe_e}")

        # 5. Express fallback — translate inner monologue via constrained LLM call.
        #    Only reached when: pipeline returned generic "I'm here." AND inner exists
        #    AND LLM is available AND FORCE_SYMBOLIC_SPEECH is False.
        try:
            from brain.behavior.speech_pipeline import FORCE_SYMBOLIC_SPEECH as _FSS
        except Exception:
            _FSS = False
        if inner and llm_available() and not _FSS:
            reply = _express(user_input, inner, intent, affect_state, context)
            if reply:
                log_activity(f"[speech_gate] express (llm) → {reply[:60]}")
                return reply

        # 6. Last resort
        reply = _react(intent, dom_emo, resource_deficit)
        log_activity(f"[speech_gate] react (last resort) → {reply[:60]}")
        return reply

    except Exception as e:
        log_error(f"[speech_gate] build_speech failed: {e}")
        return "I'm here."
