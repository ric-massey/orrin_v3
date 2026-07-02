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


# --- P6: the standing veil guard (substrate → consciousness one-way) ----------
#
# Audit record (2026-07-01, closes plan P6 change 1): the consciousness-side
# sweep found two residual raw reads and both are now routed through
# introspection.felt_affect (the one door): identity.build_system_prompt's
# boot-time fallback and generate_response's system-prompt affect load — both
# previously loaded SIGNAL_STATE_FILE raw. Modules examined and left OUT of the
# guard set because they are SUBSTRATE-side (they may hold raw keys by design):
#   - control_signals/introspection.py — the projection producer (the veil itself)
#   - cognition/global_workspace.py — the substrate→conscious chokepoint; its
#     OUTPUT is felt (tested above), its input is necessarily raw
#   - self_state/latent_identity.py — derives the LATENT identity vector
#     (unconscious machinery; nothing it writes is perceivable content)
#   - self_state/values_check.py — emotional bias on a symbolic refusal
#     threshold (unconscious modulation, like the arbiter)
#   - self_state/fragmentation.py — MUTATES affect_state (substrate mechanism)

# Consciousness-tagged modules: code whose output is conscious-facing content
# (system prompts, spoken/rendered language, speakability). These must reach
# affect ONLY via the perceived projection (felt_affect / perceived_affect_state)
# — never the raw state file, never context["affect_state"].
_CONSCIOUSNESS_MODULES = [
    "brain/cognition/self_state/identity.py",
    "brain/cognition/self_state/intention_endorsement.py",
    "brain/cognition/language/voice.py",
    "brain/cognition/language/conditional_render.py",
    "brain/think/speech_builder.py",
    "brain/behavior/speakability.py",
    "brain/utils/generate_response.py",
]

_RAW_ACCESS = re.compile(
    r"SIGNAL_STATE_FILE"                 # direct raw-state file access
    r"|\.get\(\s*[\"']affect_state[\"']" # raw substrate view off a context dict
    r"|\[\s*[\"']affect_state[\"']\s*\]"
)


def _code_lines(path):
    """Source lines with comments stripped (a mention in prose is not a leak)."""
    import pathlib
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return [line.split("#", 1)[0] for line in text.splitlines()]


def test_consciousness_modules_never_read_raw_substrate():
    """Standing guard: a consciousness-tagged module acquiring a raw affect
    access path (state file or context['affect_state']) fails here, at the
    commit that introduces it. Route it through introspection.felt_affect."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    leaks = []
    for rel in _CONSCIOUSNESS_MODULES:
        path = root / rel
        assert path.exists(), f"guard set names a missing module: {rel}"
        for i, line in enumerate(_code_lines(path), start=1):
            if _RAW_ACCESS.search(line):
                leaks.append(f"{rel}:{i}: {line.strip()}")
    assert not leaks, (
        "raw substrate access from consciousness-side code (use "
        "introspection.felt_affect — the one door):\n" + "\n".join(leaks))


def test_felt_affect_returns_projection_not_ground_truth():
    """The one door returns the cycle's published projection when present, and
    never hands back the raw affect_state object."""
    from brain.control_signals.introspection import felt_affect

    published = {"core_signals": {"impasse_signal": 0.4}}
    raw = {"core_signals": {"impasse_signal": 0.92}}
    ctx = {"perceived_affect_state": published, "affect_state": raw}
    assert felt_affect(ctx) is published

    # No published projection → computed on the spot, and it is NOT the raw dict.
    ctx2 = {"affect_state": raw}
    out = felt_affect(ctx2)
    assert out is not raw
    assert isinstance(out, dict)
    # ...and the computed projection is cached for the rest of the cycle.
    assert ctx2.get("perceived_affect_state") is out
