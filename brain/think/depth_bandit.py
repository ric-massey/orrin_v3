# brain/think/depth_bandit.py
# UCB1 bandit that learns the optimal inner-loop round count.
#
# Arms: [4, 5, 6, 7, 8] rounds.
# Reward: composite of final draft confidence + outer reward signal.
# Persisted to data/inner_loop_depth_stats.json between sessions.
#
# This is distinct from cognition/planning/thinking_depth.py, which controls
# the shallow(1) vs deep(3) chain depth for pursue_goal.  This module
# controls how many draft→critique→revise rounds the inner loop attempts.
#
# SCIENTIFIC BASIS:
#   Auer, Cesa-Bianchi & Fischer (2002) — "Finite-time analysis of the
#   multiarmed bandit problem." Machine Learning, 47, 235–256.
#   UCB1 formula: score = avg_reward + C * sqrt(log(N) / n_i)
#   where _UCB_C = 1.4 is the exploration coefficient.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import math
from typing import Dict, List

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_STATS_FILE = DATA_DIR / "inner_loop_depth_stats.json"
_ROUND_ARMS: List[int] = [4, 5, 6, 7, 8]
_UCB_C: float = 1.4     # exploration coefficient
_SEED_MIN: int = 2       # minimum observations before UCB1 takes over


def _load() -> Dict[str, Dict[str, float]]:
    raw = load_json(_STATS_FILE, default_type=dict) or {}
    out: Dict[str, Dict[str, float]] = {}
    for arm in _ROUND_ARMS:
        key = str(arm)
        blk = raw.get(key, {})
        out[key] = {
            "count":      float(blk.get("count",      0)),
            "total":      float(blk.get("total",      0)),
            "avg_reward": float(blk.get("avg_reward", 0.5)),
        }
    return out


def _save(stats: Dict[str, Dict[str, float]]) -> None:
    try:
        save_json(_STATS_FILE, stats)
    except Exception as _e:
        record_failure("depth_bandit._save", _e)


def choose_rounds() -> int:
    """
    UCB1 selection over round-count arms.
    Returns the number of inner-loop rounds to allocate.
    Falls back to 4 (minimum) on any error.
    """
    try:
        stats = _load()
        # Seed phase: give each arm _SEED_MIN observations in ascending order
        for arm in _ROUND_ARMS:
            if stats[str(arm)]["count"] < _SEED_MIN:
                return arm

        total = sum(s["count"] for s in stats.values())
        best_arm, best_ucb = _ROUND_ARMS[0], -1.0
        for arm in _ROUND_ARMS:
            s = stats[str(arm)]
            if s["count"] == 0:
                return arm
            ucb = s["avg_reward"] + _UCB_C * math.sqrt(math.log(total) / s["count"])
            if ucb > best_ucb:
                best_ucb = ucb
                best_arm = arm

        log_private(
            f"[depth_bandit/inner] → rounds={best_arm} | "
            + " ".join(f"r{a}:{stats[str(a)]['avg_reward']:.2f}(n={int(stats[str(a)]['count'])})"
                       for a in _ROUND_ARMS)
        )
        return best_arm
    except Exception as _e:
        record_failure("depth_bandit.choose_rounds", _e)
        return 4


def record_outcome(rounds_used: int, reward: float) -> None:
    """
    Update bandit with the composite reward for a completed inner-loop run.
    reward should be in [-1.0, 1.0]; clipped internally.
    """
    try:
        r = max(-1.0, min(1.0, float(reward)))
        stats = _load()
        key = str(rounds_used)
        if key not in {str(a) for a in _ROUND_ARMS}:
            return   # arm outside expected range — ignore
        s = stats.setdefault(key, {"count": 0, "total": 0, "avg_reward": 0.5})
        s["count"]     += 1
        s["total"]     += r
        s["avg_reward"] = s["total"] / s["count"]
        _save(stats)
        log_private(
            f"[depth_bandit/inner] recorded rounds={rounds_used} reward={r:.3f} "
            f"→ avg={s['avg_reward']:.3f} (n={int(s['count'])})"
        )
    except Exception as _e:
        record_failure("depth_bandit.record_outcome", _e)


def arm_summary() -> Dict[str, Dict]:
    """Return a readable snapshot for dashboards / logs."""
    try:
        return _load()
    except Exception as _e:
        record_failure("depth_bandit.arm_summary", _e)
        return {}
