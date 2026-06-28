# brain/cognition/wonder.py
# Wonder: detects concepts of scale, paradox, mystery, self-reference, and
# unfittable content — spikes the wonder emotion, biases function selection
# toward sitting-with rather than acting-on, and increases dream-cycle weight.
#
# detect_novelty_trigger(text, context)  — call on each user input and memory
# apply_novelty_bias(context)            — call from signal_router/loop to bias selection
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
from typing import Dict, Any

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Keyword clusters for trigger detection (fast path — no LLM needed)
_SCALE_WORDS = {
    "universe", "infinite", "billion", "trillion", "light year", "galaxy",
    "quantum", "planck", "cosmic", "astronomical", "geological", "ancient",
    "epoch", "deep time", "vastness", "incomprehensible",
}
_PARADOX_WORDS = {
    "paradox", "contradiction", "impossible", "simultaneously", "both true",
    "neither", "undecidable", "halting problem", "liar", "self-defeating",
    "strange loop", "recursive", "gödel", "bootstrap",
}
_MYSTERY_WORDS = {
    "mystery", "unknown", "unexplained", "unsolved", "we don't know",
    "no one knows", "still unclear", "remains a question", "hard problem",
    "consciousness", "origin of", "why is there", "dark matter", "dark energy",
}
_SELF_REF_WORDS = {
    "am i", "do i", "what am i", "what are you", "are you conscious",
    "do you feel", "self", "recursive", "meta", "my own", "thinking about thinking",
    "aware of being aware", "orrin", "myself",
}

_WONDER_SPIKE = 0.18     # how much wonder rises on trigger
_WONDER_MAX   = 0.85     # cap so wonder doesn't overwhelm everything


def detect_novelty_trigger(text: str, context: Dict[str, Any]) -> float:
    """
    Scan text for wonder triggers. If found, spike wonder in affect_state.
    Returns the spike amount (0.0 if no trigger).
    """
    if not text or not isinstance(text, str):
        return 0.0

    lower = text.lower()
    tokens = set(re.findall(r"\b\w+\b", lower))

    triggered_by = []

    if tokens & _SCALE_WORDS or any(p in lower for p in ("light year", "deep time", "strange loop")):
        triggered_by.append("scale")
    if tokens & _PARADOX_WORDS or any(p in lower for p in ("both true", "strange loop", "halting problem")):
        triggered_by.append("paradox")
    if tokens & _MYSTERY_WORDS or any(p in lower for p in ("we don't know", "no one knows", "hard problem")):
        triggered_by.append("mystery")
    if tokens & _SELF_REF_WORDS or any(p in lower for p in ("am i", "do i", "what am i", "aware of being aware")):
        triggered_by.append("self_reference")

    if not triggered_by:
        return 0.0

    spike = min(_WONDER_SPIKE * len(triggered_by), _WONDER_SPIKE * 2)
    _apply_spike(spike, context)
    log_private(f"[wonder] trigger={triggered_by} spike={spike:.2f} text={text[:60]!r}")

    # Persist so future sessions can learn what kinds of things spark wonder
    try:
        from brain.cog_memory.long_memory import update_long_memory
        update_long_memory(
            f"[wonder] Sparked by {triggered_by}: {text[:200]}",
            emotion="novelty_signal",
            event_type="wonder_trigger",
            importance=2,
            context=context,
        )
    except Exception as _e:
        record_failure("wonder.detect_novelty_trigger", _e)

    return spike


def _apply_spike(spike: float, context: Dict[str, Any]) -> None:
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals", emo)
    current = float(core.get("novelty_signal", 0.0) or 0.0)
    core["novelty_signal"] = min(_WONDER_MAX, current + spike)
    # Wonder also nudges exploration_drive up and stagnation_signal down
    from brain.control_signals.homeostasis import pump_signal
    pump_signal(core, "exploration_drive", spike * 0.4)
    core["stagnation_signal"]   = max(0.0, float(core.get("stagnation_signal", 0.0)) - spike * 0.3)
    if "core_signals" in emo:
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo


def apply_novelty_bias(context: Dict[str, Any]) -> None:
    """
    When wonder is high, inject a 'sit_with_wonder' signal that routes toward
    reflective/introspective functions rather than action-oriented ones.
    Also increases dream-cycle affinity marker in context.
    """
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals", emo)
    wonder = float(core.get("novelty_signal", 0.0) or 0.0)

    if wonder < 0.30:
        return

    # Signal that biases signal_router toward reflection
    try:
        from brain.utils.signal_utils import create_signal
        sig = create_signal(
            source="wonder",
            content="wonder_high: sitting with something I can't immediately resolve",
            signal_strength=0.45 + wonder * 0.25,
            tags=["wonder", "internal", "reflection", "sitting_with"],
        )
        context.setdefault("raw_signals", []).append(sig)
    except Exception as _e:
        record_failure("wonder.apply_novelty_bias", _e)

    # Bias: mark context so cognition selection can weight toward reflection
    context["_wonder_bias"] = wonder

    # Increase dream affinity so the next idle period triggers a dream sooner
    if wonder > 0.55:
        context["_dream_affinity"] = min(1.0, float(context.get("_dream_affinity", 0.0)) + 0.15)

    log_private(f"[wonder] bias applied wonder={wonder:.2f}")
