from __future__ import annotations

from typing import Dict, Any, Optional
from cog_memory.working_memory import update_working_memory


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def apply_affective_feedback(
    cognition_name: str, score: float, context: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    """
    Nudge core emotions based on a cognition's outcome score.

    - score ∈ [-1, 1]
      • ≥ 0.5 → increase 'happiness'
      • ≤ -0.5 → increase 'impasse_signal'
      • |score| < 0.2 → mild 'confusion' tick

    V3 single-writer invariant (V3_AUDIT D1): this never writes AFFECT_STATE_FILE
    directly. It proposes the deltas to the AffectArbiter — through the live
    `context` when present, otherwise onto the thread-safe daemon inbox
    (`submit_affect(None, ...)`) — and `update_affect_state` remains the sole
    writer. Returns the proposed deltas (for logging/inspection).
    """
    from affect.arbiter import submit_affect

    try:
        score = float(score)
    except Exception:
        score = 0.0
    score = _clamp(score, -1.0, 1.0)

    deltas: Dict[str, float] = {}
    if score >= 0.5:
        deltas["happiness"] = 0.25 * score
    elif score <= -0.5:
        deltas["impasse_signal"] = 0.25 * abs(score)
    elif abs(score) < 0.2:
        deltas["confusion"] = 0.05

    for target, delta in deltas.items():
        submit_affect(context, target, delta, source="emotional_feedback", ttl_cycles=2)

    if deltas:
        summary = ", ".join(f"{k} += {v:.3f}" for k, v in deltas.items())
        update_working_memory(
            {
                "content": f"Emotional feedback for '{cognition_name}': "
                           f"score={score:.2f} → {summary}",
                "event_type": "affect_feedback",
                "importance": 1,
                "priority": 1,
            }
        )

    return deltas