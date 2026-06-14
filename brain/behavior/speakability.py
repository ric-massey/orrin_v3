"""
brain/behavior/speakability.py

The single speakability invariant for everything Orrin says or writes to a
person. One list, one check — so the per-emitter filters that used to drift
(leave_note._SKIP_PREFIXES vs speech_pipeline._INTERNAL vs the speech_gate
suppression list — EXPRESSION_MEMBRANE_FIX_PLAN E7) collapse into a single
chokepoint that both the user-reply path (build_response / speech_pipeline) and
the expression door (express_to_user) import.

Rule: person-facing text is *composed* from felt meaning. Backend
representation — working-memory bookkeeping, symbolic/causal/rule tags,
telemetry markers, filesystem paths — must never reach a person verbatim. If
composed text still carries such a marker, that is a composer bug; the door
raises on it (assert_speakable) rather than shipping it.
"""
from __future__ import annotations

import re

# Internal bookkeeping markers that must never be quoted at a person. This is
# the union of every previously-scattered filter. Matched as a lowercase
# substring anywhere in the text.
INTERNAL_MARKERS = (
    "[chunk:", "[metacog", "[incubation", "[sym_", "[symbolic", "[rule",
    "[causal", "[done]", "[goal", "[subgoal", "[plan:", "[dream",
    "[identity", "[regulation", "[housekeeping", "[world_perception",
    "[note_written", "[clipboard", "[survey", "[question_answered",
    "[wikipedia]", "[rss:", "[metacog", "internal_telemetry",
    "✅", "🧠", "📝", "⚠️", "🌓",
)

# Any leading "[tag]" or "[tag:" is a system/telemetry line (the generic guard
# that the fixed prefix list kept missing — [regulation], [housekeeping/NORMAL]
# leaked through before). Also catches a bracket-tag embedded mid-string.
_BRACKET_TAG_RE = re.compile(r"\[[a-z_][a-z0-9_]*[:\]]", re.IGNORECASE)

# Filesystem-path leakage — composed speech should never contain a real path or
# a source-file reference. Matches absolute paths and bare module/file refs.
_PATH_RE = re.compile(
    r"(?:/[A-Za-z0-9_.\-]+){2,}"          # /a/b... absolute-ish paths
    r"|[A-Za-z0-9_./\-]+\.(?:py|json|txt|md|log)\b"  # a/b/file.py, file.json
)


def is_speakable(text: str) -> bool:
    """True if `text` is composed, person-facing language with no backend
    representation leaking through (telemetry tags, bracket markers, paths)."""
    if not text or not str(text).strip():
        return False
    low = str(text).lower()
    if any(m in low for m in INTERNAL_MARKERS):
        return False
    if _BRACKET_TAG_RE.search(text):
        return False
    if _PATH_RE.search(text):
        return False
    return True


def assert_speakable(text: str) -> str:
    """Return `text` if speakable; raise SpeakabilityError otherwise.

    The door calls this AFTER composition. A failure here means the composer
    copied backend representation instead of composing from meaning — a bug to
    fix at the source, not text to sanitize and ship.
    """
    if not is_speakable(text):
        raise SpeakabilityError(
            f"composed text is not speakable (backend representation leaked): "
            f"{str(text)[:160]!r}"
        )
    return text


def strip_internal(text: str) -> str:
    """Best-effort sanitizer for a *content kernel* (a Motive.seed), not for
    composed output. Removes bracket tags and collapses whitespace so a genuine
    meaning kernel can flow into composition reworded rather than copied. The
    door still asserts speakability on the final composed text.
    """
    if not text:
        return ""
    cleaned = _BRACKET_TAG_RE.sub(" ", str(text))
    # Drop any remaining standalone bracket groups (e.g. "[NORMAL]").
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)
    # Remove leaked paths.
    cleaned = _PATH_RE.sub(" ", cleaned)
    # Strip emoji/telemetry glyphs.
    for g in ("✅", "🧠", "📝", "⚠️", "🌓"):
        cleaned = cleaned.replace(g, " ")
    return re.sub(r"\s+", " ", cleaned).strip()


class SpeakabilityError(AssertionError):
    """Raised when composed person-facing text still carries backend representation."""
