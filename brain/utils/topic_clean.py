# brain/utils/topic_clean.py
#
# B4 (Run 13 master plan): one cleaner for page chrome and fragment topics,
# shared by the research claims extractor (goals/handlers/research_claims.py),
# the knowledge-graph concept gate (knowledge_graph_extract._validate_candidate)
# and every generator that turns text into a research topic.
#
# Run 13's knowledge graph held 26 concepts and the junk among them came from
# three sources, each a test case in tests/brain/test_b4_topic_clean.py:
#   fragments  — the lazy definition regex grabbed words before "X is a Y":
#                "world a world", "but what if there", "round the sun",
#                "this game-playing ai"
#   chrome     — page furniture read as a title: "See More Results Suggestions",
#                "Is AI the End of Math As We Know It? | Quanta Magazine"
#   own titles — his aspiration "Make things" researched as a world topic
# and "the free encyclopedia This article is about…" was scored as an answer.
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Optional, Tuple

# Navboxes end in "v t e" and portal/category links; Wikipedia's lead starts after
# "the free encyclopedia". The sentence that matters follows the last marker.
_CHROME_SPLIT_RE = re.compile(
    r"\bv\s+t\s+e\b|\bCategory\b|\bportal\b|\bthe free encyclopedia\b", re.IGNORECASE)
# Residue that is never prose: infobox rows and disambiguation hatnotes.
_INFOBOX_RE = re.compile(
    r"\b(?:Preceded by|Followed by|Website|ISBN|Retrieved|Archived|"
    r"Jump to navigation|edit source|This article is about|For other uses|"
    r"redirects here)\b", re.IGNORECASE)

# Page furniture that reads like a title.
_CHROME_TOPIC_RE = re.compile(
    r"\|"
    r"|\bsee more\b|\bsearch results\b|\bsuggestions\b|\bsign (?:in|up)\b|\blog in\b"
    r"|\bskip to\b|\bmain menu\b|\bcookie\b|\bsubscribe\b|\bnewsletter\b"
    r"|\bfree encyclopedia\b|\bthis article\b|\bwikipedia\b",
    re.IGNORECASE)

# A definition's subject never starts with a conjunction, a demonstrative or a
# preposition: those mark a regex match that began mid-clause.
_LEAD_FRAGMENT = frozenset({
    "but", "and", "or", "nor", "so", "yet", "if", "then", "when", "while",
    "because", "although", "though", "unless", "whether", "than",
    "this", "that", "these", "those", "it", "its", "there", "here",
    "which", "who", "whom", "whose", "what", "where",
    "round", "around", "about", "of", "to", "in", "on", "at", "by", "for",
    "from", "with", "into", "onto", "over", "under", "as", "like",
})

# Strict mode (topics lifted from running prose): a determiner-led phrase is a
# topic only when it fronts a proper name ("The Daily Stoic"), not a common
# noun ("The field", "One major obstacle", "the other curves").
_DETERMINERS = frozenset({
    "the", "a", "an", "one", "some", "many", "most", "other", "such", "each",
    "every", "another", "his", "her", "their", "our", "my", "your", "several"})

_MAX_WORDS = 6
_MAX_CHARS = 60


def strip_chrome(sentence: str) -> str:
    """The prose after the last navigation marker; '' for infobox residue."""
    s = _CHROME_SPLIT_RE.split(str(sentence or ""))[-1].strip(" .,;:-")
    return "" if _INFOBOX_RE.search(s) else s


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s-]", " ", str(s or "").lower()).split())


def is_junk_topic(name: str, own: Iterable[str] = (), *, strict: bool = False) -> bool:
    """True when `name` is not a usable world topic: page chrome, a clause
    fragment, a repeated-word splice, or one of his own goal/aspiration titles.
    `strict` also rejects determiner-led common-noun phrases."""
    raw = str(name or "").strip()
    if not raw or len(raw) > _MAX_CHARS:
        return True
    if _CHROME_TOPIC_RE.search(raw) or _INFOBOX_RE.search(raw):
        return True
    words = _norm(raw).split()
    if not words or len(words) > _MAX_WORDS:
        return True
    if words[0] in _LEAD_FRAGMENT:
        return True
    if strict and words[0] in _DETERMINERS:
        rest = raw.split()[1:]
        if not rest or not all(w[:1].isupper() for w in rest):
            return True
    # "world a world": the same content word twice is a splice across sentences.
    content = [w for w in words if len(w) > 2]
    if len(content) != len(set(content)):
        return True
    key = " ".join(words)
    for t in own:
        tk = _norm(t)
        if tk and (key == tk or tk.startswith(key + " ")):
            return True
    return False


def clean_topic(name: str, own: Iterable[str] = (), *, strict: bool = False) -> Optional[str]:
    """`name` stripped of chrome and surrounding punctuation, or None if junk."""
    s = strip_chrome(name).strip(" .,;:'\"-")
    s = " ".join(s.split())
    return None if is_junk_topic(s, own, strict=strict) else s


@lru_cache(maxsize=1)
def own_titles() -> Tuple[str, ...]:
    """His aspiration titles, short form included ("Make things" for
    "Make things — produce work that didn't exist before")."""
    out: list = []
    try:
        from brain.cognition.intrinsic_objectives import _ASPIRATIONS as ASPIRATIONS
        for row in ASPIRATIONS:
            title = str(row[0] if isinstance(row, (tuple, list)) else row)
            out.append(title)
            out.append(title.split("—")[0].strip())
    except Exception:  # intentional: aspirations unavailable → only chrome/fragment checks
        pass
    return tuple(out)
