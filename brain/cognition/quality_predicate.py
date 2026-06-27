# brain/cognition/quality_predicate.py
#
# THE SHARED REAL-CONTENT / QUALITY PREDICATE (T0.5).
#
# The single "is this real work?" check. Every production guarantee rests on it —
# goal closure (T1.1 `artifact_satisfied`), the forced-production test (T1.P), the
# closure-run throughput floor (T1.G), and note bodies (T2.4) all call THIS, so
# there is ONE definition of "real, not slop", not four that drift apart.
#
# DESIGN (from the Core Architecture master plan, T0.5):
#   * Layered. Cheap NEGATIVE gates first (reject known slop shapes by their
#     structure), then POSITIVE grounding (content traceable to real inputs). A
#     negative gate is a fast, certain reject; grounding is the substantive bar.
#   * Calibrated, not heuristic-by-vibe. The regression test
#     (tests/brain/test_quality_predicate.py) runs a GOLDEN SET: exemplars Ric
#     authored — they *are* the standard — and anti-exemplars pulled from the
#     2026-06-23 run's on-disk slop (the ×56 grounded_parts-template note, the
#     s_*_ok.txt stubs, near-duplicates). The predicate MUST pass every exemplar
#     and reject every anti-exemplar; that test IS the operational definition of
#     "high quality."
#   * Anti-Goodhart. This is only a FLOOR (may / may-not close). Reward stays
#     graded on real downstream significance (the effect ledger), so there is no
#     single threshold to optimize against.
#   * Ratchets. Any slop that slips through becomes a new anti-exemplar fixture;
#     the bar only rises, never silently loosens.
#
# HONEST CEILING: no pure function equals "Platonic good." This guarantees (a) no
# *known* slop shape passes, (b) the predicate provably separates the good/bad set,
# (c) the bar only ratchets up — leaving a shrinking residual for human review.
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ── Tunables ──────────────────────────────────────────────────────────────────
_MIN_CHARS = 80              # below this, content is a stub
_MIN_DISTINCT_WORDS = 12     # below this, too little information to be real work
_SKELETON_TOKEN_FRAC = 0.55  # if this fraction of content-words are template
                             # placeholders, the body is a skeleton, not a finding
_SKELETON_PHRASE_MIN = 2     # ≥ this many verbatim skeleton phrases ⇒ skeleton

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
# A machine-log line like `snapshot_goals → goals_state_….jsonl (lines=0)` — the
# exact shape of the run's s_*_ok.txt stubs.
_MACHINE_LOG_RE = re.compile(r"^\S.*(→|->).*\(.*\)\s*$")

# Template PLACEHOLDER phrases — the literal `grounded_parts` skeletons the planner
# seeds (goal_comprehension.py / compose_section.py). When the body IS these,
# provenance reached the topic but was severed at the answer (the ×56 note).
_SKELETON_PHRASES = (
    "what i actually know about",
    "question or desired change",
    "relevant evidence",
    "reasoned conclusion",
    "observable consequence",
    "purpose and thesis",
    "substantive sections",
    "coherence review",
    "final manuscript",
    "purpose; evidence; implications",
)
# The bare placeholder tokens those phrases decompose into (minus stopwords).
_SKELETON_TOKENS = frozenset({
    "purpose", "evidence", "implications", "thesis", "outline", "sections",
    "coherence", "review", "manuscript", "question", "desired", "change",
    "relevant", "reasoned", "conclusion", "observable", "consequence",
    "actually", "know", "about", "component", "placeholder",
})
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "these",
    "those", "as", "at", "by", "from", "i", "my", "me", "we", "our", "you", "your",
    "he", "she", "they", "them", "his", "her", "their", "what", "which", "who",
    "how", "why", "when", "where", "into", "than", "then", "so", "if", "not",
})


@dataclass
class QualityVerdict:
    """The predicate's structured verdict. `ok` is the floor decision; `reason` is
    a short machine tag for telemetry/funnel; `score` is an informativeness hint
    that MUST NOT be used as credit (anti-Goodhart — credit lives in the effect
    ledger)."""
    ok: bool
    reason: str
    score: float = 0.0

    def __bool__(self) -> bool:  # so `if assess_quality(...):` reads naturally
        return self.ok


def _words(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _content_words(words: List[str]) -> List[str]:
    return [w for w in words if w not in _STOPWORDS]


def _evidence_text(goal: Optional[Dict[str, Any]]) -> str:
    """Pull the goal's REAL evidence (finding / recorded observations / source) —
    deliberately NOT its grounded_parts template — so grounding can be checked
    against actual inputs."""
    if not isinstance(goal, dict):
        return ""
    parts: List[str] = []
    for k in ("finding", "answer", "conclusion", "produced_content", "result", "evidence"):
        v = goal.get(k)
        if isinstance(v, str):
            parts.append(v)
    for row in (goal.get("recent_contributions") or [])[:5]:
        parts.append(str(row))
    for row in (goal.get("definition_of_done") or []):
        if isinstance(row, dict) and row.get("met") and row.get("evidence"):
            parts.append(str(row.get("evidence")))
    return " ".join(parts)


def _template_text(goal: Optional[Dict[str, Any]]) -> str:
    """The goal's own planning skeleton (grounded_parts + title) — the text a real
    finding must add tokens BEYOND."""
    if not isinstance(goal, dict):
        return " ".join(_SKELETON_PHRASES)
    parts = list(_SKELETON_PHRASES)
    parts += [str(p) for p in (goal.get("grounded_parts") or [])]
    parts.append(str(goal.get("title") or ""))
    return " ".join(parts)


def _open_question(goal: Optional[Dict[str, Any]]) -> str:
    """The definition-of-done criterion the work must declaratively resolve."""
    if not isinstance(goal, dict):
        return ""
    for row in (goal.get("definition_of_done") or []):
        if isinstance(row, dict) and not row.get("met"):
            return str(row.get("criterion") or "")
    return str(goal.get("title") or "")


def assess_quality(
    content: str,
    *,
    goal: Optional[Dict[str, Any]] = None,
    evidence: Optional[str] = None,
    prior_outputs: Optional[List[str]] = None,
) -> QualityVerdict:
    """Judge whether `content` is real work. Negative gates (stub, template
    skeleton, near-duplicate) always run; positive grounding + answers-its-own-
    question run when the goal's evidence/question is available. Returns a
    QualityVerdict (truthy when it passes)."""
    text = (content or "").strip()

    # ── Negative gate 1: stub / triviality ───────────────────────────────────
    if len(text) < _MIN_CHARS:
        return QualityVerdict(False, "stub:too_short")
    words = _words(text)
    distinct = set(words)
    if len(distinct) < _MIN_DISTINCT_WORDS:
        return QualityVerdict(False, "stub:low_information")
    if "\n" not in text and _MACHINE_LOG_RE.match(text):
        return QualityVerdict(False, "stub:machine_log")

    cwords = _content_words(words)

    # ── Negative gate 2: template skeleton ───────────────────────────────────
    low = text.lower()
    phrase_hits = sum(1 for ph in _SKELETON_PHRASES if ph in low)
    skel_frac = (sum(1 for w in cwords if w in _SKELETON_TOKENS) / len(cwords)) if cwords else 0.0
    looks_templated = phrase_hits >= _SKELETON_PHRASE_MIN or skel_frac >= _SKELETON_TOKEN_FRAC

    # Grounding: content tokens drawn from REAL evidence, absent from the template.
    ev_text = evidence if evidence is not None else _evidence_text(goal)
    tmpl_tokens = set(_words(_template_text(goal)))
    ev_tokens = set(_content_words(_words(ev_text))) - _SKELETON_TOKENS
    grounded = [w for w in cwords if w in ev_tokens and w not in tmpl_tokens]
    has_evidence_input = bool(ev_tokens)

    if looks_templated and not grounded:
        return QualityVerdict(False, "template_skeleton")

    # ── Negative gate 3: near-duplicate of prior output ──────────────────────
    if prior_outputs:
        for prev in prior_outputs:
            if _too_similar(distinct, set(_words(prev))):
                return QualityVerdict(False, "near_duplicate")

    # ── Positive gate: grounding (only when we actually have evidence to check) ─
    if has_evidence_input and not grounded:
        return QualityVerdict(False, "ungrounded")

    # ── Positive gate: answers its own question (not a restatement) ───────────
    question = _open_question(goal)
    if question:
        q_tokens = set(_content_words(_words(question)))
        novel = [w for w in cwords if w not in q_tokens and w not in _SKELETON_TOKENS]
        # A declarative resolution adds substantive tokens beyond the question
        # itself; a body that is just the question reworded does not.
        if q_tokens and len(set(novel)) < max(3, len(q_tokens) // 2):
            return QualityVerdict(False, "restates_question")

    # Informativeness hint (NOT credit): distinct content words + grounding depth.
    score = min(1.0, (len(set(cwords)) / 60.0) + 0.1 * min(len(set(grounded)), 5))
    return QualityVerdict(True, "ok", round(score, 3))


def is_real_work(content: str, **kwargs: Any) -> bool:
    """Boolean convenience wrapper around assess_quality (the floor decision)."""
    return assess_quality(content, **kwargs).ok


def _too_similar(a: set, b: set, *, jaccard: float = 0.85) -> bool:
    """Jaccard near-duplicate test on distinct word sets."""
    if not a or not b:
        return False
    inter = len(a & b)
    union = len(a | b)
    return union > 0 and (inter / union) >= jaccard


def assess_artifact_file(path: str, *, goal: Optional[Dict[str, Any]] = None) -> QualityVerdict:
    """Read a produced artifact file and judge its CONTENT (used by
    artifact_satisfied to close the file-existence loophole). A missing/unreadable
    file is not real work."""
    try:
        from pathlib import Path
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return QualityVerdict(False, "unreadable")
    return assess_quality(text, goal=goal)
