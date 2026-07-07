# utils/text_sanity.py
# Shared text-hygiene predicates (Layer L1 — stdlib only).
#
# Memory corruption vector (BEHAVIOR_FIX_PLAN Phase 1 / audit §8): nested
# `[Chunk:` wrappers and byte-cap truncation artifacts re-entered memory as
# content, were chunked again, crystallized into symbolic rules, brooded on by
# rumination, and spoken aloud. These predicates are the single quarantine
# gate: anything that fails them may be stored as-is for forensics but must
# never be re-ingested as content (rule minting, analogy matching, rumination
# seeds, speech candidates).
from __future__ import annotations

import re

_CHUNK_HEADER_RE = re.compile(r"\[chunk\s*:", re.IGNORECASE)
# A word chopped mid-way by a byte cap, e.g. "...may need atte]" / "attenti…"
_MIDWORD_END_RE = re.compile(r"[A-Za-z]{12,}$")

_BRACKET_PAIRS = {"[": "]", "(": ")", "{": "}"}

_ELLIPSIS = "…"

_SENTENCE_END_RE = re.compile(r"[.!?…]")


def has_unbalanced_brackets(text: str) -> bool:
    """True when bracket nesting is broken (a truncation fingerprint)."""
    stack: list = []
    for ch in text:
        if ch in _BRACKET_PAIRS:
            stack.append(_BRACKET_PAIRS[ch])
        elif ch in _BRACKET_PAIRS.values():
            if not stack or stack.pop() != ch:
                return True
    return bool(stack)


def ends_mid_word(text: str) -> bool:
    """True when the text appears chopped mid-word (no terminal punctuation,
    ends in a long unbroken letter run — the byte-cap signature)."""
    t = text.rstrip()
    if not t or t.endswith((".", "!", "?", _ELLIPSIS, '"', "'", ")", "]")):
        return False
    return bool(_MIDWORD_END_RE.search(t))


def is_corrupt_text(text) -> bool:
    """
    Quarantine predicate: True when the text shows memory-corruption
    fingerprints and must not be re-ingested as content.
    """
    if not isinstance(text, str):
        return True
    t = text.strip()
    if not t:
        return True
    if _CHUNK_HEADER_RE.search(t):
        return True
    if has_unbalanced_brackets(t):
        return True
    if ends_mid_word(t):
        return True
    return False


def truncate_clean(text: str, limit: int) -> str:
    """
    Cap ``text`` at ``limit`` chars cutting at the last sentence boundary
    (falling back to the last whitespace), and append a clean ellipsis.
    Truncation artifacts must not be re-ingestible as content — never cut
    mid-word, never leave brackets dangling from the cut itself, and never
    slice through an [EXTERNAL/UNTRUSTED …] quarantine wrapper (sliced tags
    like "[EXTERNAL/UNTRUSTED source=https more deeply" re-entered working
    memory, long memory, and a goal title — FINDINGS 2026-06-12 data sweep §9).
    """
    if not isinstance(text, str) or len(text) <= limit:
        return text
    m = _Q_OPEN_RE.search(text)
    if m:
        # Truncate the quoted content, then rebuild a BALANCED wrapper so the
        # trust marker survives the cut intact.
        open_tag, close_tag = m.group(0), " [/EXTERNAL]"
        inner = _Q_STRIP_RE.sub(" ", text).strip()
        budget = limit - len(open_tag) - len(close_tag) - 1
        if budget < 16:
            # No room for a balanced wrapper at this limit. Fail closed: keep a
            # marker, drop the content, rather than emit a sliced tag.
            return "[external content]"[:limit]
        return f"{open_tag} {_truncate_plain(inner, budget)}{close_tag}"
    return _truncate_plain(text, limit)


# Same patterns as utils.content_quarantine, duplicated here to keep this
# module L1/stdlib-only with no intra-utils import at call time.
_Q_OPEN_RE = re.compile(r"\[EXTERNAL/UNTRUSTED\s+source=[^\]]*\]")
_Q_STRIP_RE = re.compile(r"\[EXTERNAL/UNTRUSTED\s+source=[^\]]*\]\s*|\s*\[/EXTERNAL\]")


# ── F3 (2026-07-05 findings): signal-to-markup gate for external intake ────────
# The 07-05 run stored 2,000 chars of raw Twitter CSS (`:host{display:inline-
# block…`) as a long memory. Tag stripping misses style rules that ride inside
# templates/shadow DOM and inline JSON; these predicates catch the residue so
# markup soup never becomes a memory.

# A CSS/JS rule body: `selector{prop:val;…}` — prose essentially never nests
# braces around semicolon-delimited runs.
_CSS_RULE_RE = re.compile(r"[#.@:\w\s,>\[\]\"'=^$*()~-]{0,80}\{[^{}]{0,800}\}")
# Minified-code fingerprints that survive rule removal.
_CODE_RESIDUE_RE = re.compile(
    r"(?:!important|;\s*[\w-]+\s*:|function\s*\(|=>|var\(--|@media\b|@font-face\b)"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def strip_markup_noise(text: str) -> str:
    """Remove CSS/JS rule soup that survives HTML tag stripping. Repeated passes
    handle nested rules flattened by the tag stripper; whitespace is squeezed."""
    t = str(text or "")
    for _ in range(5):
        t2 = _CSS_RULE_RE.sub(" ", t)
        if t2 == t:
            break
        t = t2
    t = _CODE_RESIDUE_RE.sub(" ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def prose_ratio(text: str) -> float:
    """Fraction of non-space characters that belong to natural-language words.
    English prose scores ~0.8+; stylesheet/script/JSON residue falls well below
    0.5. Empty text scores 0.0."""
    t = str(text or "")
    dense = len(re.sub(r"\s+", "", t))
    if not dense:
        return 0.0
    word_chars = sum(len(m.group(0)) for m in _WORD_RE.finditer(t))
    return word_chars / dense


def _truncate_plain(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit]
    # Prefer the last sentence end within the cap.
    last_sentence = max((m.end() for m in _SENTENCE_END_RE.finditer(head)), default=0)
    if last_sentence >= limit // 2:
        return head[:last_sentence].rstrip()
    # Otherwise cut at the last whitespace and mark the elision.
    cut = head.rfind(" ")
    if cut <= 0:
        cut = limit - 1
    return head[:cut].rstrip() + _ELLIPSIS
