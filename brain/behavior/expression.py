"""
brain/behavior/expression.py

Expression layer: translate Orrin's current affective state into words using
the vocabulary database (brain/data/vocabulary.json). No LLM — language
is learned and grows over time through the vocabulary system.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.think.cycle_state import CycleState
from brain.utils.log import log_private
_log = get_logger(__name__)

_MIN_URGENCY = 0.20
_POSITIVE_EMOTIONS = frozenset({"positive_valence", "expected_gain", "exploration_drive", "confidence", "wonder", "excitement", "gratitude"})
_NEGATIVE_EMOTIONS = frozenset({"threat_level", "negative_valence", "impasse_signal", "conflict_signal", "social_penalty", "risk_estimate", "rejection_signal", "social_deficit"})

# Congruence map: affect signals not directly in vocabulary → nearest available key.
# Based on Rogers (1959) organismic valuing process: when the expressed content
# diverges from felt experience, the gap is agreeableness, not authenticity.
# Mapping prevents strong felt states from silently collapsing to neutral.
#
# Mapping rules grounded in action tendency research (Frijda 1986):
#   - social_penalty and negative_valence are NOT interchangeable: social_penalty→hide, negative_valence→seek comfort
#     (Tangney & Dearing 2002). Both now have own vocabulary entries.
#   - rejection_signal→conflict_signal: both are rejection-oriented (Rozin & Fallon 1987);
#     rejection_signal is object-rejection, closer to conflict_signal than to blocked-approach impasse_signal.
#   - excitement now has its own vocabulary; no longer falls back to motivation.
#   - gratitude→positive_valence: approach-valence, hedonic overlap (Frijda 1986).
#   - uncertainty→risk_estimate: both involve unresolved threat appraisal.
_CONGRUENCE_MAP = {
    "threat_level":        "risk_estimate",
    "rejection_signal":     "conflict_signal",
    "gratitude":   "positive_valence",
    "uncertainty": "risk_estimate",
    "melancholy":  "negative_valence",
    "dread":       "threat_level",
    "loss_signal":       "negative_valence",
    "jealousy":    "conflict_signal",
}

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_VOCAB_PATH = DATA_DIR / "vocabulary.json"
_WEIGHTS_PATH = DATA_DIR / "vocab_weights.json"
_vocab_cache: Optional[Dict] = None


def _load_vocab() -> Dict:
    global _vocab_cache
    if _vocab_cache is not None:
        return _vocab_cache
    try:
        _vocab_cache = json.loads(_vocab_path().read_text(encoding="utf-8"))
    except Exception as _e:
        record_failure("expression._load_vocab", _e)
    return _vocab_cache or {}


def _vocab_path() -> Path:
    return _VOCAB_PATH


def _phrase_hash(phrase: str) -> str:
    return hashlib.md5(phrase.encode("utf-8", errors="replace")).hexdigest()[:12]


def _load_weights() -> Dict[str, Any]:
    try:
        from brain.utils.json_utils import load_json
        w = load_json(_WEIGHTS_PATH, default_type=dict)
        return w if isinstance(w, dict) else {}
    except Exception:
        return {}


def _weighted_choice(pool: List[str]) -> str:
    """Pick from pool using vocab_weights.json; falls back to uniform random."""
    if not pool:
        return ""
    if len(pool) == 1:
        return pool[0]
    try:
        weights_data = _load_weights()
        ws = [float((weights_data.get(_phrase_hash(p)) or {}).get("weight", 1.0)) for p in pool]
        total = sum(ws)
        if total <= 0:
            return random.choice(pool)
        r = random.random() * total
        cumulative = 0.0
        for phrase, w in zip(pool, ws):
            cumulative += w
            if r <= cumulative:
                return phrase
    except Exception as _e:
        record_failure("expression._weighted_choice", _e)
    return random.choice(pool)


def _pick(section: str, emotion: str) -> str:
    vocab = _load_vocab()
    pool = (vocab.get(section) or {}).get(emotion) or (vocab.get(section) or {}).get("neutral") or []
    return _weighted_choice(pool)


def _congruent_pick(section: str, emotion: str, intensity: float) -> str:
    """
    Select a phrase that matches the felt emotional state rather than
    defaulting to the smoothest available option.

    Rogers (1959) congruence theory: authentic expression requires that the
    content communicated matches the organismic experience. Defaulting to
    neutral phrases when a strong emotion is present is structural agreeableness
    — the system chooses social smoothness over accurate expression. At high
    intensity (> 0.60), this function resists that collapse by enforcing a
    vocabulary match for the felt state before falling back to neutral.

    Pennebaker & Seagal (1999): accurate labeling of emotional experience
    reduces physiological activation_level; suppressed or mismatched expression
    (including via vocabulary-level neutral fallback) sustains it.
    """
    vocab = _load_vocab()
    section_vocab = vocab.get(section) or {}

    # 1. Exact match
    pool = section_vocab.get(emotion)
    if pool:
        return _weighted_choice(pool)

    # 2. Congruence map (nearest affect represented in vocabulary)
    mapped = _CONGRUENCE_MAP.get(emotion)
    if mapped:
        pool = section_vocab.get(mapped)
        if pool:
            return _weighted_choice(pool)

    # 3. At high intensity, prefer any negative affect over neutral rather
    #    than collapsing to agreeable placeholders
    if intensity > 0.60 and emotion not in _POSITIVE_EMOTIONS:
        for neg_emo in ("impasse_signal", "risk_estimate", "negative_valence", "wonder"):
            pool = section_vocab.get(neg_emo)
            if pool:
                return _weighted_choice(pool)

    # 4. Neutral fallback — only when intensity is low or affect is unmapped
    pool = section_vocab.get("neutral") or []
    return _weighted_choice(pool)


def _dominant_emotion(context: Dict[str, Any]) -> str:
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if isinstance(core, dict) and core:
        filtered = {k: float(v) for k, v in core.items() if isinstance(v, (int, float)) and k != "resource_deficit"}
        if filtered:
            return max(filtered, key=filtered.get)
    return "neutral"


def _is_struggle_state(salience: CycleState, context: Dict[str, Any]) -> bool:
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    all_vals = [float(v) for v in core.values() if isinstance(v, (int, float))]
    if not all_vals or max(all_vals) < 0.65:
        return False
    pos = any(float(core.get(e) or 0) > 0.35 for e in _POSITIVE_EMOTIONS)
    neg = any(float(core.get(e) or 0) > 0.35 for e in _NEGATIVE_EMOTIONS)
    return pos and neg and len(salience.output_seed or "") >= 20


def _build_struggle_response(salience: CycleState, emotion: str) -> str:
    """For mixed-valence high-intensity states — fragmented, unresolved expression.

    Uses _congruent_pick at high intensity (0.85) — mixed-valence states are by
    definition high-intensity, so the congruence map must apply here as much as
    anywhere. Rogers (1959): incongruence is most damaging precisely in high-affect
    states where the gap between felt experience and expressed content is largest.
    """
    vocab = _load_vocab()
    starters   = vocab.get("starters")    or ["I notice"]
    connectors = vocab.get("connectors")  or ["and yet"]

    parts = []
    if salience.output_seed:
        parts.append(salience.output_seed[:120])
    else:
        reflection = _congruent_pick("reflections", emotion, 0.85)
        if reflection:
            parts.append(reflection)

    if random.random() < 0.6:
        connector_reflection = _congruent_pick("reflections", emotion, 0.85)
        if connector_reflection:
            parts.append(random.choice(connectors) + " " + connector_reflection.lower().rstrip("."))

    if not parts:
        parts.append(random.choice(starters) + " something I can't quite name yet.")

    return " ".join(parts)


def express(
    salience: CycleState,
    context: Dict[str, Any],
    user_input: str = "",
) -> str:
    """
    Translate Orrin's current state into natural language using the vocabulary
    database. Returns empty string if there is nothing worth saying.
    """
    if salience.is_quiet() and not user_input:
        return ""

    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    social_penalty = float(core.get("social_penalty") or 0.0)
    resource_deficit = float(emo.get("resource_deficit") or 0.0)

    if social_penalty > 0.65 and not user_input:
        log_private("[expression] suppressed — social_penalty (no user input)")
        return ""

    emotion = _dominant_emotion(context)

    # Compute affective intensity for congruence enforcement
    _emo_intensity = 0.0
    try:
        _emo_core = (context.get("affect_state") or {}).get("core_signals") or \
                    (context.get("affect_state") or {})
        _emo_intensity = float(_emo_core.get(emotion) or 0.0)
    except Exception as _e:
        record_failure("expression.express", _e)

    # When the user speaks we ALWAYS reply — resource_deficit, social_penalty, and low pressure
    # can shape the reply but cannot silence it completely.
    if user_input:
        if social_penalty > 0.65:
            return random.choice(["That's not something I can engage with right now.", "I need a moment."])
        if resource_deficit > 0.85:
            return random.choice(["I'm here, just slow right now.", "Yeah. Bear with me.", "Here."])
        reply = _congruent_pick("speech_replies", emotion, _emo_intensity)
        if not reply:
            reply = "I hear you."
        # Append a reflection if there's output pressure
        if salience.output_pressure > 0.5 and salience.output_seed:
            seed = salience.output_seed[:100].rstrip(".")
            reply = f"{reply} {seed}."
        log_private(f"[expression] speech reply ({emotion}) → {reply[:80]}")
        # Track phrase for feedback weighting
        context["_last_vocab_phrase_hash"] = _phrase_hash(reply)
        return reply

    if resource_deficit > 0.85 and salience.output_pressure < 0.55:
        return random.choice(["...", "Mm."])

    # Internal expression (no user input)
    in_struggle = _is_struggle_state(salience, context)
    if in_struggle:
        result = _build_struggle_response(salience, emotion)
        log_private(f"[expression] struggle ({emotion}) → {result[:80]}")
        return result

    # Use output_seed if present and short, otherwise pick from vocabulary
    if salience.output_seed and len(salience.output_seed) < 150:
        result = salience.output_seed
    else:
        result = _congruent_pick("reflections", emotion, _emo_intensity)

    # Append a reasoning conclusion if available
    if salience.reasoning_conclusion and random.random() < 0.4:
        conclusion = salience.reasoning_conclusion[:100].rstrip(".")
        if result:
            result = f"{result} {conclusion}."
        else:
            result = conclusion

    if result:
        # Track phrase for feedback weighting
        context["_last_vocab_phrase_hash"] = _phrase_hash(result)

    log_private(f"[expression] urgency={salience.output_pressure:.2f} emotion={emotion} → {(result or '')[:80]}")
    return result or ""
