# think/speech_memory.py
#
# Stage 2 — Memory Retrieval
#
# Given a list of topic tokens from Stage 1, searches long_memory and
# working_memory for the most relevant entries.
#
# Scoring (all factors multiply together):
#   overlap_score  — fraction of topic tokens that appear in the entry
#   recency        — exponential decay, half-life 48 h (recent = higher)
#   importance     — entry.importance / 4.0, capped at 2.0
#   source_bonus   — 1.5x for [research]/[read] entries (richer content)
#
# Entries below a minimum relevance threshold are excluded unless no
# other results exist, in which case the most recent entries are returned
# as a fallback so the builder always has something to work with.
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from brain.utils.json_utils import load_json
from brain.paths import LONG_MEMORY_FILE, WORKING_MEMORY_FILE

# Shared stopword set (mirrors speech_comprehension — kept local to avoid import)
_STOP: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "i", "me", "my", "we", "our",
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
    "right", "still", "also", "actually", "well", "yes", "yeah", "okay", "ok",
}

_MIN_RELEVANCE = 0.08   # entries below this score are excluded
_LM_WINDOW     = 300    # look at most recent N long-memory entries
_WM_WINDOW     = 40     # look at most recent N working-memory entries


# ── Tokenisation ──────────────────────────────────────────────────────────────

def _tokenise(text: str) -> Set[str]:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOP}


# ── Excerpt extraction ────────────────────────────────────────────────────────

_PREFIX_RE = re.compile(
    r"^\[(?:research|read|goal|thought|world_perception)\]\s*"
    r"(?:[^:]{0,80}:\s*)?"            # optional "topic: " or "Wikipedia/Title: "
    r"(?:Wikipedia/[^:]{0,60}:\s*)?", # optional second "Wikipedia/Title: "
    re.IGNORECASE,
)
_EMOJI_RE  = re.compile(r"^[✅🧠⚠️❌📝🔁🌍💭🎯🔍]+\s*")
_SOURCE_RE = re.compile(r"\s*\[source:[^\]]+\]", re.IGNORECASE)


def extract_excerpt(entry: Dict, max_len: int = 200) -> str:
    """
    Return clean readable text from a memory entry's content field.
    Strips internal prefixes like [research] topic: Wikipedia/Title: …
    """
    raw = str(entry.get("content", "")).strip()
    raw = _EMOJI_RE.sub("", raw)
    raw = _PREFIX_RE.sub("", raw)
    raw = _SOURCE_RE.sub("", raw)
    raw = " ".join(raw.split())

    if len(raw) <= max_len:
        return raw

    # Try to break at a sentence boundary
    for punct in (".", "!", "?", ";"):
        idx = raw.rfind(punct, 0, max_len)
        if idx > max_len * 0.5:
            return raw[: idx + 1]

    # Word boundary fallback
    idx = raw.rfind(" ", 0, max_len)
    return (raw[:idx] + "…") if idx > 0 else raw[:max_len]


# ── Scoring ───────────────────────────────────────────────────────────────────

def _age_hours(entry: Dict) -> float:
    ts = entry.get("timestamp", "")
    try:
        dt  = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() / 3600.0
    except (ValueError, TypeError, AttributeError):  # intentional: unparseable timestamp → one-week default
        return 168.0  # default: one week old


def _score(
    entry:         Dict,
    topic_tokens:  Set[str],
    dominant_emo:  str = "",
) -> float:
    """
    Score a memory entry for relevance to the current query.

    Bower (1981) mood-congruent recall: emotional state primes retrieval
    of memories with matching valence.  We apply a modest 20% boost when
    the entry's stored emotion matches the current dominant affect — enough
    to surface emotionally resonant content without overriding topical match.
    """
    if not topic_tokens:
        return 0.0

    content = str(entry.get("content", ""))
    overlap = len(topic_tokens & _tokenise(content))
    if overlap == 0:
        return 0.0

    overlap_score = overlap / len(topic_tokens)
    recency       = math.exp(-_age_hours(entry) / 48.0)   # half-life 48 h
    importance    = min(2.0, float(entry.get("importance", 1) or 1) / 4.0)
    source_bonus  = 1.5 if any(
        tag in content[:25] for tag in ("[research]", "[read]")
    ) else 1.0

    base = overlap_score * (0.4 + 0.6 * recency) * (0.6 + 0.4 * importance) * source_bonus

    # Mood-congruent recall bonus
    entry_emo = str(entry.get("emotion") or "").lower()
    if dominant_emo and entry_emo and entry_emo == dominant_emo:
        base *= 1.20

    return base


# ── Public entry ──────────────────────────────────────────────────────────────

# Internal bookkeeping / instrumentation entries that must never become the
# content of something Orrin says to the user. His memory is full of these; a
# reply grounded in them reads as machine noise ("[Chunk: [Chunk:…", "Health
# summary: cpu=0.00", raw "[input/question]" tags). Only genuine content
# (research findings, observations, real thoughts) should surface in speech.
_NOISE_PREFIXES = (
    "[chunk:", "[metacog", "[input/", "[pattern]", "[wonder]", "[done]",
    "[goal pursuit]", "[goal_", "[subgoal_adapt]", "[regulation]",
    "[behavioral_adapt]", "[energy]", "[temporal", "[state_processor]",
    "[working_memory]", "[symbolic]", "[env", "[body_sense]", "[identity",
    "[attention", "[inhibition]", "[reflection/audit]", "[allostatic",
    "spoke:", "chose:", "health summary", "🧠", "🌓", "⏳", "🔄",
)


def _is_internal_noise(content: str) -> bool:
    """True if this memory is internal instrumentation, not sayable content."""
    c = (content or "").strip().lower()
    if not c:
        return True
    # Any internal bracket-tag ([chunk:, [metacog/, [world_model], [concept], …),
    # description/attribute soup, or vitals are instrumentation — never sayable.
    if "[chunk" in c or "cpu=" in c or "description=" in c:
        return True
    if re.search(r"\[[a-z_]{2,}[\]/ ]", c):   # [word], [word/, [word  → internal tag
        return True
    if re.search(r"\b[a-z_]+=\w", c):          # key=value attribute soup
        return True
    return c.startswith(_NOISE_PREFIXES)


def recent_findings(n: int = 2) -> List[str]:
    """
    Most recent GENUINE things Orrin learned — research/read findings and dream
    insights — as clean excerpts. Used to answer "what have you been up to /
    learning?" by recency, since those questions rarely topic-match the subject
    of what he actually studied.
    """
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    out: List[str] = []
    for entry in reversed(long_mem[-150:]):
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content", ""))
        if _is_internal_noise(content):
            continue
        etype = str(entry.get("event_type", "")).lower()
        low = content.strip().lower()
        is_finding = (
            etype in ("world_perception", "dream_insight")
            or low.startswith(("[research]", "[read]"))
            or "research" in etype
        )
        if not is_finding:
            continue
        ex = extract_excerpt(entry)
        if len(ex) >= 20:
            out.append(ex)
        if len(out) >= n:
            break
    return out


def retrieve_relevant(
    topics:          List[str],
    n:               int  = 5,
    include_working: bool = True,
    affect_state:    Optional[Dict] = None,
) -> List[Dict]:
    """
    Stage 2 entry point.

    topics         — keyword list from Stage 1 comprehension
    n              — max entries to return
    include_working — also search working memory

    Each returned entry has two extra keys injected:
      _relevance  — float score
      _excerpt    — clean readable string ready for template slot filling
    """
    topic_tokens: Set[str] = {w for w in topics if len(w) > 3}

    # Extract dominant emotion for mood-congruent recall (Bower 1981)
    dominant_emo = ""
    if affect_state:
        core = affect_state.get("core_signals") or affect_state
        if isinstance(core, dict):
            candidates_emo = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
            if candidates_emo:
                dominant_emo = max(candidates_emo, key=lambda k: candidates_emo[k])

    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    work_mem = (load_json(WORKING_MEMORY_FILE, default_type=list) or []) if include_working else []

    # Cap windows for performance — most recent entries are most useful
    candidates = long_mem[-_LM_WINDOW:] + work_mem[-_WM_WINDOW:]

    scored: List[Dict] = []
    seen_ids: Set[str] = set()

    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id", "")
        if eid and eid in seen_ids:
            continue
        if eid:
            seen_ids.add(eid)

        if _is_internal_noise(entry.get("content", "")):
            continue

        s = _score(entry, topic_tokens, dominant_emo)
        if s >= _MIN_RELEVANCE:
            enriched = dict(entry)
            enriched["_relevance"] = round(s, 4)
            enriched["_excerpt"]   = extract_excerpt(entry)
            scored.append(enriched)

    scored.sort(key=lambda e: e["_relevance"], reverse=True)

    # If too few relevant results, pad with the most recent non-empty entries
    if len(scored) < 2 and candidates:
        recent_ids = {e.get("id") for e in scored}
        for entry in reversed(candidates[-20:]):
            if not isinstance(entry, dict):
                continue
            if entry.get("id") in recent_ids:
                continue
            if _is_internal_noise(entry.get("content", "")):
                continue
            excerpt = extract_excerpt(entry)
            if len(excerpt) < 20:
                continue
            enriched = dict(entry)
            enriched["_relevance"] = 0.0
            enriched["_excerpt"]   = excerpt
            scored.append(enriched)
            if len(scored) >= 2:
                break

    return scored[:n]
