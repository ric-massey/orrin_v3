# brain/utils/subject_terms.py
#
# The SUBJECT of a question or goal title, for symbolic matching (close-out
# scoring, prior-claims reuse, claims extraction, answer citation).
#
# Run 12 (DEMO_RUN_2026-08-19 §3): three private copies of this function each
# kept the question-template scaffolding ("What did I get WRONG or OVERSIMPLIFY
# about X?") as subject terms and matched by SUBSTRING. Every claims file shared
# did/get/wrong, so any relation "answered" any question (`get` ⊂ "together",
# `now` ⊂ "known") and every goal "built on" whichever claims file was newest.
# One shared definition here: scaffold words stopped, matching on whole tokens.
#
# Dependency-free on purpose: imported from both brain/ and the goals daemon.
from __future__ import annotations

import re
from typing import Iterable, List, Set

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Function words + the scaffolding of every question/title template Orrin mints
# (intrinsic_generators._deepening_question, epistemic_closeout.question_for,
# "Open question:"/"Answer:" wrappers, "Understand X more deeply" titles).
SCAFFOLD_STOP = frozenset({
    # function words
    "the", "and", "for", "with", "that", "this", "its", "are", "was", "were",
    "been", "being", "from", "about", "into", "onto", "than", "then", "there",
    "their", "they", "them", "these", "those", "which", "what", "how", "why",
    "when", "where", "who", "whom", "whose", "does", "did", "doing", "done",
    "has", "have", "had", "can", "could", "would", "should", "will", "shall",
    "may", "might", "must", "not", "but", "any", "all", "some", "most", "much",
    "many", "very", "just", "also", "own", "only", "even", "still", "yet",
    "you", "your", "our", "his", "her",
    # question / title scaffolding
    "get", "got", "wrong", "oversimplify", "oversimplified", "oversimplifying",
    "actually", "beyond", "mentions", "mention", "keep", "keeps", "seeing", "see",
    "now", "know", "knowing", "known", "said", "say", "before", "find", "found",
    "makes", "make", "true", "worth", "first", "look", "tends", "precede",
    "next", "concrete", "step", "right", "open", "question",
    "answer", "really", "understand", "understanding", "deeply", "deeper",
    "deep", "more", "obvious", "something", "new", "learn", "learned", "explained",
    "explain", "thing", "things", "way", "ways", "earlier", "notes", "missing",
})


def tokens(text: str) -> List[str]:
    """Lower-cased alphanumeric tokens, in order."""
    return _TOKEN_RE.findall(str(text or "").lower())


def subject_terms(text: str) -> List[str]:
    """The content words that name what `text` is about, in order, deduplicated.
    Scaffold and function words are dropped; tokens shorter than 3 chars too."""
    out: List[str] = []
    for w in tokens(text):
        if len(w) > 2 and w not in SCAFFOLD_STOP and w not in out:
            out.append(w)
    return out


def _forms(term: str) -> Set[str]:
    """A term plus its naive plural/singular partner, so 'system' meets 'systems'."""
    forms = {term}
    if term.endswith("ies") and len(term) > 4:
        forms.add(term[:-3] + "y")
    elif term.endswith("es") and len(term) > 4:
        forms.add(term[:-2])
    elif term.endswith("s") and len(term) > 3:
        forms.add(term[:-1])
    else:
        forms.update({term + "s", term + "es"})
    return forms


def matched_terms(terms: Iterable[str], text: str) -> List[str]:
    """The subset of `terms` that appear in `text` as WHOLE tokens (plural-
    tolerant). Never substring: 'get' does not match 'together'."""
    toks = set(tokens(text))
    return [t for t in terms if _forms(str(t).lower()) & toks]


def mentions(terms: Iterable[str], text: str) -> bool:
    return bool(matched_terms(terms, text))
