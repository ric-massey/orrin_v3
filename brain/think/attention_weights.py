# brain/think/attention_weights.py
# reward_signal-driven signal_router plasticity: when a cycle produces high reward,
# the signal sources that were routed to attention get their learned weights
# bumped. Over time, sources that reliably precede high reward get higher
# intrinsic credibility in the signal_router, accelerating routing.
#
# Analogy: reward_signal projections to the signal_router modulating which channels
# stay open based on reward history — reward-driven routing-weight plasticity.
from __future__ import annotations

from typing import Dict, List, Any

from utils.json_utils import load_json, save_json
from utils.log import log_private

from paths import DATA_DIR
_WEIGHTS_PATH = DATA_DIR / "attention_value_weights.json"

_LR_POS = 0.06   # learning rate when reward > threshold
_LR_NEG = 0.03   # learning rate when reward < threshold (slower unlearning)
_REWARD_THRESHOLD = 0.55
_DECAY = 0.995   # slow global decay so unused sources fade


def update_attention_weights(context: Dict[str, Any], reward: float) -> None:
    """
    Called by finalize_cycle after the reward is known.

    Reads the signal sources that were active this cycle from context
    (stored by the signal_router as context["_active_signal_sources"]), and
    bumps or dampens their weights depending on whether reward exceeded
    the threshold.
    """
    sources: List[str] = list(context.get("_active_signal_sources") or [])
    if not sources:
        return

    weights: Dict[str, float] = load_json(_WEIGHTS_PATH, default_type=dict) or {}
    if not isinstance(weights, dict):
        weights = {}

    reward = float(reward)
    is_positive = reward >= _REWARD_THRESHOLD

    # Global decay first — all sources fade slightly each call so stale
    # associations from old context don't persist forever.
    for src in list(weights.keys()):
        weights[src] = max(0.0, weights[src] * _DECAY)

    for src in sources:
        current = float(weights.get(src, 0.5))
        if is_positive:
            delta = _LR_POS * (1.0 - current)   # asymptote at 1.0
        else:
            delta = -_LR_NEG * current           # asymptote at 0.0
        weights[src] = max(0.0, min(1.0, current + delta))

    try:
        save_json(_WEIGHTS_PATH, weights)
        log_private(f"[attention_weights] updated {len(sources)} source(s), reward={reward:.3f}")
    except Exception as e:
        log_private(f"[attention_weights] save failed: {e}")


def get_source_weight(source: str) -> float:
    """Return the learned attention value weight for a signal source (0-1)."""
    try:
        weights: Dict[str, float] = load_json(_WEIGHTS_PATH, default_type=dict) or {}
        return float(weights.get(source, 0.5))
    except Exception:
        return 0.5
