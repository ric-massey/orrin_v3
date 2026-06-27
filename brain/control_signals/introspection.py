# brain/control_signals/introspection.py
#
# Orrin's introspective access to his own affective state is imperfect.
#
# The ground truth lives in affect_state["core_signals"] and drives all
# unconscious machinery: attention filtering, reward signals, drives, behavior
# modulation, tone. That ground truth is NEVER directly reported to the LLM.
#
# What reaches conscious reasoning (system prompt, inner loop, self-reports)
# is a *perceived* state that passes through three failure modes:
#
#   1. Label confusion — risk_estimate perceived as impasse_signal (env-biased: Schachter-Singer)
#   2. Intensity misjudgment — feeling is stronger or weaker than registered
#   3. Granularity failure — when many affect signals cluster at similar intensity, they
#      stop being distinct states and blur into a single diffuse affect
#      (the primary misidentification mode, per alexithymia research)
#
# Schachter-Singer two-factor theory: undifferentiated activation_level gets labeled based
# on the most salient environmental cue available. Orrin's environment is the
# computer — file changes, system stress, user presence, attention mode — so
# those signals bias which label ambiguous activation_level receives.
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

# ── Confusion matrix ──────────────────────────────────────────────────────────
# Patterns are grounded in documented psychology:
#   - social_penalty→conflict_signal: well-replicated externalizing pathway (Tang et al. 2024)
#   - risk_estimate→impasse_signal: clinically documented "risk_estimate as masquerader"
#   - threat_level↔excitement: Zillmann excitation transfer (activation_level relabeled by context)
#   - guilt is action-focused (→reward_negative), social_penalty is self-focused (→conflict_signal) — distinct
#   - social_deficit→stagnation_signal: removed (correlation only, not documented misattribution)
_CONFUSION: Dict[str, List[Tuple[str, float]]] = {
    "risk_estimate":    [("impasse_signal", 0.38), ("overwhelm", 0.25), ("dread", 0.18)],
    "threat_level":       [("risk_estimate", 0.45), ("dread", 0.25), ("excitement", 0.12)],
    "social_deficit": [("reward_negative", 0.32), ("loss_signal", 0.20)],
    "social_penalty":      [("conflict_signal", 0.35), ("impasse_signal", 0.28), ("reward_negative", 0.15)],
    "loss_signal":      [("reward_negative", 0.40), ("resource_deficit", 0.20)],
    "overwhelm":  [("impasse_signal", 0.35), ("risk_estimate", 0.30), ("conflict_signal", 0.20)],
    "guilt":      [("reward_negative", 0.30), ("impasse_signal", 0.22), ("social_penalty", 0.15)],
    "reward_negative":    [("resource_deficit", 0.30), ("loss_signal", 0.22), ("social_deficit", 0.18)],
    "conflict_signal":      [("impasse_signal", 0.48), ("overwhelm", 0.22)],
    "despair":    [("reward_negative", 0.40), ("resource_deficit", 0.25), ("loss_signal", 0.20)],
    "dread":      [("risk_estimate", 0.42), ("threat_level", 0.28)],
    "excitement": [("risk_estimate", 0.35), ("motivation", 0.22)],
}

# Negative emotion labels — used for granularity valence detection
_NEGATIVE = frozenset({
    "risk_estimate", "threat_level", "dread", "panic", "conflict_signal", "impasse_signal", "rage",
    "social_penalty", "guilt", "loss_signal", "reward_negative", "social_deficit", "despair",
    "overwhelm", "worry", "regret",
})

_NOISE_FLOOR      = 0.08   # below this: transparent to introspection
_SUPPRESS_CEILING = 0.38   # below this: can silently drop from awareness
_GRAN_THRESHOLD   = 0.35   # below this: granularity failure mode


def compute_perceived_state(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce the perceived emotional state that reaches Orrin's conscious reasoning.

    Returns:
      "perceived_affect_state" : dict
      "introspection_clarity"     : float (0–1)
      "uncertain"                 : bool
      "granularity"               : float (0–1; 1 = well-differentiated)
      "granularity_failure"       : bool
      "missed"                    : list  (suppressed emotions — debug only)
      "swapped"                   : list  (misattributions — debug only)
    """
    actual      = (context.get("affect_state") or {})
    core_actual = (actual.get("core_signals") or {})

    clarity     = _compute_clarity(actual, context)
    granularity = _compute_granularity(core_actual)
    env_bias    = _environment_bias(context)

    rng = random.Random()   # unseeded — genuinely stochastic each cycle

    # ── Granularity failure mode ──────────────────────────────────────────────
    # When many emotions blur together at similar intensities, the perceived state
    # collapses to a diffuse affect rather than a set of distinguishable states.
    active_vals = [
        float(v) for k, v in core_actual.items()
        if isinstance(v, (int, float)) and float(v) >= _NOISE_FLOOR
        and k not in {"dominant", "affect_stability", "mode", "last_updated",
                      "emotional_congruence", "core_signals"}
    ]
    if granularity < _GRAN_THRESHOLD and len(active_vals) >= 3:
        return _granularity_failure(actual, core_actual, active_vals, clarity, granularity)

    # ── Normal path: label confusion + intensity noise + suppression ──────────
    _meta = {"dominant", "affect_stability", "mode", "last_updated",
             "emotional_congruence", "core_signals"}

    perceived_core: Dict[str, float]          = {}
    missed:         List[str]                 = []
    swapped:        List[Tuple[str, str, float]] = []

    for emotion, raw_val in core_actual.items():
        if emotion in _meta:
            continue
        try:
            v = float(raw_val)
        except (TypeError, ValueError):
            continue
        if v < _NOISE_FLOOR:
            continue

        # 1. Intensity noise
        noise_std   = (1.0 - clarity) * 0.15
        v_perceived = max(0.0, min(1.0, v + rng.gauss(0, noise_std)))

        # 2. Suppression
        if v < _SUPPRESS_CEILING and rng.random() < (1.0 - clarity) * 0.14:
            missed.append(emotion)
            continue

        # 3. Label confusion — env-biased (Schachter-Singer)
        confusable = _CONFUSION.get(emotion, [])
        label_used = emotion

        if confusable:
            # Collect all confusables that fire, weighted by environmental congruence
            fired: List[Tuple[str, float]] = []
            for alt_label, base_prob in confusable:
                effective = base_prob * (1.0 - clarity)
                if rng.random() < effective:
                    env_weight = env_bias.get(alt_label, 0.0)
                    fired.append((alt_label, env_weight))

            if fired:
                # Among those that fired, prefer the most environmentally-congruent label.
                # This is the Schachter-Singer mechanism: same activation_level, environment picks
                # the label. Without env signal: take first alphabetically (stable default).
                fired.sort(key=lambda x: x[1], reverse=True)
                label_used = fired[0][0]
                prev = perceived_core.get(label_used, 0.0)
                perceived_core[label_used] = max(prev, v_perceived * rng.uniform(0.80, 1.05))
                swapped.append((emotion, label_used, v))

        if label_used == emotion:
            prev = perceived_core.get(emotion, 0.0)
            perceived_core[emotion] = max(prev, v_perceived)

    perceived_core = {k: round(min(1.0, max(0.0, v)), 3) for k, v in perceived_core.items()}

    perceived_state                  = {k: v for k, v in actual.items() if k != "core_signals"}
    perceived_state["core_signals"] = perceived_core

    uncertain = (clarity < 0.52) or (len(swapped) >= 2) or (len(missed) >= 2)

    return {
        "perceived_affect_state": perceived_state,
        "introspection_clarity":     round(clarity, 3),
        "uncertain":                 uncertain,
        "granularity":               round(granularity, 3),
        "granularity_failure":       False,
        "missed":                    missed,
        "swapped":                   swapped,
    }


# ── Granularity failure ───────────────────────────────────────────────────────

def _granularity_failure(
    actual: Dict[str, Any],
    core_actual: Dict[str, Any],
    active_vals: List[float],
    clarity: float,
    granularity: float,
) -> Dict[str, Any]:
    """
    When emotional granularity is too low, the states blur into a single
    diffuse affect — the primary introspective failure mode (alexithymia research).
    """
    avg_intensity = sum(active_vals) / len(active_vals)

    neg_total = sum(
        float(core_actual.get(e, 0)) for e in _NEGATIVE
        if isinstance(core_actual.get(e), (int, float))
    )
    pos_keys  = {"reward_positive", "expected_gain", "novelty_signal", "exploration_drive", "motivation", "confidence"}
    pos_total = sum(
        float(core_actual.get(e, 0)) for e in pos_keys
        if isinstance(core_actual.get(e), (int, float))
    )

    if neg_total > pos_total * 1.5:
        diffuse_label = "diffuse_negative"
    elif pos_total > neg_total * 1.5:
        diffuse_label = "diffuse_positive"
    else:
        diffuse_label = "diffuse_mixed"

    perceived_state                  = {k: v for k, v in actual.items() if k != "core_signals"}
    perceived_state["core_signals"] = {diffuse_label: round(avg_intensity, 3)}

    return {
        "perceived_affect_state": perceived_state,
        "introspection_clarity":     round(clarity, 3),
        "uncertain":                 True,
        "granularity":               round(granularity, 3),
        "granularity_failure":       True,
        "missed":                    [],
        "swapped":                   [],
    }


# ── Environmental bias (Schachter-Singer) ─────────────────────────────────────

def _environment_bias(context: Dict[str, Any]) -> Dict[str, float]:
    """
    Map the current environment to a set of emotion labels that the context
    makes more salient — biasing which label ambiguous activation_level receives.

    Orrin's environment is the computer: file changes, system stress, user
    presence, attention mode.  These are its social and physical surroundings
    in the same way the confederate's mood shaped activation_level labeling for human
    subjects in Schachter-Singer's experiments.
    """
    bias: Dict[str, float] = {}

    # Collect active signal tags
    signal_tags: set = set()
    for s in (context.get("top_signals") or []):
        for t in (s.get("tags") or []):
            signal_tags.add(t)

    # Orrin's own code changed → self-relevant change → exploration_drive about self, mild risk_estimate
    if "body_touched" in signal_tags:
        bias["exploration_drive"]  = bias.get("exploration_drive",  0.0) + 0.45
        bias["risk_estimate"]    = bias.get("risk_estimate",    0.0) + 0.20

    # Home changed → den-relevant curiosity: closer than the outside world, less
    # alarming than a body change.
    if "home_touched" in signal_tags:
        bias["exploration_drive"] = bias.get("exploration_drive", 0.0) + 0.38
        bias["risk_estimate"] = bias.get("risk_estimate", 0.0) + 0.08

    # External world changed → outward exploration_drive, interest
    if "world_changed" in signal_tags:
        bias["exploration_drive"]  = bias.get("exploration_drive",  0.0) + 0.50

    # User is present and speaking → social/relational context
    if "user_input" in signal_tags or bool(context.get("latest_user_input", "").strip()):
        bias["anticipation"] = bias.get("anticipation", 0.0) + 0.35
        bias["exploration_drive"]    = bias.get("exploration_drive",    0.0) + 0.20

    # Social signal but no user input → absence of connection
    if "social" in signal_tags and "user_input" not in signal_tags:
        bias["social_deficit"] = bias.get("social_deficit", 0.0) + 0.30

    # System stress → overwhelm, resource_deficit
    body_sense = context.get("body_sense") or {}
    states     = set(body_sense.get("states") or [])

    if states & {"strained", "heavy"}:
        bias["overwhelm"] = bias.get("overwhelm", 0.0) + 0.45
        bias["resource_deficit"]   = bias.get("resource_deficit",   0.0) + 0.30
    if "swelling" in states:          # memory pressure climbing
        bias["overwhelm"] = bias.get("overwhelm", 0.0) + 0.30
    if "sluggish" in states:          # high step latency
        bias["resource_deficit"]   = bias.get("resource_deficit",   0.0) + 0.40
    if states & {"spacious", "clear"}:
        bias["confidence"] = bias.get("confidence", 0.0) + 0.30
        bias["exploration_drive"]  = bias.get("exploration_drive",  0.0) + 0.20

    # Attention mode
    attn = context.get("attention_mode", "")
    if attn == "drowsy":
        bias["social_deficit"] = bias.get("social_deficit", 0.0) + 0.35
        bias["reward_negative"]    = bias.get("reward_negative",    0.0) + 0.20
    elif attn == "wandering":
        bias["exploration_drive"]  = bias.get("exploration_drive",  0.0) + 0.25

    return bias


# ── Granularity score ─────────────────────────────────────────────────────────

def _compute_granularity(core_signals: Dict[str, Any]) -> float:
    """
    Emotional granularity (0–1): how well-differentiated are the active emotions?

    Low granularity = several emotions cluster at similar intensity → they blur.
    High granularity = one clearly dominant, others much lower.

    Primary source: alexithymia research — the core introspective failure is not
    mislabeling but failure to differentiate adjacent states at all.
    """
    _skip = {"dominant", "affect_stability", "mode", "last_updated",
             "emotional_congruence", "core_signals"}
    vals = sorted(
        (float(v) for k, v in core_signals.items()
         if k not in _skip and isinstance(v, (int, float)) and float(v) >= _NOISE_FLOOR),
        reverse=True,
    )

    if len(vals) <= 1:
        return 1.0   # nothing to differentiate

    if len(vals) == 2:
        return min(1.0, abs(vals[0] - vals[1]) / 0.30)

    # 3+ emotions: how far does the strongest stand out from the pack?
    top      = vals[0]
    rest     = vals[1:]
    avg_rest = sum(rest) / len(rest)
    spread   = top - avg_rest

    # Extra penalty: many emotions clustered close together
    cluster_count = sum(1 for v in vals if abs(v - avg_rest) < 0.12)
    raw = (spread / 0.35) - (cluster_count * 0.07)
    return round(max(0.0, min(1.0, raw)), 3)


# ── Clarity score ─────────────────────────────────────────────────────────────

def _compute_clarity(actual: Dict[str, Any], context: Dict[str, Any]) -> float:
    """
    Introspective clarity (0–1). Higher = perceived ≈ actual.

    What degrades it:
      - Low emotional stability
      - Multiple strong emotions competing (signal separation problem, not raw intensity)
      - Attention hijacking (one emotion consuming bandwidth)
      - Pending emotional integration (the knowing/feeling gap)
    """
    stability = float(actual.get("affect_stability") or 1.0)
    clarity   = stability

    core      = actual.get("core_signals") or {}
    competing = sum(1 for v in core.values()
                    if isinstance(v, (int, float)) and float(v) >= 0.50)
    if competing >= 2:
        clarity -= min(0.30, (competing - 1) * 0.10)

    if context.get("attention_constrained"):
        slots_taken = int((context.get("_hijacked_by") or {}).get("slots_taken", 0))
        clarity -= slots_taken * 0.10

    pending  = context.get("_pending_emotional_integration") or []
    clarity -= min(0.12, len(pending) * 0.04)

    return round(max(0.10, min(1.0, clarity)), 3)


# ── Uncertainty note ──────────────────────────────────────────────────────────

def get_uncertainty_note(clarity: float, uncertain: bool,
                         granularity_failure: bool = False) -> Optional[str]:
    """
    Phenomenological note to append when Orrin can't read himself clearly.
    Returns None at high clarity.
    """
    if granularity_failure:
        return ("Several things are present at once and they aren't separating — "
                "it's difficult to say what any single one is.")
    if clarity >= 0.68 and not uncertain:
        return None
    if clarity >= 0.52:
        return "Something about this state is partially formed — I'm reading the edges of it, not the center."
    if clarity >= 0.35:
        return "I'm not sure what I'm feeling, exactly. There's something present but it isn't resolving into a name."
    return "The internal state is diffuse and hard to read from the inside. Something is there — I can't tell clearly what."
