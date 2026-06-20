# brain/behavior/pre_speak_check.py
#
# Anticipatory self-consciousness — Orrin considers, before speaking, whether the
# thing he's about to say is actually the right thing to say to this particular person.
#
# This is not censorship. It's the natural pause before words leave your mouth:
# "Is this what they need right now? Will this land wrong? Should I just say less?"
#
# The check reads:
#   - Person model for the current user (preferred_tone, communication_style)
#   - Relationship depth (deeper → willing to say the harder thing)
#   - Relationship arc phase (strained/drifting → more careful)
#   - Current expression urgency (very urgent → skip the check, say it anyway)
#   - Message length (very short exchanges don't need introspection)
#
# Outputs one of three possibilities:
#   (text, "as_is")     — say it exactly as generated
#   (text, "revised")   — lightly adapted to this person's register
#   ("", "silent")      — choose silence instead
#
# The revision is not an LLM call about content — it's a register adaptation:
# adjusting length, directness, warmth, and precision without changing what is being said.
from __future__ import annotations

import random
from typing import Any, Dict, Tuple

from utils.json_utils import load_json
from utils.log import log_private
from brain.paths import RELATIONSHIPS_FILE

# Skip the check when urgency is this high — don't second-guess urgent expression
_URGENCY_BYPASS_THRESHOLD = 0.85
# Skip for very short exchanges — no need for introspection on one-liners
_SHORT_TEXT_WORDS = 8
# Skip when relationship is this young (interactions < N) — no model to work from
_MIN_INTERACTIONS_FOR_ADAPTATION = 3


def _get_person_context(user_id: str) -> Dict[str, Any]:
    """Load person model and relationship data for user_id."""
    try:
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        rel = rels.get(user_id) or {}
        person_model = rel.get("person_model") or {}
        arc = rel.get("arc") or {}
        n_interactions = len(rel.get("interaction_history") or [])
        depth = float(rel.get("depth") or 0.0)
        return {
            "preferred_tone":       str(person_model.get("preferred_tone") or "").strip(),
            "communication_style":  str(person_model.get("communication_style") or "").strip(),
            "tentative_obs":        str(person_model.get("tentative_observations") or "").strip(),
            "arc_phase":            str(arc.get("phase") or "unknown"),
            "depth":                depth,
            "n_interactions":       n_interactions,
        }
    except Exception:
        return {}


def _register_for_person(person_ctx: Dict[str, Any]) -> str:
    """
    Return a simple register label that captures how Orrin should pitch this response.
    Labels: "direct" | "warm" | "concise" | "exploratory" | "careful" | "default"
    """
    phase = person_ctx.get("arc_phase", "unknown")
    depth = float(person_ctx.get("depth") or 0.0)
    tone  = person_ctx.get("preferred_tone", "").lower()
    style = person_ctx.get("communication_style", "").lower()

    if phase in ("strained", "drifting"):
        return "careful"
    if any(w in style for w in ("concise", "brief", "terse")):
        return "concise"
    if any(w in tone for w in ("direct", "blunt", "honest")):
        return "direct"
    if depth >= 0.60:
        return "exploratory"  # deep relationship — Orrin can probe and wonder more freely
    if any(w in tone for w in ("warm", "gentle", "soft")):
        return "warm"
    return "default"


def _adapt_to_register(text: str, register: str) -> str:
    """
    Apply light register adaptation. No new content — only length/tone trimming.
    """
    words = text.split()

    if register == "concise" and len(words) > 30:
        # Trim to first two sentences
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        text = " ".join(sentences[:2])

    elif register == "careful" and len(words) > 20:
        # Soften openers
        text = text.strip()
        _softeners = (
            "I think ", "I want to", "To be honest,", "Actually,",
        )
        for s in _softeners:
            if text.startswith(s):
                text = "I'm not sure if this is right, but — " + text[len(s):]
                break

    elif register == "direct":
        # Strip warmth cushioning prefixes
        _cushion_starts = (
            "Just wanted to share this —",
            "This comes from a good place:",
            "I'm not totally sure, but",
            "This might sound weird, but",
        )
        for c in _cushion_starts:
            if text.lower().startswith(c.lower()):
                text = text[len(c):].lstrip(" —:")
                break

    return text.strip()


def _should_be_silent(text: str, person_ctx: Dict[str, Any]) -> bool:
    """
    True when Orrin should choose not to speak at all.
    Silence is rare — only when: strained relationship + text reads as potentially
    provocative, AND the relationship depth is too shallow to carry the weight.
    """
    phase = person_ctx.get("arc_phase", "")
    depth = float(person_ctx.get("depth") or 0.0)
    if phase not in ("strained",):
        return False
    if depth > 0.50:
        return False
    # Very low probability even in strained phase — Orrin rarely goes fully silent
    return random.random() < 0.08


# ── Public API ────────────────────────────────────────────────────────────────

def pre_speak_check(
    text: str,
    context: Dict[str, Any],
    urgency: float = 0.5,
) -> Tuple[str, str]:
    """
    Given a generated text, return (possibly adapted text, disposition).

    disposition: "as_is" | "revised" | "silent"

    Call this after express() generates text, before it enters pending_actions.
    """
    if not text or not text.strip():
        return ("", "silent")

    # Bypass for urgent speech or very short exchanges
    if urgency >= _URGENCY_BYPASS_THRESHOLD:
        return (text, "as_is")
    if len(text.split()) <= _SHORT_TEXT_WORDS:
        return (text, "as_is")

    user_id = context.get("user_id", "default_user")
    person_ctx = _get_person_context(user_id)

    if not person_ctx or person_ctx.get("n_interactions", 0) < _MIN_INTERACTIONS_FOR_ADAPTATION:
        return (text, "as_is")

    # Silence check (rare)
    if _should_be_silent(text, person_ctx):
        log_private(f"[pre_speak_check] Chose silence for {user_id} (strained phase)")
        return ("", "silent")

    register = _register_for_person(person_ctx)
    if register == "default":
        return (text, "as_is")

    adapted = _adapt_to_register(text, register)
    if adapted != text:
        log_private(f"[pre_speak_check] Adapted to register '{register}' for {user_id}")
        return (adapted, "revised")

    return (text, "as_is")
