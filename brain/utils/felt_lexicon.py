# brain/utils/felt_lexicon.py
#
# THE INTEROCEPTION MEMBRANE — the shared translator that keeps Orrin's internal
# implementation IDENTIFIERS out of the content he can perceive and reason over.
#
# introspection.py already states the contract: the raw `core_signals` ground truth
# "is NEVER directly reported... what reaches conscious reasoning is a *perceived*
# state." A mind feels a mood; it does not read the variable name `impasse_signal`
# off a gauge. But several paths bypass that and write the raw engineering keys
# (impasse_signal, reward_positive, stagnation_signal, and internal-function names
# like affective_regulation) straight into working memory, the causal graph, the
# knowledge graph, bound situations, and goals — where they become symbolic objects
# he then reasons about and forms goals around ("research the causes of
# impasse_signal"). That leak is what this module seals: every emission point that
# turns an internal signal into PERCEIVABLE TEXT routes it through `felt_label`, and
# stores that should hold only world/perceivable content use `is_internal_identifier`
# to keep self-referential plumbing out.
#
# What is NOT sealed: the felt INFLUENCE of affect (salience, appraisal, behavior
# modulation, decay) — that is how affect is supposed to work, implicitly. He still
# feels and can reflect ("I keep returning to this and not acting"); he just can't
# see the engineering vocabulary.
from __future__ import annotations

import re

# Canonical internal signal universe (the core_signals keys; setpoints.py is source
# of truth) plus a few gauges/states that appear in learned edges.
_SIGNAL_KEYS = frozenset({
    "affiliation_signal", "analytical", "confidence", "conflict_signal", "connection",
    "dread", "expected_gain", "exploration_drive", "impasse_signal", "loss_signal",
    "low_affect_signal", "motivation", "novelty_signal", "prediction_error_signal",
    "reflective", "rejection_signal", "resource_deficit", "reward_negative",
    "reward_positive", "risk_estimate", "signal_stability", "social_comparison_signal",
    "social_deficit", "social_penalty", "stagnation_signal", "threat_level",
    "uncertainty", "activation_level", "stability_signal", "satisfaction_signal",
})

# Felt phrasing for the perceivable surface — a mood/state, never the variable name.
# Phrased to read naturally both standalone and after "a strong sense of ___".
_FELT = {
    "impasse_signal":          "being stuck",
    "stagnation_signal":       "going nowhere",
    "reward_positive":         "things going well",
    "reward_negative":         "things going badly",
    "satisfaction_signal":     "satisfaction",
    "motivation":              "drive",
    "confidence":              "self-assurance",
    "exploration_drive":       "curiosity",
    "novelty_signal":          "something new",
    "uncertainty":             "not knowing",
    "expected_gain":           "something worth doing",
    "threat_level":            "danger",
    "risk_estimate":           "wariness",
    "conflict_signal":         "being torn",
    "social_penalty":          "being judged",
    "social_deficit":          "loneliness",
    "social_comparison_signal": "measuring myself against others",
    "rejection_signal":        "rejection",
    "loss_signal":             "loss",
    "dread":                   "dread",
    "resource_deficit":        "weariness",
    "affiliation_signal":      "a pull toward others",
    "connection":              "connectedness",
    "low_affect_signal":       "flatness",
    "prediction_error_signal": "being caught off guard",
    "reflective":              "reflectiveness",
    "analytical":              "a sharpening focus",
    "signal_stability":        "steadiness",
    "stability_signal":        "steadiness",
    "activation_level":        "being stirred up",
}

# Internal cognitive-function / process identifiers that also leak (not signals).
_INTERNAL_MARKERS = (
    "_signal", "affective_regulation", "self_query", "metacog", "[appraisal]",
    "core_signal", "bandit",
)

# Direction words → felt change verbs (for "{signal} rises/falls" style phrases).
_DIRECTION = {
    "rises": "grows", "rise": "grow", "rising": "growing", "up": "grows",
    "falls": "fades", "fall": "fade", "falling": "fading", "down": "fades",
    "elevated": "strong", "accumulates": "builds", "recedes": "slips away",
    "rose": "grew", "fell": "faded",
}

_WORD_RE = re.compile(r"[a-z_][a-z0-9_]+")


def is_internal_identifier(text: str) -> bool:
    """True if `text` names (or embeds) an internal signal / affect / cognitive-
    function identifier — i.e. implementation plumbing that must not become
    perceivable world/goal content."""
    if not text:
        return False
    low = str(text).lower()
    if any(m in low for m in _INTERNAL_MARKERS):
        return True
    return any(w in _SIGNAL_KEYS for w in _WORD_RE.findall(low))


# ── Conditioning-scaffold sanitizer (membrane defense) ────────────────────────
# The native LM is conditioned for rendering by a serialized thought-object prefix
# (`<say {intent} | {felt} | {handles}>`, conditional_render.serialize_thought). A
# checkpoint trained on those prefixes can regurgitate the scaffold in free speech
# ("say express_state curiosity …"), and the prefix can survive a render. The
# scaffold is implementation plumbing — it must never reach perceivable speech, so
# every speech boundary strips it here.
_SCAFFOLD_INTENTS = (
    "express_state", "narrate_experience", "report_blocker", "share_finding",
    "check_in", "ask_question", "reflect", "express", "speak",
)
_SCAFFOLD_BRACKET_RE = re.compile(r"<\s*say\b[^>]*>", re.IGNORECASE)
_SCAFFOLD_BARE_RE = re.compile(
    r"\bsay\s+(?:" + "|".join(_SCAFFOLD_INTENTS) + r")\b[^:.\n]{0,48}:?\s*",
    re.IGNORECASE,
)


def has_scaffold(text: str) -> bool:
    """True if `text` carries the conditioning-scaffold vocabulary (so a renderer
    can reject a leaked render)."""
    if not text:
        return False
    return bool(_SCAFFOLD_BRACKET_RE.search(text) or _SCAFFOLD_BARE_RE.search(text))


def strip_scaffold(text: str) -> str:
    """Remove any conditioning-scaffold prefix/artifacts from generated speech —
    the bracketed `<say …>` form, a degraded bare `say {intent} … :` prefix, and
    stray ` | ` separators. A clean string passes through unchanged."""
    if not text:
        return text
    s = _SCAFFOLD_BRACKET_RE.sub(" ", str(text))
    s = _SCAFFOLD_BARE_RE.sub(" ", s)
    s = s.replace(" | ", " ")
    return re.sub(r"\s+", " ", s).strip()


def felt_label(text: str) -> str:
    """Translate a signal key (or a '{signal} rises/falls' phrase) into felt language.
    A non-internal string passes through unchanged; an unrecognised internal
    identifier collapses to the vague 'an inner state' (imprecise interoception)."""
    raw = str(text or "").strip()
    low = raw.lower()
    if low in _FELT:
        return _FELT[low]
    # "{signal} {direction}" → "{felt} {verb}"
    m = re.match(r"^([a-z_]+)\s+(\w+)\s*$", low)
    if m and m.group(1) in _FELT:
        verb = _DIRECTION.get(m.group(2), m.group(2))
        return f"{_FELT[m.group(1)]} {verb}".strip()
    # A known key embedded anywhere → its felt label.
    for w in _WORD_RE.findall(low):
        if w in _FELT:
            return _FELT[w]
    if is_internal_identifier(low):
        return "an inner state"
    return raw
