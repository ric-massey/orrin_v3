# think/speech_planner.py
#
# Stage 3 — Response Planning
#
# Takes the outputs of Stage 1 (comprehension) and Stage 2 (retrieved memories)
# plus Orrin's current affect state, active goal, and inner-loop thought, then
# decides:
#
#   response_type — what kind of response to give
#   primary       — the main thing to say (memory excerpt or inner thought)
#   secondary     — optional supporting detail
#   ask_back      — follow-up question to pose at the end, or None
#   tone          — affect-derived delivery tone
#   length        — brief | medium | full
#   source        — where primary came from (inner | long_memory | working_memory | goal | affect)
#
# Response type taxonomy:
#   answer        — directly responds to a question using retrieved knowledge
#   share_finding — offers a relevant observation or research finding
#   express_state — describes Orrin's current internal state / what he's working on
#   uncertainty   — honest "I don't know" with a redirect
#   acknowledge   — brief acknowledgment of a command or short statement
#   invite        — opens a topic, invites the user to continue
from __future__ import annotations

import random as _random
import time as _time
from typing import Any, Dict, List, Optional, Tuple


# ── Template rate-limiting (BEHAVIOR_FIX_PLAN Phase 3) ────────────────────────
# Any single canned template fires at most once per conversation window —
# honest unavailability beats the same deflection every turn (audit §4 caught
# "What got you thinking about this?" on every reply).

_TEMPLATE_WINDOW_S = 600.0          # one conversation window ≈ 10 minutes
_template_last_used: Dict[str, float] = {}


def _once_per_window(template: Optional[str]) -> Optional[str]:
    """Return the template if it hasn't fired this window, else None."""
    if not template:
        return template
    now = _time.monotonic()
    if now - _template_last_used.get(template, 0.0) < _TEMPLATE_WINDOW_S:
        return None
    _template_last_used[template] = now
    return template


_HONEST_UNAVAILABILITY = (
    "I don't have a good answer to that yet.",
    "I don't know enough about that yet to say anything useful.",
    "Honestly, that's outside what I know right now.",
    "I haven't learned enough about that to have a real answer.",
)


def _honest_unknown() -> str:
    return _random.choice(_HONEST_UNAVAILABILITY)


# ── Theory of Mind override ───────────────────────────────────────────────────

def _apply_tom_override(plan: Dict[str, Any], tom: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Adjust the plan based on Theory of Mind signals.

    Misalignment trumps everything — if the user doesn't feel understood,
    stop sharing information and acknowledge first.

    Intention shapes response type — a user seeking connection doesn't want
    a fact dump, a user seeking information doesn't want emotional expression.

    Affective state shapes ask_back — distressed users get a checking-in
    question rather than a topic-expansion question.
    """
    if not tom:
        return plan

    misaligned      = tom.get("misaligned", False)
    intention       = str(tom.get("their_intention") or "")
    affective_state = str(tom.get("their_affective_state") or "")
    shift           = tom.get("shift")

    # Misalignment: switch away from content delivery
    if misaligned:
        if plan["response_type"] in ("answer", "share_finding"):
            plan["response_type"] = "acknowledge"
            plan["ask_back"]      = "What would actually be useful right now?"
            plan["source"]        = "tom_realign"
        return plan

    # Positive shift after misalignment: stay warm, don't immediately info-dump
    if isinstance(shift, tuple) and len(shift) >= 1 and shift[0] == "improved":
        if plan["response_type"] in ("answer", "uncertainty"):
            plan["response_type"] = "share_finding"
            plan["source"]        = "tom_reconnect"

    # User is seeking connection — emotional engagement over information
    if intention == "seeking_connection":
        if plan["response_type"] in ("answer", "uncertainty"):
            plan["response_type"] = "express_state"
            plan["source"]        = "tom_connection"

    # User is clearly seeking information — don't deflect with personal expression
    if intention == "seeking_information":
        if plan["response_type"] == "express_state" and plan["source"] == "affect":
            plan["response_type"] = "uncertainty"
            plan["source"]        = "tom_information"

    # Distressed or frustrated user — soften ask_back
    if affective_state in ("distressed", "frustrated", "confused"):
        if plan.get("ask_back") and "?" in str(plan["ask_back"]):
            plan["ask_back"] = "Does that help at all?"

    return plan


# ── Register → length override ────────────────────────────────────────────────

_REGISTER_LENGTH: Dict[str, str] = {
    "concise": "brief",
    "direct":  "brief",
    "terse":   "brief",
    "warm":    "medium",
    "formal":  "medium",
}


def _length_for_register(register: str, default_length: str) -> str:
    """Override computed length with person's preferred register if set."""
    return _REGISTER_LENGTH.get(register, default_length)


# ── Symbolic dictionary lookup ────────────────────────────────────────────────

def _sym_dict_lookup(topics: List[str]) -> str:
    """
    Check the symbolic dictionary for any of the topic tokens.
    Returns a short definition string if found, "" otherwise.
    Used as a fallback before returning an uncertainty response — if we have
    a definition for the topic, we can give a minimal informative answer
    instead of conceding ignorance.
    """
    if not topics:
        return ""
    try:
        from brain.symbolic.symbolic_dictionary import define
        for topic in topics:
            for token in topic.lower().split():
                if len(token) > 3:
                    defn = define(token)
                    if defn:
                        return defn[:200]
    except (ImportError, OSError, KeyError, TypeError):  # best-effort symbolic-dictionary lookup
        pass
    return ""


# ── Affect helpers ────────────────────────────────────────────────────────────

def _dominant_affect(affect: Dict) -> Tuple[str, float]:
    """Return (affect_name, value) for the strongest signal in affect_state."""
    core = affect.get("core_signals") or affect
    if not isinstance(core, dict):
        return "neutral", 0.0
    candidates = {
        k: float(v)
        for k, v in core.items()
        if isinstance(v, (int, float)) and float(v) > 0.15
    }
    if not candidates:
        return "neutral", 0.0
    name = max(candidates, key=lambda k: candidates[k])
    return name, candidates[name]


def _tone_label(affect_name: str, affect_val: float) -> str:
    """Map affect name to a tone token used in speech_builder templates."""
    mapping = {
        "exploration_drive":    "curious",
        "novelty_signal":       "contemplative",
        "impasse_signal":  "frustrated",
        "stagnation_signal":      "bored",
        "reward_positive":          "happy",
        "threat_level":         "uncertain",
        "resource_deficit":      "tired",
        "risk_estimate":      "uncertain",
        "confidence":   "neutral",
    }
    return mapping.get(affect_name, "neutral")


# ── Length ────────────────────────────────────────────────────────────────────

def _response_length(intent: str, tone: str) -> str:
    if tone in ("tired", "bored"):
        return "brief"
    if tone == "frustrated":
        return "brief"
    if intent in ("question", "opinion_request"):
        return "medium"
    if tone in ("curious", "contemplative"):
        return "medium"
    return "brief"


# ── Epistemic stance calibration (Du Bois 2001) ───────────────────────────────
#
# Maps the top memory's source and relevance to an epistemic label that
# the builder uses to select the right confidence-level template.

def _get_epistemic(top_mem: Optional[Dict]) -> str:
    """
    Calibrate epistemic stance from the memory entry that will be the reply's
    primary content.

    Du Bois (2001) stance triangle: epistemic stance (what I know/believe)
    must be marked to match actual confidence. Speaking with evidential
    framing ("From what I read") when confidence is low damages trust.
    """
    if top_mem is None:
        return "hedged"
    mem_type  = str(top_mem.get("type") or "")
    relevance = float(top_mem.get("_relevance") or 0.0)

    if mem_type in ("concept_definition", "knowledge_graph"):
        return "certain"    # authoritative source — direct assertion appropriate
    if mem_type == "opinion":
        return "opinion"    # personal stance — contemplative frame
    if relevance >= 0.60:
        return "evidential" # strong memory match — evidential frame
    if relevance >= 0.35:
        return "evidential" # moderate match — evidential (builder adds light hedge)
    return "hedged"         # weak match — explicit uncertainty frame


# ── Ask-back question (Pickering & Garrod 2004 — lexical alignment) ───────────

def _ask_back(
    comprehension: Dict,
    tone: str,
    memories: List[Dict],
    goal: Dict,
) -> Optional[str]:
    intent    = comprehension.get("intent", "statement")
    topics    = comprehension.get("topics", [])
    key_terms = comprehension.get("key_terms", [])

    # Pickering & Garrod (2004): prefer the user's own vocabulary when asking back.
    # key_terms are extracted from the raw input so they mirror what the user said.
    # Fall back to longest topic when no key_terms available.
    focal = (key_terms[0] if key_terms else None) or (max(topics, key=len) if topics else None)

    # Don't pepper the user with questions when tired or after short acks
    if tone == "tired" or intent in ("greeting", "short_ack", "command"):
        return None

    # Curious — Orrin wants to know what the user thinks
    if tone == "curious" and focal:
        return f"What's your take on {focal}?"

    # Question without a good answer → redirect
    if intent in ("question", "opinion_request") and not memories:
        return "What made you think of this?"

    # Active goal — occasionally connect
    if goal and goal.get("title") and tone not in ("frustrated", "uncertain"):
        if focal:
            return f"Does that connect to {goal.get('title', '')} at all?"

    # Contemplative — open the floor
    if tone == "contemplative":
        return "Does that track with your experience?"

    return None


# ── Public entry ──────────────────────────────────────────────────────────────

def _plan_core(
    comprehension:  Dict[str, Any],
    memories:       List[Dict],
    inner:          str,
    affect:         Dict[str, Any],
    goal:           Dict[str, Any],
    register:       str,
) -> Dict[str, Any]:
    """Decision tree that builds the raw plan. ToM override applied by plan_response."""
    intent      = comprehension.get("intent", "statement")
    about_orrin = comprehension.get("about_orrin", False)
    about_goal  = comprehension.get("about_goal", False)
    topics      = comprehension.get("topics", [])
    epistemic   = _get_epistemic(memories[0] if memories else None)

    affect_name, affect_val = _dominant_affect(affect)
    tone   = _tone_label(affect_name, affect_val)
    length = _length_for_register(register, _response_length(intent, tone))

    top_mem   = memories[0] if memories else None
    sec_mem   = memories[1] if len(memories) > 1 else None
    has_mem   = bool(top_mem and top_mem.get("_relevance", 0) > 0.12)
    has_inner = bool(inner and len(inner.strip()) > 30)

    def _primary_mem() -> str:
        return top_mem.get("_excerpt", "") if top_mem else ""

    def _secondary_mem() -> str:
        return sec_mem.get("_excerpt", "") if sec_mem else ""

    def _ask() -> Optional[str]:
        return _ask_back(comprehension, tone, memories, goal)

    # ── Decision tree ─────────────────────────────────────────────────────────

    # 1. User is asking about Orrin's own state or current work
    if about_orrin or intent == "status_check":
        if about_goal and goal and goal.get("title"):
            return {
                "response_type": "express_state",
                "primary":   f"Working on {goal['title']} right now.",
                "secondary": _primary_mem() if has_inner else "",
                "ask_back":  _ask(),
                "tone":      tone,
                "length":    length,
                "source":    "goal",
            }
        # Asked what he's been doing/learning and he has a relevant finding →
        # lead with the actual finding (what he learned), with his inner state as
        # supporting colour. This is how "what have you been up to?" gets a real
        # answer instead of a vague mood report.
        if has_mem:
            return {
                "response_type": "share_finding",
                "primary":   _primary_mem(),
                "secondary": (inner.strip()[:160] if has_inner else _secondary_mem()),
                "ask_back":  _ask(),
                "tone":      tone,
                "length":    length,
                "source":    "long_memory",
            }
        if has_inner:
            return {
                "response_type": "express_state",
                "primary":   inner.strip()[:200],
                "secondary": _primary_mem(),
                "ask_back":  _ask(),
                "tone":      tone,
                "length":    length,
                "source":    "inner",
            }
        # Nothing topic-matched and no inner thought — but "what have you been
        # learning/up to?" deserves a real answer. Surface a recent finding by
        # recency rather than collapsing to a terse mood report.
        try:
            from brain.think.speech_memory import recent_findings as _recent_findings
            _rf = _recent_findings(2)
        except Exception:
            _rf = []
        if _rf:
            return {
                "response_type": "share_finding",
                "primary":   _rf[0],
                "secondary": _rf[1] if len(_rf) > 1 else "",
                "ask_back":  _ask(),
                "tone":      tone,
                "length":    length,
                "source":    "recent_finding",
            }
        # Fall through to affect-based express_state below

    # 2. Direct question + have relevant memory → answer
    if intent in ("question",) and has_mem:
        return {
            "response_type": "answer",
            "primary":   _primary_mem(),
            "secondary": _secondary_mem(),
            "ask_back":  _ask(),
            "tone":      tone,
            "length":    length,
            "source":    "long_memory",
            "epistemic": epistemic,
        }

    # 3. Opinion request + memory → share perspective
    if intent == "opinion_request":
        if has_mem:
            return {
                "response_type": "share_finding",
                "primary":   _primary_mem(),
                "secondary": "",
                "ask_back":  _ask(),
                "tone":      tone,
                "length":    "medium",
                "source":    "long_memory",
                "epistemic": epistemic,
            }
        # Brown & Levinson (1987) face restoration: "I don't know" is a face-threatening
        # act. Adding "What do you think?" mitigates it and restores affiliative frame.
        return {
            "response_type": "uncertainty",
            "primary":   " ".join(topics[:2]) if topics else "that",
            "secondary": _honest_unknown(),
            "ask_back":  _once_per_window("What do you think?"),
            "tone":      tone,
            "length":    "brief",
            "source":    "affect",
            "epistemic": "hedged",
        }

    # 4. Question with no memory → check symbolic dictionary before conceding uncertainty
    if intent == "question" and not has_mem:
        topic_str = " ".join(topics[:2]) if topics else ""
        sym_def   = _sym_dict_lookup(topics)
        if sym_def:
            return {
                "response_type": "answer",
                "primary":   sym_def,
                "secondary": "",
                "ask_back":  _ask(),
                "tone":      tone,
                "length":    "brief",
                "source":    "symbolic_dictionary",
                "epistemic": "evidential",
            }
        # Brown & Levinson: mitigate the face-threat of uncertainty with a
        # secondary affiliative element — signals exploration_drive not just ignorance.
        # Honest unavailability beats deflection: say plainly that no grounded
        # answer exists; the deflection question fires at most once per window.
        face_restore = "Worth looking into though." if tone in ("curious", "contemplative") else ""
        return {
            "response_type": "uncertainty",
            "primary":   topic_str or "that",
            "secondary": face_restore or _honest_unknown(),
            "ask_back":  _once_per_window("What got you thinking about this?"),
            "tone":      tone,
            "length":    "brief",
            "source":    "affect",
            "epistemic": "hedged",
        }

    # 5. Command → brief acknowledgment
    if intent == "command":
        return {
            "response_type": "acknowledge",
            "primary":   "",
            "secondary": "",
            "ask_back":  None,
            "tone":      tone,
            "length":    "brief",
            "source":    "affect",
            "epistemic": "certain",
        }

    # 6. Statement or emotional + memory → share related finding
    if intent in ("statement", "emotional") and has_mem:
        return {
            "response_type": "share_finding",
            "primary":   _primary_mem(),
            "secondary": "",
            "ask_back":  _ask(),
            "tone":      tone,
            "length":    length,
            "source":    "long_memory",
            "epistemic": epistemic,
        }

    # 7. Inner thought available → share it
    if has_inner:
        return {
            "response_type": "share_finding",
            "primary":   inner.strip()[:200],
            "secondary": "",
            "ask_back":  _ask(),
            "tone":      tone,
            "length":    length,
            "source":    "inner",
            "epistemic": "evidential",
        }

    # 8. Fall back: express current affect state
    return {
        "response_type": "express_state",
        "primary":   "",
        "secondary": "",
        "ask_back":  None,
        "tone":      tone,
        "length":    "brief",
        "source":    "affect",
        "epistemic": "hedged",
    }


def plan_response(
    comprehension:  Dict[str, Any],
    memories:       List[Dict],
    inner:          str,
    affect:         Dict[str, Any],
    goal:           Dict[str, Any],
    *,
    theory_of_mind: Optional[Dict[str, Any]] = None,
    register:       str = "neutral",
) -> Dict[str, Any]:
    """
    Stage 3 public entry point. Calls _plan_core then applies Theory of Mind
    and register overrides before returning.

    theory_of_mind — from context["theory_of_mind"]: used to override response
                     type when the user is misaligned or their intention conflicts
                     with the default plan.
    register       — person's preferred style ("concise", "warm", etc.): applied
                     to the length field so content is sized correctly upfront,
                     before pre_speak_check sees it.
    """
    plan = _plan_core(comprehension, memories, inner, affect, goal, register)
    return _apply_tom_override(plan, theory_of_mind)
