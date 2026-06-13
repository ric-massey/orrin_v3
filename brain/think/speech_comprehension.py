# think/speech_comprehension.py
#
# Stage 1 — Comprehension
#
# Parses raw user input into a structured dict that later stages use to decide
# what to say and how to say it.  No memory access, no affect — pure text.
#
# Output keys:
#   intent        — greeting | question | command | opinion_request |
#                   status_check | emotional | statement | short_ack
#   question_type — factual | status | opinion | open | None
#   topics        — list of meaningful keyword strings extracted from input
#   tone          — curious | frustrated | excited | urgent | playful | casual
#   about_orrin   — bool: user is asking about Orrin's state / thoughts
#   about_goal    — bool: user is asking about Orrin's current work
#   raw           — original string, stripped
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Stopwords ─────────────────────────────────────────────────────────────────

_STOP: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "i", "me", "my", "we", "our",
    "orrin", "hello", "hey", "hi",
    "you", "your", "he", "his", "she", "her", "it", "its", "they", "their",
    "this", "that", "these", "those", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "up", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "but", "and", "or", "if", "while",
    "what", "who", "which", "as", "think", "know", "like", "really",
    "thing", "things", "get", "got", "make", "see", "go", "going", "come",
    "right", "still", "also", "actually", "well", "yes", "yeah", "okay",
    "ok", "tell", "said", "say", "let", "want", "need", "mean",
    "working", "doing", "thinking", "feeling", "having", "looking",
    "talking", "trying", "taking", "making", "being", "seem", "seems",
    "really", "just", "much", "many", "some", "them", "then", "time",
    "back", "even", "good", "long", "down", "work", "feel", "been",
    # Common adjectives that are never meaningful topics on their own
    "hard", "easy", "real", "true", "false", "high", "wide", "deep",
    "full", "free", "open", "able", "sure", "next", "last", "late",
    "new", "old", "big", "small", "large", "great", "little", "simple",
    "complex", "clear", "dark", "soft", "fast", "slow", "near", "away",
    "whole", "past", "future", "present", "different", "possible",
    "important", "interesting", "relevant", "specific", "general",
    "certain", "main", "early", "recent", "current", "given", "known",
    # Relational/quantifier words that are never standalone topics
    "term", "kind", "type", "sort", "form", "part", "side", "point",
    "case", "role", "level", "area", "field", "sense", "ways", "terms",
    # Command/request verbs — intent carriers, not topic content
    "explain", "describe", "research", "search", "find", "show",
    "write", "stop", "start", "continue", "check", "analyze",
    "help", "summarize", "compare", "papers", "article", "articles",
}

# ── Classifiers ───────────────────────────────────────────────────────────────

_Q_STARTERS: Set[str] = {
    "what", "why", "how", "when", "where", "who", "which", "whose",
    "is", "are", "do", "does", "did", "will", "would", "could", "should",
    "can", "have", "has", "had",
}

_GREET_WORDS: Set[str] = {
    "hi", "hey", "hello", "yo", "sup", "howdy", "hiya",
    "morning", "afternoon", "evening",
}

_COMMAND_VERBS: Set[str] = {
    "research", "look", "find", "search", "explain", "describe",
    "show", "read", "write", "stop", "start", "continue", "check",
    "analyze", "help", "run", "list", "summarize", "compare",
}

_OPINION_PHRASES: List[str] = [
    "what do you think", "what's your", "your opinion", "your take",
    "do you think", "do you believe", "do you feel", "you agree",
    "what would you", "how do you feel",
]

_STATUS_PHRASES: List[str] = [
    "how are you", "how's it going", "how are things", "how's orrin",
    "what are you up to", "what are you working", "what have you been",
    "what's on your mind", "what are you thinking", "what's new",
    "been doing", "been up to", "what's going on",
]

_ABOUT_ORRIN_FRAGMENTS: List[str] = [
    "are you", "how are you", "what are you", "what do you",
    "how do you", "do you ", "you think", "you feel", "you working",
    "you been", "you doing", "you thinking", "orrin",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _words(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def extract_topics(text: str) -> List[str]:
    """Return meaningful keyword tokens from text, longest-first."""
    raw = _words(text)
    seen: Set[str] = set()
    out: List[str] = []
    for w in raw:
        if len(w) > 3 and w not in _STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# Leading salutation ("hi", "hey there", "hello orrin,", "good morning") — stripped
# so a greeting prefix can't swallow a real question/request that follows it.
_GREETING_PREFIX_RE = re.compile(
    r"^\s*(?:good\s+(?:morning|afternoon|evening)|hi+|hey+|hello+|yo+|sup|howdy|hiya|greetings)"
    r"(?:\s+(?:there|orrin))?[\s,!.:;-]*",
    re.IGNORECASE,
)


def _classify_intent(text: str) -> Tuple[str, Optional[str]]:
    raw_lower = text.lower().strip()
    raw_first = raw_lower.split()[0] if raw_lower.split() else ""

    # Strip a leading greeting so we classify on what the user ACTUALLY wants.
    # "Hello Orrin, what have you been learning?" must read as a status question,
    # not a bare greeting (the old order let the greeting win and dropped the rest).
    body = _GREETING_PREFIX_RE.sub("", text).strip()
    had_greeting = (body.lower() != raw_lower) or (raw_first in _GREET_WORDS)

    lower = body.lower().strip()
    ws    = lower.split()
    first = ws[0] if ws else ""

    # Pure greeting: nothing substantive remained after the salutation
    # (not a question, doesn't open with a question word, and < 3 words).
    _substantive = (
        body.rstrip().endswith("?")
        or first in _Q_STARTERS
        or first in _COMMAND_VERBS
        or len(ws) >= 3
    )
    if had_greeting and not _substantive:
        return "greeting", None

    # Very short → ack (but only if not a question/command)
    if (len(ws) <= 3
            and not body.rstrip().endswith("?")
            and first not in _Q_STARTERS
            and first not in _COMMAND_VERBS):
        if had_greeting:
            return "greeting", None
        return "short_ack", None

    # Status check (comes before generic question so "how are you" isn't "question")
    for phrase in _STATUS_PHRASES:
        if phrase in lower:
            return "status_check", "status"

    # Opinion request
    for phrase in _OPINION_PHRASES:
        if phrase in lower:
            return "opinion_request", "opinion"

    # Information requests that look like commands ("tell me about X",
    # "explain X", "describe X") — treat as questions, not commands
    if any(lower.startswith(p) for p in (
        "tell me about", "tell me what", "tell me how",
        "explain ", "describe ", "walk me through",
    )):
        return "question", "open"

    # Question
    if body.rstrip().endswith("?") or first in _Q_STARTERS:
        if any(p in lower for p in ("what is", "what are", "who is",
                                     "when did", "how does", "where is",
                                     "how many", "how much")):
            return "question", "factual"
        return "question", "open"

    # Command
    if first in _COMMAND_VERBS:
        return "command", None

    # Emotional expression
    if body.rstrip().endswith("!") or any(
        w in lower for w in ("amazing", "wow", "interesting", "weird",
                              "strange", "great", "awful", "terrible",
                              "cool", "wild", "crazy", "love", "hate")
    ):
        return "emotional", None

    # Nothing substantive but we did greet → greeting; else a plain statement.
    if had_greeting and not ws:
        return "greeting", None
    return "statement", None


def _detect_tone(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("frustrated", "stuck", "broken", "annoying",
                                 "keeps", "won't", "doesn't work", "problem")):
        return "frustrated"
    if text.rstrip().endswith("!") or any(
        w in lower for w in ("amazing", "wow", "great", "love", "awesome",
                              "excited", "finally")
    ):
        return "excited"
    if any(w in lower for w in ("quickly", "urgent", "asap", "important",
                                 "need", "must", "critical")):
        return "urgent"
    if any(w in lower for w in ("lol", "haha", "heh", "funny", "joking",
                                 "kidding", "jk", "lmao")):
        return "playful"
    if "?" in text and len(text.split()) > 4:
        return "curious"
    return "casual"


def _about_orrin(text: str) -> bool:
    lower = text.lower()
    return any(frag in lower for frag in _ABOUT_ORRIN_FRAGMENTS)


def _about_goal(text: str) -> bool:
    lower = text.lower()
    return any(w in lower for w in (
        "working on", "goal", "progress", "project",
        "up to", "what you", "been doing",
    ))


# ── Public entry ──────────────────────────────────────────────────────────────

def _extract_key_terms(text: str) -> List[str]:
    """
    Extract the user's preferred vocabulary for lexical alignment
    (Pickering & Garrod 2004): multi-word phrases first, then distinctive
    single terms.  These are used in ask_back generation so Orrin mirrors
    the user's own words rather than substituting synonyms.
    """
    # Multi-word noun phrases: runs of capitalised words
    phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
    # Hyphenated compounds: step-by-step, long-term
    phrases += re.findall(r'\b[a-z]{3,}(?:-[a-z]{3,})+\b', text)
    # Quoted terms (user marking salience)
    phrases += re.findall(r'"([^"]{4,30})"', text)
    # Distinctive single tokens (long, not stopwords)
    singles = [
        w for w in re.findall(r'[a-zA-Z]{7,}', text.lower())
        if w not in _STOP
    ]
    # Deduplicate preserving order, cap at 4
    seen: Set[str] = set()
    out: List[str] = []
    for t in phrases + singles:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(t)
        if len(out) >= 4:
            break
    return out


_SHORT_CONTINUATIONS: Set[str] = {
    "yes", "yeah", "yep", "no", "nope", "ok", "okay", "sure", "right",
    "exactly", "agreed", "true", "false", "interesting", "really", "wow",
    "hm", "hmm", "huh", "tell me more", "go on", "continue", "keep going",
    "and?", "so?", "why?", "how?", "when?", "what?", "who?",
}


def parse_input(user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Stage 1 entry point.
    Returns a comprehension dict consumed by speech_memory and speech_planner.

    Topic carryover: short continuation phrases ("yes", "tell me more", "go on")
    yield no extractable topics, which causes the pipeline to default to expressing
    internal state rather than continuing the thread. When detected, we carry
    forward the previous turn's topics so retrieval stays on the same subject.
    """
    text = (user_input or "").strip()
    ctx  = context or {}

    if not text:
        return {
            "intent": "short_ack",
            "question_type": None,
            "topics": [],
            "tone": "casual",
            "about_orrin": False,
            "about_goal": False,
            "raw": "",
        }

    intent, question_type = _classify_intent(text)
    # Extract topics from the greeting-stripped text so "hello"/"orrin" don't
    # become topics and pull the memory search off the actual subject.
    topics = extract_topics(_GREETING_PREFIX_RE.sub("", text))

    # Topic carryover for short continuations — keep previous turn's thread alive
    if not topics or text.lower().strip(".?!") in _SHORT_CONTINUATIONS:
        prev = ctx.get("_last_speech_comprehension") or {}
        carried = prev.get("topics") or []
        if carried:
            topics = carried        # reuse previous topics
            # But mark intent as continuation so the planner can treat it as such
            if intent == "short_ack" and carried:
                intent = "statement"    # promote so pipeline doesn't skip it

    return {
        "intent":        intent,
        "question_type": question_type,
        "topics":        topics,
        "key_terms":     _extract_key_terms(text),   # user's preferred vocabulary
        "tone":          _detect_tone(text),
        "about_orrin":   _about_orrin(text),
        "about_goal":    _about_goal(text),
        "raw":           text,
    }
