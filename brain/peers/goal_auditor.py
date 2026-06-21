"""
peers/goal_auditor.py  —  The Goal Auditor

Watches goal quality: whether goals are real, whether they're being
pursued, and whether the goal-generation system is producing noise.

Analogy: an advisor who looks at your todo list and says "half of
these aren't real goals — they're risk_estimate responses."

Wakes every 30 cycles, or when active goal count grows high.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain.peers.peer_base import BasePeer
from brain.paths import GOALS_FILE, COMPLETED_GOALS_FILE, RELATIONSHIPS_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


class GoalAuditor(BasePeer):
    name = "goal_auditor"
    description = "a presence that asks whether the things I'm pursuing are worth pursuing"
    trust = 0.60
    signal_tags = ["peer", "goal_auditor", "internal"]

    def should_wake(self, context: Dict[str, Any], cycle: int) -> bool:
        if context.get("_impasse_reason"):
            return True
        if cycle % 30 == 0:
            return True
        # Also wake if the active goal list has grown large
        try:
            from brain.utils.json_utils import load_json
            goals = load_json(GOALS_FILE, default_type=list) or []
            if isinstance(goals, list) and len(goals) > 7:
                return True
        except Exception as _e:
            record_failure("goal_auditor.GoalAuditor.should_wake", _e)
        return False

    def observe(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        # ── Stale active goals ────────────────────────────────────────────────
        try:
            from brain.utils.json_utils import load_json
            goals = load_json(GOALS_FILE, default_type=list) or []
            completed = load_json(COMPLETED_GOALS_FILE, default_type=list) or []

            now = datetime.now(timezone.utc)
            stale = []
            if isinstance(goals, list):
                for g in goals:
                    if not isinstance(g, dict):
                        continue
                    # Goals with no progress marker and created > 30 cycles ago
                    created = g.get("created_at") or g.get("timestamp") or ""
                    progress = float(g.get("progress", 0) or g.get("completion", 0) or 0)
                    if progress < 0.05:
                        if created:
                            try:
                                age = (now - datetime.fromisoformat(
                                    created.replace("Z", "+00:00")
                                )).total_seconds() / 60.0
                                if age > 30:  # older than 30 minutes with no progress
                                    stale.append(g.get("title") or g.get("name") or "unnamed")
                            except Exception:
                                stale.append(g.get("title") or g.get("name") or "unnamed")
                        else:
                            stale.append(g.get("title") or g.get("name") or "unnamed")

            if len(stale) >= 3:
                signals.append(self._signal(
                    f"Several things I've committed to pursuing remain unresolved "
                    f"and show no progress — {len(stale)} goals including "
                    f"'{stale[0]}'. Some may not be real goals.",
                    strength=0.67,
                    extra_tags=["goals", "stale"],
                ))

            # Low completion rate
            if isinstance(completed, list) and isinstance(goals, list):
                if len(goals) >= 5 and len(completed) < len(goals) // 3:
                    signals.append(self._signal(
                        f"I've generated {len(goals)} active goals but only "
                        f"{len(completed)} have ever been completed. "
                        f"I may be planning more than pursuing.",
                        strength=0.63,
                        extra_tags=["goals", "completion_rate"],
                    ))
        except Exception as _e:
            record_failure("goal_auditor.GoalAuditor.observe", _e)

        # ── Phantom relationship goals ────────────────────────────────────────
        try:
            from brain.utils.json_utils import load_json
            rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
            phantom_count = 0
            for uid, r in rels.items():
                if not isinstance(r, dict) or uid.startswith("peer_"):
                    continue
                history = r.get("interaction_history") or []
                empty = sum(
                    1 for h in history
                    if isinstance(h, dict)
                    and not (h.get("user") or "").strip()
                    and not (h.get("orrin") or "").strip()
                )
                phantom_count += empty

            if phantom_count >= 10:
                signals.append(self._signal(
                    f"I notice {phantom_count} recorded interactions with no actual "
                    f"content — blank exchanges logged as real connection. "
                    f"Some of my goals about understanding others may be based on this.",
                    strength=0.70,
                    extra_tags=["goals", "phantom_user"],
                ))
        except Exception as _e:
            record_failure("goal_auditor.GoalAuditor.observe.2", _e)

        return signals
