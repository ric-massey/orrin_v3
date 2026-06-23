# think/speech_builder.py
#
# Stage 4 — Sentence Construction
#
# Fills templates with real content from the Stage 3 plan to produce a final
# reply string.  Templates are organised by (response_type, tone).  Each slot
# is filled from the plan dict; missing or empty slots degrade gracefully.
#
# Orrin's voice rules (derived from existing speech_gate.py templates):
#   - Direct.  No filler ("Great question", "Certainly", "Of course").
#   - Honest about uncertainty.
#   - First-person but not self-absorbed.
#   - Fragments are fine when they serve clarity.
#   - Do not start with "I".
from __future__ import annotations

import random
import re
from brain.utils.failure_counter import record_failure
from typing import Any, Dict, List, Optional

from brain.think.speech_coherence import cohere, cohere_topic, is_compatible
# Static template tables (_T, _AFFECT_FALLBACKS), extracted to speech_templates.py
# (Phase 4.5C).
from brain.think.speech_templates import _T, _AFFECT_FALLBACKS  # noqa: F401



# ── Construction grammar layer ────────────────────────────────────────────────
#
# A "construction" (Goldberg 1995) is a form-meaning pairing stored at the
# clause level.  Each construction type has:
#   detect — regex that recognises this frame type in a past reply
#   frames — surface realisations with a {content} slot
#
# When >= _MIN_EXEMPLARS scored replies exist, Stage 4 classifies each
# exemplar into a frame type, weights types by (quality × topic_relevance),
# selects the best frame type, and fills a surface form with current content.
#
# Frame selection is gated by speech_coherence.is_compatible() to avoid
# inserting full sentences into OBJECT-position slots.

_MIN_EXEMPLARS = 4

_FRAME_TYPES: List[Dict] = [
    {
        "name": "evidential",
        # Matches: "From what I read/found/know/learned/picked up",
        #          "From what I've read/found", "Picked this up",
        #          "Came across", "What I have/read/found on"
        "detect": re.compile(
            r"^(from what i(?:'ve)? (read|know|found|learned|picked up)|"
            r"picked this up|came across|what i (read|found|have on))",
            re.IGNORECASE,
        ),
        "frames": [
            "From what I read — {content}",
            "From what I found — {content}",
            "Picked this up recently — {content}",
            "What I have on that: {content}",
            "Came across this: {content}",
        ],
    },
    {
        "name": "internal_state",
        "detect": re.compile(
            r"^(been (sitting|thinking|chewing|circling|turning)|"
            r"something (keeps|has|came up|is pulling)|"
            r"this keeps|can't let go)",
            re.IGNORECASE,
        ),
        "frames": [
            "Been sitting with this: {content}",
            "Something keeps coming back — {content}",
            "This keeps pulling at me — {content}",
            "Can't let go of this: {content}",
            "Something keeps coming up: {content}",
        ],
    },
    {
        "name": "associative",
        "detect": re.compile(
            r"^(connects|that (ties|connects)|funny you|"
            r"this (actually|ties|connects)|there's a thread|worth knowing)",
            re.IGNORECASE,
        ),
        "frames": [
            "Connects to something I read — {content}",
            "That ties in — {content}",
            "This actually connects: {content}",
            "There's a thread here — {content}",
            "Worth knowing: {content}",
        ],
    },
    {
        "name": "hedged",
        "detect": re.compile(
            r"^(not (sure|certain)|honestly|best i|take this|might be|"
            r"not there yet|haven't|don't have)",
            re.IGNORECASE,
        ),
        "frames": [
            "Not certain, but: {content}",
            "Honestly — {content}",
            "Best I've got: {content}",
            "Might be off, but — {content}",
            "Take this with some caution — {content}",
        ],
    },
    {
        "name": "attention",
        "detect": re.compile(
            r"^(something (interesting|strange|relevant|worth)|"
            r"there's something|related|short (answer|version))",
            re.IGNORECASE,
        ),
        "frames": [
            "Something interesting here — {content}",
            "Something relevant: {content}",
            "There's something worth knowing — {content}",
            "Related: {content}",
            "Short version: {content}",
        ],
    },
    {
        "name": "bare",
        "detect": None,   # catch-all
        "frames": [
            "{content}",
            "{content}.",
        ],
    },
]


def _classify_frame(reply: str) -> str:
    """Return the frame type name that best matches a past reply string."""
    r = reply.strip()
    for ft in _FRAME_TYPES[:-1]:   # skip bare (catch-all)
        if ft["detect"] and ft["detect"].search(r):
            return ft["name"]
    return "bare"


def _frame_by_name(name: str) -> Dict:
    for ft in _FRAME_TYPES:
        if ft["name"] == name:
            return ft
    return _FRAME_TYPES[-1]   # bare fallback


def _topic_relevance(exemplar_topics: List[str], current_tokens: set) -> float:
    """Overlap fraction between exemplar topics and current query topics."""
    if not current_tokens or not exemplar_topics:
        return 0.1
    ex_tokens = {t.lower() for t in exemplar_topics if len(t) > 3}
    overlap   = len(ex_tokens & current_tokens)
    return min(1.0, 0.1 + overlap / len(current_tokens))


def _score_frames(
    exemplars:      List[Dict],
    current_topics: List[str],
) -> Dict[str, float]:
    """
    Compute a weighted score for each frame type across scored exemplars.

    weight = quality_score × topic_relevance

    Frame types with more high-quality, topically relevant exemplars
    score higher, making the construction grammar statistically grounded.
    """
    current_tokens = {t.lower() for t in current_topics if len(t) > 3}
    totals: Dict[str, float] = {}
    for ex in exemplars:
        q     = float(ex.get("quality_score") or 0.5)
        rel   = _topic_relevance(ex.get("topics", []), current_tokens)
        fname = _classify_frame(ex.get("reply", ""))
        totals[fname] = totals.get(fname, 0.0) + (q * rel)
    return totals


def build_from_exemplars(
    exemplars:    List[Dict],
    plan:         Dict[str, Any],
    comprehension: Dict[str, Any],
) -> str:
    """
    Construction grammar-based reply generation.

    1. Score frame types by (quality × topic_relevance) across all exemplars.
    2. Select the highest-scoring frame type whose templates are compatible
       with the current content shape (coherence guard).
    3. Pick a random surface form from that frame type.
    4. Fill {content} via speech_coherence.cohere() for slot-shape enforcement.

    Returns "" if exemplars are insufficient or content is empty.
    """
    if len(exemplars) < _MIN_EXEMPLARS:
        return ""

    primary = _clean(str(plan.get("primary", "") or ""))
    if not primary:
        return ""

    topics       = comprehension.get("topics", [])
    frame_scores = _score_frames(exemplars, topics)

    if not frame_scores:
        return ""

    # Sort frame types by score descending; walk until we find a compatible one
    ranked = sorted(frame_scores, key=lambda k: frame_scores[k], reverse=True)
    selected_frames: List[str] = []

    for fname in ranked:
        ft       = _frame_by_name(fname)
        all_tmpl = ft["frames"]
        compatible = [t for t in all_tmpl if is_compatible(t, primary)]
        if compatible:
            selected_frames = compatible
            break

    if not selected_frames:
        # Nothing compatible — use bare frames as last resort
        selected_frames = _frame_by_name("bare")["frames"]

    template = random.choice(selected_frames)
    result   = cohere(template, primary)
    result   = re.sub(r"\s{2,}", " ", result).strip()
    return result


# ── Slot filling ──────────────────────────────────────────────────────────────

def _clean(text: str, max_len: int = 160) -> str:
    """Strip whitespace and truncate cleanly at a sentence or word boundary."""
    text = text.strip()
    if not text or len(text) <= max_len:
        return text
    for punct in (".", "!", "?", ";"):
        idx = text.rfind(punct, 0, max_len)
        if idx > max_len * 0.5:
            return text[: idx + 1]
    idx = text.rfind(" ", 0, max_len)
    return (text[:idx] + "…") if idx > 0 else text[:max_len]


def _fill(template: str, slots: Dict[str, str]) -> str:
    """
    Replace {slot} markers in template.

    {topic} receives cohere_topic() treatment — lowercase, max 4 words,
    no leading article — because uncertainty templates embed it mid-sentence.

    Empty slot values are removed cleanly, and leftover punctuation artifacts
    are collapsed.
    """
    result = template
    for key, val in slots.items():
        if key == "topic" and val:
            val = cohere_topic(val)
        result = result.replace("{" + key + "}", val if val else "")
    result = re.sub(r"\s{2,}", " ", result).strip()
    result = re.sub(r"([.!?,;])\s*([.!?,;])", r"\1", result)
    result = re.sub(r"—\s*$", "", result).strip()
    return result


def _construction_score(response_type: str, tone: str) -> float:
    """Return the learned quality score for this (response_type, tone) bucket."""
    try:
        from brain.think.speech_log import get_construction_score
        return get_construction_score(response_type, tone)
    except Exception as _e:
        record_failure("speech_builder._construction_score", _e)
        return 0.5


def _pick(response_type: str, tone: str) -> str:
    """
    Select a template for (response_type, tone).

    Uses the construction score to weight the choice:
    - score >= 0.65 → bucket is working; use it normally
    - score <= 0.30 → try neutral fallback (this tone isn't landing)
    - otherwise     → random as usual

    Gracefully falls back when no score data exists yet.
    """
    score = _construction_score(response_type, tone)

    if score < 0.30:
        neutral_key = (response_type, "neutral")
        if neutral_key in _T:
            return random.choice(_T[neutral_key])

    key = (response_type, tone)
    if key in _T:
        return random.choice(_T[key])

    neutral_key = (response_type, "neutral")
    if neutral_key in _T:
        return random.choice(_T[neutral_key])

    return "{primary}"


# ── Public entry ──────────────────────────────────────────────────────────────

# ── Length → content size (Grice 1975 — Quantity maxim) ──────────────────────
#
# The plan["length"] field says how much to say; _clean() enforces it.
# Previously all responses got 160 chars regardless of length field.
# brief=80 (~40 words): one focused idea.  medium=140 (~70 words): one idea
# with support.  full=220 (~110 words): developed, multi-clause response.
_LENGTH_MAX: Dict[str, int] = {"brief": 80, "medium": 140, "full": 220}


# ── Epistemic frame override for answer type (Du Bois 2001 — stance) ─────────
#
# Which frame type to prefer based on the confidence of the content source.
# Overrides tone-driven template selection when response_type == "answer"
# so that low-confidence matches don't get assertive evidential framing.
#
# plan["epistemic"]:
#   "certain"    — KG/concept_definition or very high relevance (>= 0.65)
#   "evidential" — good memory match (>= 0.35): "From what I read/found"
#   "hedged"     — weak match (< 0.35): "Not certain, but" / "Best I've got"
#   "opinion"    — from opinion store: first-person stance frames
_EPISTEMIC_TONE_OVERRIDE: Dict[str, str] = {
    "certain":    "neutral",       # direct assertion; tone from affect
    "evidential": "curious",       # evidential framing ("From what I read")
    "hedged":     "uncertain",     # always hedged ("Not certain, but")
    "opinion":    "contemplative", # personal stance ("Something I keep turning over")
}


_SANITIZE_TAG = re.compile(r"\[[A-Za-z_][^\]]*\]?")        # [chunk:…, [world_model], [metacog/
_SANITIZE_KV = re.compile(r"\(?\b[a-z_]+=\S*\)?")          # description=, (description=), score=0.3
_SANITIZE_CAMEUP = re.compile(r"\s*[—:-]?\s*it came up in:.*$", re.I | re.S)


def sanitize_speech(text: str) -> str:
    """Strip internal instrumentation that must never reach the user — bracket
    tags, attribute soup, and trailing raw-memory quotes — so a reply reads as
    speech, not a machine log."""
    s = text or ""
    s = _SANITIZE_CAMEUP.sub("", s)
    s = _SANITIZE_TAG.sub("", s)
    s = _SANITIZE_KV.sub("", s)
    s = re.sub(r"\(\s*\)", "", s)                 # leftover empty parens
    s = re.sub(r"\s{2,}", " ", s).strip(" -—:;,.")
    return s


def build_reply(
    plan:          Dict[str, Any],
    comprehension: Dict[str, Any],
    exemplars:     Optional[List[Dict]] = None,
) -> str:
    """
    Stage 4 entry point.

    Tries the construction grammar (exemplar) path first when enough scored
    exemplars exist.  Falls back to hand-written templates when exemplars are
    insufficient or content is empty.

    Coherence is enforced at two points:
      1. Frame selection — is_compatible() filters out OBJECT-slot frames
         when content is a full sentence.
      2. Slot filling — cohere() adjusts casing and truncates when needed.

    Length enforcement (Grice Quantity): plan["length"] sets max content size.
    Epistemic stance (Du Bois): plan["epistemic"] overrides tone for answers.
    End-focus (Halliday 1967): secondary never appended in brief mode.
    """
    response_type = plan.get("response_type", "express_state")
    tone          = plan.get("tone", "neutral")
    length        = plan.get("length", "medium")
    epistemic     = plan.get("epistemic", "evidential")

    # Grice Quantity: size content to plan length
    max_primary   = _LENGTH_MAX.get(length, 140)
    max_secondary = max_primary // 2

    primary   = _clean(str(plan.get("primary",   "") or ""), max_len=max_primary)
    secondary = _clean(str(plan.get("secondary", "") or ""), max_len=max_secondary)
    ask_back  = (plan.get("ask_back") or "").strip()
    topics    = comprehension.get("topics", [])
    topic     = " ".join(topics[:2]) if topics else "that"

    # Du Bois epistemic: for answer responses, override tone to match confidence
    effective_tone = tone
    if response_type == "answer" and epistemic in _EPISTEMIC_TONE_OVERRIDE:
        override = _EPISTEMIC_TONE_OVERRIDE[epistemic]
        if (response_type, override) in _T:
            effective_tone = override

    # ── Construction grammar path (exemplar-driven) ───────────────────────────
    # Exclude uncertainty: its primary is a topic label, not content — wrapping
    # "consciousness" in "From what I found — {content}" is incoherent.
    # Exclude acknowledge/invite: they are meta-communicative, not content replies.
    base = ""
    _CG_EXCLUDED = ("acknowledge", "invite", "uncertainty")
    if exemplars and primary and response_type not in _CG_EXCLUDED:
        base = build_from_exemplars(exemplars, plan, comprehension)

    # ── Template fallback ─────────────────────────────────────────────────────
    if not base:
        template = _pick(response_type, effective_tone)
        if not primary and "{primary}" in template:
            fallbacks = _AFFECT_FALLBACKS.get(tone, _AFFECT_FALLBACKS["neutral"])
            base = random.choice(fallbacks)
        else:
            slots = {
                "primary":   primary,
                "secondary": secondary,
                "topic":     topic,
            }
            base = _fill(template, slots)

    # Tier 3 — language learned from reading: occasionally open with a framing
    # phrase Orrin picked up from articles he's read, so his voice broadens with
    # exposure. Only for content-bearing replies, only when he's actually learned
    # openers, and never stacked onto a base that already opens with a connective.
    if base and response_type in ("answer", "share_finding", "express_state"):
        try:
            from brain.cognition.language_acquisition import learned_openers as _lo
            _openers = _lo()
            if _openers and random.random() < 0.35:
                _b0 = base.lstrip()
                if _b0 and _b0[0].isupper() and "," not in _b0[:24]:
                    _op = random.choice(_openers)
                    base = f"{_op}, {_b0[0].lower()}{_b0[1:]}"
        except Exception as _e:  # best-effort learned-opener flourish — never break speech
            record_failure("speech_builder.learned_openers", _e)

    # Halliday end-focus: only append secondary when length allows.
    # In brief mode the final clause carries the information weight;
    # appending secondary pushes it from the end and fragments focus.
    if secondary and secondary not in base and length != "brief" and len(base) < 120:
        base = base.rstrip(".!?") + ". " + secondary

    # Append ask-back question with proper sentence separation
    if ask_back:
        base = base.rstrip(" ")
        if base and base[-1] not in ".!?":
            base += "."
        base = base + " " + ask_back

    # Final cleanup
    reply = re.sub(r"\s{2,}", " ", base).strip()

    # Strip any internal instrumentation that leaked into the content (defense in
    # depth on top of the memory-retrieval noise filter).
    reply = sanitize_speech(reply)
    if len(reply) < 2:
        reply = "Still putting words to that — say a bit more?"

    # Ensure first word is not "I" (Orrin's voice rule)
    if reply.startswith("I ") or reply.startswith("I'"):
        reply = "Honestly, " + reply[0].lower() + reply[1:]

    return reply
