# brain/cognition/quality_standard/originality.py
#
# A DETERMINISTIC VETO on exemplar promotion — NOT a definition of "good".
#
# The promotion criterion lives elsewhere (downstream credit in proposer.py + the
# quality predicate in gate.py). This module answers one narrow, genuinely
# deterministic question: *how much of this artifact is copied from its sources
# rather than authored?* Copy-fraction is exactly measurable; quality is not.
# So this is used only as a veto — a credited, predicate-passing artifact that is
# mostly other people's verbatim words is held back from AUTO-canonisation and
# routed to a human, never silently promoted.
#
# WHY THIS EXISTS. Run 9 (2026-07-17, symbolic-only) promoted its first three
# exemplars ever; one was ~90% a pasted PLOS abstract, because the research
# handler's OFFLINE fallback stitches verbatim source excerpts into a memo when
# no LLM is available (goals/handlers/research.py `_offline_fallback_memo`). The
# quality standard's golden set only grows and only loosens by human sign-off
# (the ratchet), so canonising a scrape would permanently define "good work" as
# scrape-quality — a Goodhart seed in the one store designed to resist Goodhart.
# Turning the LLM on does NOT fix this: an LLM that paraphrases the same abstract
# still gets promoted (a *worse* contamination — borrowed competence graded as
# Orrin's own). The fix is mode-independent and needs no intelligence: measure
# copying directly, from material already captured next to the artifact.
#
# WHAT IS AND ISN'T CLAIMED. This can establish "this text was copied too
# closely." It cannot establish "this is good work." It is one veto among the
# real promotion criteria, not a replacement for them.
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from brain import paths
from brain.utils.failure_counter import record_failure

# The exact fingerprint the offline research fallback stamps on its own output
# (`_offline_fallback_memo`). A definitive self-declaration that the memo is
# stitched source excerpts, not synthesis.
_OFFLINE_STITCH_MARK = "Offline synthesis fallback"

# Provenance self-declaration in a memo's footer (web_research._write_research_memo
# stamps `---\nsource: <source>\n`). `fetch_and_read` means the body is a raw
# fetched web page — external text dumped as a "memo", never authored synthesis —
# so it is the strongest, cleanest scrape signal available: the artifact declares
# its own provenance. This is the case a quote/verbatim check misses, because a
# raw dump carries no quoting markup and often has no separately-captured sources
# to diff against (it was fetched inline). Provenance beats heuristics.
_RAW_FETCH_SOURCES = ("fetch_and_read",)
_SOURCE_FOOTER_RE = re.compile(r"^source:\s*(\S+)", re.MULTILINE)
_READ_FROM_RE = re.compile(r"\(read from:\s*https?://", re.IGNORECASE)

# Word-level shingle length for verbatim-overlap detection. Long enough that
# incidental overlap between independent prose is rare; short enough to catch a
# copied sentence or clause.
_SHINGLE_N = 8

# Veto thresholds. Each names a deterministic property, not a quality judgment.
_MAX_QUOTE_RATIO = 0.50      # ≥ half the memo is other people's verbatim words
_MAX_VERBATIM_RATIO = 0.50   # the AUTHORED prose is itself majority-copied from sources
_MIN_ORIGINAL_CHARS = 200    # below this there is essentially no synthesis to canonise

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_BLOCKQUOTE_RE = re.compile(r"^\s*>.*$", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")


@dataclass
class CopyReport:
    """Deterministic measurements of how derivative an artifact is. Every field is
    a fact about the text/sources, not a verdict — `is_derivative` turns these into
    the veto decision so the thresholds live in exactly one place."""
    quote_ratio: float = 0.0
    verbatim_ratio: float = 0.0
    offline_stitch: bool = False
    raw_fetch: bool = False
    provenance: Optional[str] = None
    original_prose_chars: int = 0
    sources_found: int = 0
    reasons: List[str] = field(default_factory=list)


def _strip_quoted(text: str) -> str:
    """Return the text with fenced code blocks and markdown blockquotes removed —
    i.e. the part the author actually wrote, not the part they quoted."""
    without_fences = _FENCE_RE.sub("", text or "")
    without_quotes = _BLOCKQUOTE_RE.sub("", without_fences)
    return without_quotes


def _quoted_char_count(text: str) -> int:
    fenced = sum(len(m.group(0)) for m in _FENCE_RE.finditer(text or ""))
    quoted_lines = sum(len(m.group(0)) for m in _BLOCKQUOTE_RE.finditer(text or ""))
    return fenced + quoted_lines


def _shingles(text: str, n: int = _SHINGLE_N) -> set:
    words = _WORD_RE.findall((text or "").lower())
    if len(words) < n:
        return set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _load_sources(goal_id: Optional[str]) -> str:
    """Concatenate the source documents captured alongside a research artifact
    (doc_*.txt in the goal's daemon artifact dir). Fail-open: any resolution
    problem yields an empty corpus, so ABSENCE of sources can never trigger the
    veto — only their PRESENCE with high overlap can. This is why a filing-mess
    (the memo landing under a different goal id than its sources) degrades to
    'no verbatim signal', never to a false positive."""
    if not goal_id:
        return ""
    try:
        art_dir = paths.GOALS_DIR / "artifacts" / goal_id
        if not art_dir.is_dir():
            return ""
        parts: List[str] = []
        for p in sorted(art_dir.glob("doc_*.txt")):
            try:
                parts.append(p.read_text(encoding="utf-8"))
            except OSError:
                continue
        return "\n".join(parts)
    except Exception as exc:  # never let source-loading block promotion
        record_failure("quality_standard.originality._load_sources", exc)
        return ""


def analyze(text: str, *, goal_id: Optional[str] = None) -> CopyReport:
    """Measure how derivative `text` is. Pure measurement — no thresholds applied."""
    rep = CopyReport()
    if not text:
        return rep

    rep.offline_stitch = _OFFLINE_STITCH_MARK in text
    if rep.offline_stitch:
        rep.reasons.append("offline_stitch_header")

    # Provenance footer: the memo self-declares where its body came from.
    m = _SOURCE_FOOTER_RE.search(text)
    if m:
        rep.provenance = m.group(1)
    rep.raw_fetch = (rep.provenance in _RAW_FETCH_SOURCES) or bool(_READ_FROM_RE.search(text))
    if rep.raw_fetch:
        rep.reasons.append("raw_fetch_provenance")

    total_chars = len(text)
    quoted = _quoted_char_count(text)
    rep.quote_ratio = (quoted / total_chars) if total_chars else 0.0

    # Original prose = authored words only (markdown punctuation/headers excluded),
    # so a memo that is all section headers around quoted blocks scores near zero.
    authored = _strip_quoted(text)
    rep.original_prose_chars = sum(len(w) for w in _WORD_RE.findall(authored))

    sources = _load_sources(goal_id)
    if sources:
        rep.sources_found = 1
        authored_shingles = _shingles(authored)
        if authored_shingles:
            source_shingles = _shingles(sources)
            overlap = len(authored_shingles & source_shingles)
            rep.verbatim_ratio = overlap / len(authored_shingles)

    return rep


def is_derivative(report: CopyReport) -> tuple[bool, str]:
    """Turn measurements into the veto decision. Returns (derivative, reason).
    A True here does not mean 'bad' — it means 'too copied to AUTO-canonise as a
    standard of authored work; a human must decide.'"""
    if report.raw_fetch:
        return True, "raw_fetch_dump"
    if report.offline_stitch:
        return True, "offline_synthesis_stitch"
    if report.quote_ratio >= _MAX_QUOTE_RATIO:
        return True, f"quoted_material_{report.quote_ratio:.0%}"
    if report.original_prose_chars < _MIN_ORIGINAL_CHARS:
        return True, f"insufficient_original_prose_{report.original_prose_chars}c"
    if report.sources_found and report.verbatim_ratio >= _MAX_VERBATIM_RATIO:
        return True, f"verbatim_from_sources_{report.verbatim_ratio:.0%}"
    return False, "authored"


def check(text: str, *, goal_id: Optional[str] = None) -> tuple[bool, str, CopyReport]:
    """Convenience: analyze + decide in one call. Returns (derivative, reason, report)."""
    rep = analyze(text, goal_id=goal_id)
    derivative, reason = is_derivative(rep)
    return derivative, reason, rep
