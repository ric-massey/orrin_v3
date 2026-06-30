# Membrane-as-law (Grounded Cognition plan, Phase 1A / invariant #2).
#
# "Nothing internal becomes perceivable content except as a felt translation" —
# enforced at the chokepoints BY CONSTRUCTION, not by remembering to call a
# function. These tests drive the emitters that turn internal signals into
# perceivable content and assert the engineering identifier never survives into
# the content string, while the machine key rides in a STRUCTURED field that
# consumers read (the decouple that kills the parse-coupling class).
#
# Note on scope: bare English words that happen to also be signal keys
# (motivation, connection, dread, confidence) are legitimate FELT vocabulary and
# may appear — a mind feels "motivation". The leak this guards is the
# ENGINEERING-shaped identifier: underscored keys (impasse_signal) and internal
# markers ([metacog, affective_regulation, *_signal). See
# test_felt_lexicon_membrane.py for the same stance on felt_label itself.
from __future__ import annotations

import re

from brain.utils.felt_lexicon import _SIGNAL_KEYS, _INTERNAL_MARKERS

# Engineering-shaped identifiers only: underscored signal keys + internal markers.
# (Bare English mood words are allowed felt vocabulary.)
_ENG_KEYS = {k for k in _SIGNAL_KEYS if "_" in k}
_WORD = re.compile(r"[a-z_][a-z0-9_]+")


def _has_engineering_identifier(text: str) -> bool:
    low = str(text or "").lower()
    if any(m in low for m in _INTERNAL_MARKERS):
        return True
    return any(w in _ENG_KEYS for w in _WORD.findall(low))


# --- The workspace affect chokepoint: felt content + structured key ----------

def test_workspace_affect_emits_felt_content_and_structured_key():
    """When an underscored engineering signal dominates affect, the conscious
    moment's CONTENT is felt (no identifier) and the raw key rides in the
    `focus_signal` field, not parsed back out of the prose."""
    from brain.cognition.global_workspace import update_workspace

    ctx = {
        "affect_state": {"core_signals": {"impasse_signal": 0.92}},
    }
    moment = update_workspace(ctx)
    assert moment is not None
    # The perceivable content carries no engineering identifier...
    assert not _has_engineering_identifier(moment["content"]), moment["content"]
    # ...and is an actual felt translation, not the raw key with spaces.
    assert "impasse_signal" not in moment["content"]
    assert "being stuck" in moment["content"]
    # The machine key survives in the STRUCTURED field for consumers.
    assert moment.get("focus_signal") == "impasse_signal"


def test_endorsement_reads_focus_field_not_prose():
    """intention_endorsement must take the signal key off the structured field,
    never regex it back out of the felt content string."""
    from brain.cognition.self_state.intention_endorsement import _desire_in_focus

    # Felt prose only in `content`; the key lives in `focus_signal`.
    ctx = {
        "global_workspace": {
            "content": "a strong sense of being stuck",
            "focus_signal": "impasse_signal",
        }
    }
    out = _desire_in_focus(ctx)
    assert out is not None
    key, gloss, is_affect = out
    assert key == "impasse_signal"
    assert is_affect is True
    # The gloss is human-readable, never the raw identifier.
    assert not _has_engineering_identifier(gloss)


def test_endorsement_does_not_parse_key_from_prose():
    """With no structured field, the felt prose alone must NOT yield an
    engineering key — proving the regex parse-back path is gone."""
    from brain.cognition.self_state.intention_endorsement import _desire_in_focus

    ctx = {"global_workspace": {"content": "a strong sense of being stuck"}}
    out = _desire_in_focus(ctx)
    # Either None or a fall-back DRIVE — but never the affect key recovered from prose.
    assert out is None or out[0] != "impasse_signal"


# --- The stagnation-escalation chokepoint ------------------------------------

def test_stagnation_escalation_content_is_felt():
    """The escalation signals must not prefix the felt sentence with the machine
    label (stagnation_signal_acute: ...). The classification lives in tags."""
    from brain.control_signals.stagnation_signal_escalation import (
        update_stagnation_signal_escalation,
        _ACUTE_THRESHOLD,
    )

    ctx = {
        "affect_state": {"core_signals": {"stagnation_signal": 0.9}},
        "_cycles_bored": _ACUTE_THRESHOLD + 5,
    }
    update_stagnation_signal_escalation(ctx)
    sigs = ctx.get("raw_signals") or []
    assert sigs, "escalation should inject a signal at acute cycle count"
    sig = sigs[-1]
    assert not _has_engineering_identifier(sig.get("content", "")), sig.get("content")
    # The machine classification is preserved structurally, in tags.
    assert "stagnation_signal" in (sig.get("tags") or [])
