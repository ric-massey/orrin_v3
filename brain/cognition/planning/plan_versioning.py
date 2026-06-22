"""Plan drift-scoring + versioning helpers (Phase 4D, from pursue_goal.py).

The plan-bookkeeping slice of goal pursuit: _score_drift turns an assessment
string into a [0,1] drift severity, and _save_plan_version /
_rollback_plan_version snapshot and restore a goal's plan (capped history) so a
bad replan can be undone. Self-contained — operate on goal dicts + text only.
pursue_goal re-imports them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain.core.runtime_log import get_logger
from brain.utils.log import log_activity

_log = get_logger(__name__)


_DRIFT_STRONG   = frozenset({"completely off track", "fundamentally wrong", "abandon",
                              "wrong direction", "stalled completely", "no progress",
                              "going nowhere", "hopeless", "irrelevant"})
_DRIFT_MODERATE = frozenset({"off track", "stalled", "not converging", "drift",
                              "not working", "replanning", "blocked", "failed",
                              "pivot", "reconsi", "ineffective", "slow progress"})
_DRIFT_MILD     = frozenset({"minor issue", "slight", "could improve", "somewhat",
                              "not ideal", "room for improvement"})


def _score_drift(assessment_text: str) -> float:
    """
    Return drift severity in [0.0, 1.0].
    0.0 = on track, 1.0 = completely derailed.
    """
    lower = (assessment_text or "").lower()
    if any(s in lower for s in _DRIFT_STRONG):
        return 0.85
    if any(s in lower for s in _DRIFT_MODERATE):
        return 0.55
    if any(s in lower for s in _DRIFT_MILD):
        return 0.22
    return 0.0


# ── Plan versioning ───────────────────────────────────────────────────────────

_MAX_PLAN_VERSIONS = 5


def _save_plan_version(goal: Dict[str, Any], reason: str = "") -> None:
    """Snapshot current plan into goal["_plan_versions"] before overwriting."""
    current_plan = list(goal.get("plan") or [])
    if not current_plan:
        return
    versions: List[Dict] = list(goal.get("_plan_versions") or [])
    versions.append({
        "version":    len(versions),
        "steps":      current_plan,
        "saved_at":   datetime.now(timezone.utc).isoformat(),
        "reason":     reason,
    })
    goal["_plan_versions"] = versions[-_MAX_PLAN_VERSIONS:]


def _rollback_plan_version(goal: Dict[str, Any], version_idx: int = -1) -> bool:
    """
    Restore a previous plan version.
    version_idx=-1 (default) restores the most recent snapshot.
    Returns True on success.
    """
    versions: List[Dict] = goal.get("_plan_versions") or []
    if not versions:
        return False
    target = versions[version_idx]
    goal["plan"] = list(target.get("steps") or [])
    goal["_rollback_from"] = target.get("version")
    log_activity(
        f"[pursue_goal] Rolled back plan to version {target.get('version')} "
        f"({target.get('reason', '?')})"
    )
    return True
