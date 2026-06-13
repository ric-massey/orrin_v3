# think/speech_coherence.py
#
# Coherence enforcement for Stage 4 slot filling.
#
# Problem: frame templates have typed {content} slots.  "Been chewing on
# {content}" takes a grammatical OBJECT — inserting a full sentence there
# produces broken output ("Been chewing on The binding problem refers to...").
# "From what I read — {content}" takes a CLAUSE — any length is fine.
#
# This module detects slot type from the template surface form, adjusts
# content to match, enforces casing rules, and cleans punctuation artifacts.
# It is the last gate before any reply string leaves Stage 4.
#
# Linguistic grounding:
#   Goldberg (1995, 2006) construction grammar: form and meaning are stored
#   as a unit.  The {content} slot is typed by its syntactic position inside
#   the construction; inserting wrong-shaped material violates the
#   construction's internal grammar and produces unacceptable output.
#   Chafe (1994) on "flow of information" and Givón (1984) on topic
#   continuity both predict that the information shape of a slot must match
#   the discourse function of the frame — a new-information clause cannot
#   occupy an old-information argument position without repair.
from __future__ import annotations

import re
from typing import List


# ── Slot-type detection ───────────────────────────────────────────────────────
#
# CLAUSE  — slot follows a colon, em-dash, or ellipsis.
#           Content begins a new clause; any length is acceptable.
#           First letter should be uppercase.
#
# OBJECT  — slot is the direct object of a preposition ("chewing on …",
#           "working through …").  Content should be a short noun phrase.
#           If a full sentence is supplied, truncate to the head noun phrase.
#           First letter should be lowercase.
#
# FREE    — bare slot with no syntactic context cue (e.g. "{content}." alone).
#           Minimal constraints; content is used as-is.

_OBJECT_RE = re.compile(
    r'\b(on|about|through|around|over|with|toward|towards)\s+\{content\}',
    re.IGNORECASE,
)
_CLAUSE_SEP_RE = re.compile(
    r'(?:[:—\-]|\.\.\.)\s*\{content\}',
)

# Finite-verb heuristic — if a string contains one of these and is long
# enough, treat it as a full sentence rather than a noun phrase.
_VERB_RE = re.compile(
    r'\b(is|are|was|were|has|have|had|does|do|did|will|would|could|should|'
    r'refers|relates|involves|describes|shows|suggests|indicates|means|'
    r'requires|creates|produces|leads|results|comes|makes|takes|gives|'
    r'gets|uses|needs|forms|causes|allows|enables|supports|represents|'
    r'reflects|contains|includes|consists|begins|ends|occurs|happens|'
    r'exists|appears|seems|feels|becomes|remains|operates|functions|'
    r'activates|modulates|encodes|consolidates|integrates|generates|'
    r'predicts|updates|processes|computes|stores|retrieves|selects)\b',
    re.IGNORECASE,
)

# Words that should be stripped from the end of a noun-phrase truncation
_TRAILING_FUNCTION = {
    "is", "are", "was", "were", "has", "have", "had",
    "of", "in", "at", "to", "a", "an", "the", "and",
    "that", "which", "when", "where", "who", "with",
}


# ── Public helpers ────────────────────────────────────────────────────────────

def slot_type(template: str) -> str:
    """
    Inspect a frame template string and return the positional type of its
    {content} slot: 'object', 'clause', or 'free'.
    """
    if _OBJECT_RE.search(template):
        return "object"
    if _CLAUSE_SEP_RE.search(template):
        return "clause"
    return "free"


def is_full_sentence(text: str) -> bool:
    """
    Heuristic: True when text reads as a complete declarative sentence.
    Requires >= 5 words AND at least one recognisable finite verb.
    Short phrases with verbs ("is real", "seems true") are excluded by
    the word-count floor.
    """
    if not text or len(text.split()) < 5:
        return False
    return bool(_VERB_RE.search(text))


def to_noun_phrase(text: str, max_words: int = 6) -> str:
    """
    Reduce a full sentence to a short noun phrase for OBJECT-slot frames.

    Strategy: walk forward word by word and stop just before the first
    finite verb.  Cap at max_words.  Strip trailing function words and
    punctuation from whatever survives.  Falls back to a hard 40-character
    truncation if nothing meaningful remains.
    """
    words = text.strip().rstrip(".,;:!?—").split()
    kept: List[str] = []
    for w in words[:max_words]:
        # Stop before the first finite verb (sentence begins here)
        if _VERB_RE.search(w) and kept:
            break
        kept.append(w)
    # Strip trailing function words from the resulting chunk
    while kept and kept[-1].lower() in _TRAILING_FUNCTION:
        kept.pop()
    if not kept:
        return text[:40].rstrip(".,;:!? ")
    return " ".join(kept)


def _apply_casing(content: str, template: str) -> str:
    """
    Adjust the first letter of content based on its syntactic position
    inside the template.

      After colon / dash / ellipsis → uppercase (starts a new clause).
      After bare preposition        → lowercase (continues the NP argument).
      Otherwise                     → leave as-is.
    """
    if not content:
        return content
    slot_idx = template.find("{content}")
    if slot_idx < 0:
        return content
    before = template[:slot_idx].rstrip()
    if not before:
        return content
    if before[-1] in ":—-" or before.endswith("..."):
        return content[0].upper() + content[1:]
    if re.search(r'\b(on|about|through|around|over|with)\s*$', before, re.IGNORECASE):
        return content[0].lower() + content[1:]
    return content


def is_compatible(template: str, content: str) -> bool:
    """
    Quick compatibility check used by the frame-selection loop.

    Returns False when filling the slot would require destructive truncation
    that loses substantive information — specifically an OBJECT-slot frame
    being handed a full sentence.  In that case the caller should prefer a
    CLAUSE-slot frame rather than truncating.
    """
    if slot_type(template) == "object" and is_full_sentence(content):
        return False
    return True


def cohere(template: str, content: str) -> str:
    """
    Fill {content} in template, enforcing three coherence rules:

    1. Object-slot frames receive a truncated noun phrase when content is a
       full sentence.
    2. First-letter casing matches the syntactic position.
    3. Double punctuation and orphaned trailing dashes are cleaned.

    Returns the filled template string.
    """
    if not content:
        return template.replace("{content}", "")

    stype = slot_type(template)
    text  = content.strip()

    if stype == "object" and is_full_sentence(text):
        text = to_noun_phrase(text)

    text   = _apply_casing(text, template)
    result = template.replace("{content}", text)

    # Clean punctuation artifacts
    result = re.sub(r'([.!?])\s*[.!?]', r'\1', result)   # double sentence-end
    result = re.sub(r'[—\-:]\s*$', '', result).strip()    # orphaned separator at end
    return result


def cohere_topic(topic: str) -> str:
    """
    Clean a topic string for mid-sentence {topic} slots (uncertainty templates).

    Uncertainty templates embed the topic inside a running sentence:
      "Don't have much on {topic} yet."
      "Not enough on {topic} to say."

    The topic must therefore be:
      - Lowercase (mid-sentence)
      - 1–4 words (longer reads as a clause, breaking the sentence rhythm)
      - No leading article (the/a/an adds nothing mid-sentence)
    """
    words = topic.strip().lower().split()
    if words and words[0] in ("the", "a", "an"):
        words = words[1:]
    words = words[:4]
    return " ".join(words) if words else topic
