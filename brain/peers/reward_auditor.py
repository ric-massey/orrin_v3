"""
peers/reward_auditor.py  —  The Reward Auditor

Watches whether the bandit is actually learning meaningful distinctions,
or whether the reward signal has collapsed to noise.

Analogy: a coach who notices when an athlete keeps drilling the same
movement but the numbers show no improvement.  "You think you're
practicing.  Are you?"

Wakes every 50 cycles, or when action_debt is high (stalled on a goal
without learning anything from it).
"""
from __future__ import annotations
from core.runtime_log import get_logger

import json
from typing import Any, Dict, List

from peers.peer_base import BasePeer
from brain.paths import BANDIT_STATE_FILE, EVALUATOR_WAL, REWARD_TRACE
from utils.failure_counter import record_failure
_log = get_logger(__name__)


class RewardAuditor(BasePeer):
    name = "reward_auditor"
    description = "a presence that watches whether I'm actually learning from outcomes"
    trust = 0.62
    signal_tags = ["peer", "reward_auditor", "internal"]

    def should_wake(self, context: Dict[str, Any], cycle: int) -> bool:
        if context.get("_impasse_reason"):
            return True
        if cycle % 50 == 0:
            return True
        debt = int(context.get("action_debt", 0) or 0)
        if debt >= 4:
            return True
        return False

    def observe(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        # ── WAL resolution rate ───────────────────────────────────────────────
        try:
            wal_entries = []
            path = EVALUATOR_WAL
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                wal_entries.append(json.loads(line))
                            except Exception as _e:
                                record_failure("reward_auditor.RewardAuditor.observe", _e)

            recent = wal_entries[-40:] if len(wal_entries) >= 40 else wal_entries
            if len(recent) >= 10:
                resolved = sum(1 for e in recent if e.get("resolved"))
                rate = resolved / len(recent)
                if rate < 0.25:
                    signals.append(self._signal(
                        f"Most of what I've been trying hasn't resolved into clear "
                        f"feedback yet — only {int(rate * 100)}% of recent decisions "
                        f"have come back with outcomes. "
                        f"I may not be learning what I think I'm learning.",
                        strength=0.68,
                        extra_tags=["learning", "wal"],
                    ))
        except Exception as _e:
            record_failure("reward_auditor.RewardAuditor.observe.2", _e)

        # ── Reward variance (flat signal = bandit can't differentiate) ────────
        try:
            from utils.json_utils import load_json
            trace = load_json(REWARD_TRACE, default_type=list) or []
            if isinstance(trace, list) and len(trace) >= 15:
                recent_rewards = []
                for e in trace[-20:]:
                    if isinstance(e, dict):
                        r = e.get("reward") or e.get("value")
                        if isinstance(r, (int, float)):
                            recent_rewards.append(float(r))
                if len(recent_rewards) >= 10:
                    lo, hi = min(recent_rewards), max(recent_rewards)
                    spread = hi - lo
                    avg = sum(recent_rewards) / len(recent_rewards)
                    if spread < 0.20 and 0.40 < avg < 0.65:
                        signals.append(self._signal(
                            f"My feedback signals have been nearly flat — "
                            f"rewards clustering between {lo:.2f} and {hi:.2f}. "
                            f"I'm receiving similar signals for very different choices. "
                            f"The distinction isn't landing.",
                            strength=0.64,
                            extra_tags=["learning", "variance"],
                        ))
        except Exception as _e:
            record_failure("reward_auditor.RewardAuditor.observe.3", _e)

        # ── Bandit imbalance: one arm dominating counts ───────────────────────
        try:
            from utils.json_utils import load_json
            bstate = load_json(BANDIT_STATE_FILE, default_type=dict) or {}
            counts = bstate.get("counts") or bstate.get("n") or {}
            if isinstance(counts, dict) and len(counts) >= 4:
                total = sum(float(v) for v in counts.values() if isinstance(v, (int, float)))
                if total > 0:
                    top_arm = max(counts, key=lambda k: float(counts[k] or 0))
                    top_frac = float(counts[top_arm]) / total
                    if top_frac >= 0.55:
                        signals.append(self._signal(
                            f"My reinforcement patterns show heavy concentration — "
                            f"'{top_arm}' accounts for {int(top_frac * 100)}% of all "
                            f"choices recorded. Other paths are being starved of feedback.",
                            strength=0.62,
                            extra_tags=["learning", "bandit"],
                        ))
        except Exception as _e:
            record_failure("reward_auditor.RewardAuditor.observe.4", _e)

        return signals
