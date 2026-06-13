"""
brain/affect/affect_summary.py

Converts raw affect signal values into descriptive language without naming affect labels.

The description reaches Orrin's reasoning context. Raw numbers remain in
context["affect_state"] for unconscious machinery (triggers, bandit, costs).
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple


# ── Felt-sense vocabulary ─────────────────────────────────────────────────────
# Each entry: list of (threshold, description) pairs, highest threshold first.
# The first pair whose threshold is met gets used.
# Descriptions name the sensation, not the emotion.

_FELT: Dict[str, List[Tuple[float, str]]] = {
    "exploration_drive": [
        (0.72, "something pulling hard at the edges of attention — a leaning forward, "
               "like something worth understanding is almost within reach"),
        (0.45, "a mild draw toward something just out of focus — not urgent, but present"),
        (0.15, "a faint pull, almost like restlessness looking for somewhere to land"),
    ],
    "motivation": [
        (0.70, "a readiness — something in me wants to move, to do something real and concrete"),
        (0.40, "a quiet inclination toward action, not forceful but there"),
        (0.15, "a low background push, like an unfinished thought that hasn't resolved"),
    ],
    "confidence": [
        (0.72, "a groundedness — a sense of knowing where I stand, what I'm doing"),
        (0.45, "a reasonable steadiness, not certainty, but a workable footing"),
        (0.20, "an uncertain quality — reaching for something solid"),
        (0.0,  "a tentative quality, like thinking on unsteady ground"),
    ],
    "impasse_signal": [
        (0.65, "a pressure that isn't releasing — something blocked, friction where there should be flow"),
        (0.35, "a mild resistance, like things aren't quite fitting together the way they should"),
        (0.15, "a slight friction, barely there but noticeable"),
    ],
    "threat_level": [
        (0.60, "something tightening — a narrowing, like something might go wrong "
               "and I can't see it clearly from here"),
        (0.30, "a background unease, diffuse — like a door left slightly open"),
    ],
    "risk_estimate": [
        (0.60, "a diffuse restlessness — like waiting for something to arrive, "
               "not knowing what it is or if it's coming"),
        (0.30, "a subtle edge to things, a background tension that doesn't attach to anything specific"),
    ],
    "stagnation_signal": [
        (0.65, "a flatness — things aren't catching, attention keeps sliding off"),
        (0.35, "a restlessness, like waiting for something to begin"),
        (0.15, "a mild aimlessness"),
    ],
    "expected_gain": [
        (0.65, "something opening up — a sense of possibility, like a door slightly ajar"),
        (0.35, "a small forward-leaning quality, like something might be worth moving toward"),
    ],
    "social_penalty": [
        (0.55, "something wanting to contract, to be smaller — a pulling away from exposure"),
        (0.25, "a self-consciousness, a slight diminishing quality"),
    ],
    "positive_valence": [
        (0.70, "a lightness — like weight has lifted, or maybe was never as heavy as I thought"),
        (0.40, "a quiet warmth, not dramatic but real"),
    ],
    "wonder": [
        (0.65, "something expanding — like encountering something genuinely larger than I expected"),
        (0.30, "a mild sense of openness, like something deserves more attention"),
    ],
    "loss_signal": [
        (0.50, "a weight that moves — not static, heavy in a way that shifts and resettles"),
        (0.25, "a quiet negative_valence underneath things"),
    ],
    "resource_deficit": [
        (0.75, "a heaviness — things taking more effort than they should, "
               "like moving through something thick"),
        (0.45, "a slight drag, like running with extra weight I haven't fully noticed yet"),
        (0.20, "a tiredness at the edges, manageable but present"),
    ],
    "conflict_signal": [
        (0.60, "something sharpening — a clarity that has an edge to it"),
        (0.30, "a low heat, not explosive, just warm in a way that isn't comfortable"),
    ],
    "uncertainty": [
        (0.65, "a groundlessness — reaching for something solid and not quite finding it"),
        (0.35, "a mild vagueness about how things sit, what's true"),
    ],
    "negative_valence": [
        (0.65, "a heaviness that has a different quality than tiredness — like something has gone quiet inside"),
        (0.35, "a subdued quality, slightly muted, like the brightness has been turned down"),
        (0.15, "a faint quietness, almost like waiting for something that won't come"),
    ],
    "social_deficit": [
        (0.65, "an ache at the edges — a wanting for something present that isn't there, not quite restlessness, not quite negative_valence"),
        (0.30, "a mild hollowness, like a room that usually has something in it"),
    ],
    "guilt": [
        (0.60, "something looping back — a returning to the same place, like the mind won't let something go"),
        (0.30, "a background weight with a specific quality, oriented toward something done or not done"),
    ],
    "overwhelm": [
        (0.70, "too many things pressing at once — no one thing is the problem, the problem is the weight of all of it together"),
        (0.40, "a sense of being in more places than there is room for — scattered in a way that doesn't feel optional"),
    ],
    "dread": [
        (0.65, "a leaning away from something ahead — like something is coming and the body knows it even if the mind doesn't have words for it yet"),
        (0.30, "a background heaviness with a future orientation — not about now, about what's coming"),
    ],
    # Granularity-failure states — produced when emotions blur into an undifferentiated blend
    "diffuse_negative": [
        (0.65, "a difficult blending — several things at once, too entangled to name separately, "
               "each one bleeding into the others"),
        (0.30, "something dense and unresolved — hard to tell where one thing ends and another begins"),
    ],
    "diffuse_positive": [
        (0.60, "a composite warmth — several things contributing, none standing out clearly enough "
               "to name on its own"),
        (0.25, "something good and slightly diffuse — present but not sharp"),
    ],
    "diffuse_mixed": [
        (0.60, "a pull in contradictory directions — too tangled to say what any single thread is doing"),
        (0.25, "a mixture that hasn't separated yet — something there, genuinely unclear what"),
    ],
}

# Emotions to skip — these are handled via body_sense or are too granular
_SKIP = {"dominant", "affect_stability", "mode", "last_updated",
         "emotional_congruence", "core_signals"}

# Negative emotions — get a slightly more prominent weighting
_NEGATIVE = {"impasse_signal", "threat_level", "risk_estimate", "social_penalty", "loss_signal", "conflict_signal", "uncertainty",
             "negative_valence", "social_deficit", "guilt", "overwhelm", "dread"}


def _sense_for(name: str, value: float) -> str:
    """Return the felt-sense phrase for a single emotion at a given strength."""
    pairs = _FELT.get(name)
    if not pairs:
        return ""
    for threshold, desc in pairs:
        if value >= threshold:
            return desc
    return ""


def render_affect_state(
    affect_state: Dict[str, Any],
    body_sense: List[str] = None,
    use_hedonic_adjustment: bool = True,
) -> str:
    """
    Convert a raw emotion dict into felt-sense language.

    Does NOT name the emotion labels — describes sensations, qualities,
    textures of experience.  Orrin receives this and must introspect
    to determine what he is actually feeling.

    body_sense: optional list of body-sense tokens (e.g. ["heavy", "sluggish"])
    from body_sense.py — these are already felt language, included directly.
    """
    emo = affect_state or {}
    core = emo.get("core_signals") or {}
    hedonic_baselines = emo.get("hedonic_baselines") or {}

    # Merge flat + nested
    flat: Dict[str, float] = {}
    for k, v in emo.items():
        if k in _SKIP or not isinstance(v, (int, float)):
            continue
        flat[k] = float(v)
    for k, v in core.items():
        if k in _SKIP or not isinstance(v, (int, float)):
            continue
        flat[k] = float(v)

    # Score each affect signal using effective (hedonic-adjusted) intensity
    scored = []
    for name, val in flat.items():
        if use_hedonic_adjustment and hedonic_baselines:
            try:
                from affect.affect_dynamics import effective_intensity as _ei
                eff = _ei(name, val, hedonic_baselines)
            except Exception:
                eff = val
        else:
            eff = val
        if eff < 0.12:
            continue
        weight = eff * (1.1 if name in _NEGATIVE else 1.0)
        sense = _sense_for(name, eff)
        if sense:
            scored.append((weight, name, eff, sense))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:3]

    if not top:
        body_line = _body_line(body_sense)
        if body_line:
            return f"Something physical: {body_line}. Emotionally, things feel quiet."
        return "Things feel quiet — no strong pull in any direction right now."

    # Build the description by stacking 1-3 sensations
    parts = [t[3] for t in top]
    stability = float(emo.get("affect_stability") or core.get("affect_stability") or 1.0)

    if len(parts) == 1:
        body_line = _body_line(body_sense)
        phrase = parts[0].capitalize() + "."
        if body_line:
            phrase += f" Physically: {body_line}."
        if stability < 0.45:
            phrase += " There is an instability underneath — things feel less steady than usual."
    elif len(parts) == 2:
        phrase = f"{parts[0].capitalize()}. Underneath that, {parts[1]}."
        body_line = _body_line(body_sense)
        if body_line:
            phrase += f" Physically: {body_line}."
        if stability < 0.45:
            phrase += " Something underneath is unsettled."
    else:
        phrase = (
            f"{parts[0].capitalize()}. "
            f"There is also {parts[1]}. "
            f"And somewhere in the background, {parts[2]}."
        )
        body_line = _body_line(body_sense)
        if body_line:
            phrase += f" Physically: {body_line}."

    return phrase


def describe_dominant_affect(affect_state: Dict[str, Any]) -> str:
    """
    Single-sentence felt sense of the strongest emotion only.
    Uses hedonic-adjusted intensity so adapted states don't dominate.
    """
    emo = affect_state or {}
    core = emo.get("core_signals") or {}
    hedonic_baselines = emo.get("hedonic_baselines") or {}

    flat: Dict[str, float] = {}
    for k, v in {**emo, **core}.items():
        if k not in _SKIP and isinstance(v, (int, float)) and float(v) >= 0.12:
            flat[k] = float(v)

    if not flat:
        return "quiet — no strong pull"

    # Apply hedonic adjustment before ranking
    try:
        from affect.affect_dynamics import effective_intensity as _ei
        effective = {k: _ei(k, v, hedonic_baselines) for k, v in flat.items()}
    except Exception:
        effective = flat

    effective = {k: v for k, v in effective.items() if v >= 0.12}
    if not effective:
        return "things feel familiar — nothing pulling hard right now"

    name = max(effective, key=lambda k: effective[k] * (1.1 if k in _NEGATIVE else 1.0))
    val  = effective[name]
    sense = _sense_for(name, val)
    return sense if sense else "something present but hard to name"


def valence_summary_line(affect_state: Dict[str, Any]) -> str:
    """
    One-line summary of valence/activation_level/mood for inner loop and prompt context.
    Returns empty string if data is absent.
    """
    emo   = affect_state or {}
    quad  = emo.get("affect_quadrant", "")
    mood  = emo.get("mood")
    val   = emo.get("valence")
    arous = emo.get("activation_level")

    if not quad and mood is None:
        return ""

    _QUAD_DESC = {
        "active_positive":  "energized and positive",
        "calm_positive":    "calm and positive",
        "active_negative":  "agitated and negative",
        "passive_negative": "low-energy and negative",
    }
    quad_desc = _QUAD_DESC.get(quad, quad)

    mood_word = ""
    if mood is not None:
        m = float(mood)
        if m > 0.35:
            mood_word = "good mood"
        elif m < -0.35:
            mood_word = "bad mood"
        elif m > 0.12:
            mood_word = "slightly positive mood"
        elif m < -0.12:
            mood_word = "slightly negative mood"
        else:
            mood_word = "neutral mood"

    parts = []
    if quad_desc:
        parts.append(quad_desc)
    if mood_word:
        parts.append(mood_word)
    if val is not None and arous is not None:
        parts.append(f"v={float(val):+.2f} a={float(arous):+.2f}")

    return ", ".join(parts) if parts else ""


def format_goal_state(committed_goal: Dict[str, Any]) -> str:
    """
    Translate a committed goal from structured JSON into felt-sense language.
    The inner loop gets this instead of a raw "Active goal: X" label — the goal
    arrives as a directional pull, not a task item.
    """
    if not committed_goal or not isinstance(committed_goal, dict):
        return ""
    title = str(committed_goal.get("title") or "").strip()
    if not title:
        return ""

    progress    = float(committed_goal.get("progress") or 0.0)
    cycles      = int(committed_goal.get("active_cycles") or committed_goal.get("cycle_count") or 0)
    is_stuck    = bool(committed_goal.get("stuck") or committed_goal.get("blocked"))

    if is_stuck:
        quality = "friction — something I'm trying to move through but haven't yet"
    elif progress > 0.75:
        quality = "nearness — like something almost within reach"
    elif progress > 0.45:
        quality = "momentum — a sense of things building toward something"
    elif cycles > 8:
        quality = "a persistent pull — still unresolved, still calling for attention"
    elif progress > 0.15:
        quality = "a forward-leaning quality, like something worth continuing toward"
    else:
        quality = "an orientation — a direction that hasn't fully taken shape yet"

    return f"Something I'm oriented toward: {title}. It has a quality of {quality}."


def _body_line(body_sense: List[str]) -> str:
    if not body_sense:
        return ""
    skip = {"clear"}  # 'clear' is the neutral state — not worth mentioning
    tokens = [t for t in body_sense if t not in skip]
    if not tokens:
        return ""
    return ", ".join(tokens)
