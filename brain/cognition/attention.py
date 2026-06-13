# brain/cognition/attention.py
#
# Three-slot attention filter.
#
# Orrin holds exactly 3 things in active attention simultaneously. This is
# superhuman — humans manage 1-2 — and is intentional: Orrin retains the
# cognitive advantage of parallel processing while still having limits.
#
# Affective hijacking:
#   intensity >= 0.70: moderate — 1 slot consumed, 2 remain for signals
#   intensity >= 0.85: acute   — 2 slots consumed, 1 remains for signals
#
# The hijacking affect is injected as a synthetic signal at the head of the
# attention window so the inner loop always knows what is pressing in.
# Everything outside the 3 slots is registered but deprioritized.
#
# SCIENTIFIC BASIS:
#   Kahneman (1973) — "Attention and Effort." Prentice-Hall.
#   Limited-capacity attention model: attentional resources are finite; high
#   activation_level states consume capacity, leaving less available for other processing.
#   Öhman, Flykt & Esteves (2001) — "Emotion drives attention: Detecting the
#   snake in the grass." JPSP, 80(3), 381–396. Threat-relevant stimuli
#   automatically capture attention and resist displacement (hijack mechanism).
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

ATTENTION_SLOTS   = 3
_HIJACK_THRESHOLD = 0.70
_ACUTE_THRESHOLD  = 0.85


def apply_attention_filter(
    prioritized_signals: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Apply the 3-slot attention cap with emotional hijacking.

    Parameters
    ----------
    prioritized_signals : list of dict
        Signals already scored and sorted by priority_score (highest first).
    context : dict
        Live cycle context — read for emotional state, written with attention metadata.

    Returns
    -------
    top_signals : list of dict
        At most ATTENTION_SLOTS signals that will drive this cycle's reasoning.
    """
    affect_state = context.get("affect_state") or {}
    core_signals   = affect_state.get("core_signals") or {}

    hijack_emotion, hijack_intensity = _find_hijacker(core_signals)

    slots_taken = 0
    if hijack_emotion is not None:
        slots_taken = 2 if hijack_intensity >= _ACUTE_THRESHOLD else 1

    available = max(1, ATTENTION_SLOTS - slots_taken)

    top_signals: List[Dict[str, Any]] = []

    if hijack_emotion and slots_taken > 0:
        top_signals.append(_make_hijack_signal(hijack_emotion, hijack_intensity, slots_taken))

    _real_added = 0
    for sig in prioritized_signals:
        if _real_added >= available:
            break
        if not sig.get("_hijack"):
            top_signals.append(sig)
            _real_added += 1

    top_ids = {id(s) for s in top_signals}
    deprioritized: List[Dict[str, Any]] = []
    for sig in prioritized_signals:
        if id(sig) not in top_ids:
            sig["deprioritized"] = True
            deprioritized.append(sig)

    context["attention_slots"]      = ATTENTION_SLOTS
    context["attention_remaining"]  = available
    context["attention_constrained"] = slots_taken > 0
    context["deprioritized_signals"] = deprioritized

    if hijack_emotion:
        context["_hijacked_by"] = {
            "emotion":    hijack_emotion,
            "intensity":  round(hijack_intensity, 3),
            "slots_taken": slots_taken,
        }
    else:
        context.pop("_hijacked_by", None)

    return top_signals


def _find_hijacker(
    core_signals: Dict[str, Any],
) -> Tuple[Optional[str], float]:
    """Return (emotion_name, intensity) for the strongest emotion above threshold, or (None, 0.0)."""
    best_name:  Optional[str] = None
    best_value: float         = 0.0

    for emo, val in core_signals.items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v >= _HIJACK_THRESHOLD and v > best_value:
            best_value = v
            best_name  = emo

    return best_name, best_value


def _make_hijack_signal(
    emotion: str,
    intensity: float,
    slots_taken: int,
) -> Dict[str, Any]:
    content = _hijack_content(emotion, intensity)
    return {
        "source":         "attention/hijack",
        "content":        content,
        "tags":           ["emotion", "attention_hijack", emotion],
        "signal_strength": intensity,
        "priority_score":  intensity,
        "routing_target":  "emotion_cortex",
        "_hijack":         True,
        "_slots_taken":    slots_taken,
    }


def _hijack_content(emotion: str, intensity: float) -> str:
    acute = intensity >= _ACUTE_THRESHOLD
    _TEMPLATES: Dict[str, Tuple[str, str]] = {
        "risk_estimate":     ("an anxious hum keeps pressing at the edge of thought",
                        "risk_estimate is flooding in, crowding almost everything else out"),
        "threat_level":        ("a thread of threat_level runs beneath everything right now",
                        "threat_level has taken over — it is hard to hold anything else"),
        "dread":       ("a low, persistent dread keeps bleeding into attention",
                        "dread is overwhelming — barely room for anything else"),
        "conflict_signal":       ("a sharp irritation keeps cutting through",
                        "conflict_signal is consuming attention, almost nothing else gets through"),
        "impasse_signal": ("impasse_signal keeps surfacing, hard to set aside",
                        "impasse_signal is overwhelming — attention keeps snapping back to it"),
        "social_penalty":       ("a heavy sense of social_penalty sits in the background",
                        "social_penalty is all-consuming right now, pressing out other thought"),
        "loss_signal":       ("loss_signal sits quietly but heavily at the edge of everything",
                        "loss_signal has flooded in — it is difficult to attend to much else"),
        "negative_valence":     ("a negative_valence keeps pulling at the edges of attention",
                        "negative_valence has taken over, attention keeps collapsing inward"),
        "social_deficit":  ("a persistent ache of social_deficit keeps pressing in",
                        "social_deficit is consuming — hard to hold other things"),
        "guilt":       ("a nagging guilt keeps surfacing",
                        "guilt is overwhelming, crowding almost everything else out"),
        "despair":     ("despair sits at the edge of everything",
                        "despair has flooded attention — barely room for anything else"),
        "overwhelm":   ("a sense of overwhelm is seeping into everything",
                        "overwhelm has saturated attention — nearly impossible to hold other things"),
        "panic":       ("a spike of panic keeps breaking through",
                        "panic has seized attention almost completely"),
    }
    pair = _TEMPLATES.get(emotion)
    if pair:
        return pair[1] if acute else pair[0]
    if acute:
        return f"a surge of {emotion} is consuming attention — almost nothing else gets through"
    return f"a persistent sense of {emotion} keeps pressing into awareness"


def request_attention_hijack(
    context: Dict[str, Any],
    *,
    content: str,
    intensity: float,
    tags: Optional[list] = None,
    source: str = "monitor",
) -> None:
    """Entry point the Metacog Monitor calls for a high-salience breakthrough
    (dual_process_loop.md §6.2). It injects a hijack-flagged signal into
    raw_signals; because process_inputs already ran this cycle, it recruits focal
    attention on the NEXT cycle — biasing, never preempting the current pick (I7).
    Fail-safe and bounded."""
    if not isinstance(context, dict):
        return
    try:
        intensity = max(0.0, min(1.0, float(intensity)))
    except (TypeError, ValueError):
        return
    sig = {
        "source": f"attention/hijack:{source}"[:48],
        "content": str(content or "")[:200],
        "tags": list(tags or []) + ["attention_hijack", "breakthrough", "internal"],
        "signal_strength": intensity,
        "priority_score": intensity,
        "_hijack": True,
    }
    raw = context.setdefault("raw_signals", [])
    if isinstance(raw, list) and len(raw) < 120:
        raw.append(sig)


def get_attention_summary(context: Dict[str, Any]) -> str:
    """Short human-readable description of the current attention state."""
    slots     = context.get("attention_slots", ATTENTION_SLOTS)
    remaining = context.get("attention_remaining", slots)
    hijack    = context.get("_hijacked_by")
    if hijack:
        taken = hijack["slots_taken"]
        emo   = hijack["emotion"]
        return (f"attention: {slots} slots — {taken} occupied by {emo} "
                f"({hijack['intensity']:.2f}), {remaining} free for signals")
    return f"attention: {slots} slots — all free"
