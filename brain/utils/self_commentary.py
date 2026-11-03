"""Orrin's commentary on himself: entries that restate his current state in words.

Lifted out of control_signals/signal_patterns.py (2026-11-02) so memory can use the
same test. Appraisal skips these because keyword-detecting a sentence about a signal
re-fires that signal (the rumination loop that pinned impasse_signal). Long memory
skips them for Ric's principle — most memories should be about his world, not
himself: smoke life 3 promoted 186 working-memory summaries into a 429-row long
memory, every one of them shadow questions (13 canned prompts, 66 times), "Strongly
defined dominant emotion: X (0.NN)" readouts, and "I've been running hot and flat"
templates. The state they restate is kept where it belongs, in the affect state.
"""
from __future__ import annotations

from typing import Any

SELF_COMMENTARY_EVENT_TYPES = frozenset({
    "oscillation_detected", "affect_cause", "dominant_affect",
    "affect_analysis", "unexplained_affect_reflection",
    "metacog_pattern", "affective_reflection", "shadow_dialogue",
    "incubated_insight", "self_query",
    # Decision logs ("Chose: X — {weights:{…}}") embed signal names as
    # feature-weight keys, so keyword-detecting them spuriously fires those
    # signals. A choice's affect is already accounted for via the reward/bandit
    # channel, not by re-reading the log text.
    "choice",
})

# Machine-generated introspective markup. It rides inside ordinary "chunk"
# (conscious-stream) entries, so the event_type test alone can't catch it.
INTROSPECTIVE_MARKERS = (
    "[sym_dream", "[metacog", "[emotion/cause]", "[incubation insight]",
    "counterfactual:", "oscillation detected", "dominant affect", "dominant emotion",
    "shadow question",
    # Decision logs ("🧠 Chose: X — {…'multi-factor'…weights{…}}"). The weights
    # dict lists every signal name as a key, so keyword detection spuriously fires
    # whichever signals appear there. These ride inside plain "chunk" conscious-stream
    # entries too, so match on the log signature, not the event_type.
    "🧠 chose", "multi-factor",
)


def is_self_commentary_type(et: str) -> bool:
    return (
        et in SELF_COMMENTARY_EVENT_TYPES
        or "affect" in et            # affect_cause, dominant_affect, affective_reflection, affect_stagnation, …
        or "metacog" in et           # metacog_pattern, metacog_monitor, …
        or et.endswith("_reflection")
        or et.endswith("_dialogue")
    )


def has_introspective_markup(content: Any) -> bool:
    c = str(content or "").lower()
    return any(m in c for m in INTROSPECTIVE_MARKERS)


def is_self_commentary(entry: Any) -> bool:
    """True for a memory entry that restates Orrin's own state (by type or markup)."""
    if not isinstance(entry, dict):
        return False
    return (is_self_commentary_type(str(entry.get("event_type") or ""))
            or has_introspective_markup(entry.get("content")))
