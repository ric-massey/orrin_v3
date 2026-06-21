# cognition/planning/thinking_depth.py
# UCB1 bandit for choosing reasoning depth: 1 (shallow) vs 3 (deep, 3-step chain).
#
# NOTE: As of the inner-loop architecture, meta_controller.py is the primary
# decision-maker for "think_more vs act vs output vs defer". This module is
# downgraded to a signal provider: depth_as_signal() returns a float that
# meta_controller reads as one input alongside confidence and debt.
# choose_depth() is retained for direct callers (pursue_goal) and for seeding
# the bandit stats that depth_as_signal() reads.
#
# Scientific basis:
#   UCB1 (Auer et al., 2002) balances exploitation of known-good depths with
#   exploration of under-tried ones. The "depth" meta-parameter maps directly to
#   computational cost vs reasoning quality — the bandit learns the tradeoff.
#
#   Reward is the environment-delta score computed by ORRIN_loop after each
#   pursue_committed_goal step.  pursue_goal stashes the chosen depth on
#   context["_pursue_goal_depth"]; ORRIN_loop calls update_depth(depth, reward)
#   after the env snapshot so the bandit trains on real state change, not text.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import math
from typing import Dict

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_DEPTH_STATS_FILE = DATA_DIR / "depth_stats.json"
_DEPTHS = [1, 3]  # 1 = single LLM call, 3 = question→reason→plan chain
_UCB_C  = 1.5     # UCB exploration constant — higher = more exploration


def _load_stats() -> Dict[str, Dict[str, float]]:
    raw = load_json(_DEPTH_STATS_FILE, default_type=dict) or {}
    out = {}
    for d in _DEPTHS:
        key = str(d)
        block = raw.get(key, {})
        out[key] = {
            "count":      float(block.get("count", 0)),
            "total":      float(block.get("total", 0)),
            "avg_reward": float(block.get("avg_reward", 0.5)),
        }
    return out


def _save_stats(stats: Dict[str, Dict[str, float]]) -> None:
    save_json(_DEPTH_STATS_FILE, stats)


def choose_depth() -> int:
    """
    UCB1 selection over available depths.
    Returns 1 (shallow) or 3 (deep). Falls back to 1 if stats unavailable.
    """
    try:
        stats = _load_stats()
        total_count = sum(v["count"] for v in stats.values())
        if total_count < len(_DEPTHS) * 2:
            # Not enough data yet — round-robin to seed all arms
            for d in _DEPTHS:
                if stats[str(d)]["count"] == 0:
                    return d
            return _DEPTHS[0]

        best_depth, best_score = _DEPTHS[0], -1.0
        for d in _DEPTHS:
            s = stats[str(d)]
            if s["count"] == 0:
                return d
            ucb = s["avg_reward"] + _UCB_C * math.sqrt(math.log(total_count) / s["count"])
            if ucb > best_score:
                best_score = ucb
                best_depth = d

        log_private(f"[depth_bandit] chose depth={best_depth} (UCB scores: "
                    + ", ".join(f"d{d}={stats[str(d)]['avg_reward']:.2f}" for d in _DEPTHS) + ")")
        return best_depth
    except Exception:
        return 1


def update_depth(depth: int, reward: float) -> None:
    """Record outcome for a given depth choice."""
    try:
        stats = _load_stats()
        key = str(depth)
        if key not in stats:
            stats[key] = {"count": 0, "total": 0, "avg_reward": 0.5}
        s = stats[key]
        s["count"]  += 1
        s["total"]  += reward
        s["avg_reward"] = s["total"] / s["count"]
        _save_stats(stats)
        log_private(f"[depth_bandit] updated depth={depth} reward={reward:.3f} "
                    f"→ avg={s['avg_reward']:.3f} (n={int(s['count'])})")
    except Exception as _e:
        record_failure("thinking_depth.update_depth", _e)


# ── Depth-as-signal for meta_controller ─────────────────────────────────────

def depth_as_signal() -> float:
    """
    Returns 0.0–1.0 representing how much the bandit history favours deep thinking.
    0.5 = neutral / insufficient data.
    Used by meta_controller.py as one input among several.
    """
    try:
        stats = _load_stats()
        deep_avg  = stats.get("3", {}).get("avg_reward", 0.5)
        shal_avg  = stats.get("1", {}).get("avg_reward", 0.5)
        deep_n    = stats.get("3", {}).get("count", 0)
        shal_n    = stats.get("1", {}).get("count", 0)
        if deep_n < 2 or shal_n < 2:
            return 0.5  # not enough data to have a view
        return max(0.0, min(1.0, 0.5 + (deep_avg - shal_avg)))
    except Exception:
        return 0.5


