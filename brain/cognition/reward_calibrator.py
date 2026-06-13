"""
cognition/reward_calibrator.py

Rebalances Orrin's learning signal away from retrieval-driven reinforcement
toward grounded, external signals.

The core problem: the bandit rewards functions whose outputs are retrieved
later. Emotionally charged / narratively coherent outputs are highly
retrievable → get reinforced → dominate behavior. Ideas survive because
they *spread*, not because they are true or useful.

Fix: introduce four primary reward sources that do not depend on retrieval,
and cap the retrievability contribution to a weak auxiliary signal.

Primary reward sources (sum to 1.0):
  - goal_closure    0.35  — goal marked completed this cycle
  - user_validation 0.30  — explicit positive user signal
  - prediction_hit  0.20  — predictions were correct (measured by prediction.py)
  - contradiction_resolved 0.15 — a known contradiction was resolved

Auxiliary (formerly primary — now capped):
  - retrieval_boost  max +0.08  — memory was retrieved (down from uncapped)

This module does NOT replace the existing reward signals file — it wraps
`release_reward_signal()` with calibrated weights and provides a
`calibrated_reward()` entry point for high-level cognition.
"""
from __future__ import annotations
from core.runtime_log import get_logger

from typing import Any, Dict

from utils.log import log_activity
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Weight constants (must sum to ≤ 1.0 for primary sources) ──────────────────
_W_GOAL_CLOSURE          = 0.35
_W_USER_VALIDATION       = 0.30
_W_PREDICTION_HIT        = 0.20
_W_CONTRADICTION_RESOLVED = 0.15
_W_RETRIEVAL_MAX         = 0.08   # hard cap on retrieval-based reward


def calibrated_reward(
    context: Dict[str, Any],
    goal_closed: bool = False,
    user_positive: bool = False,
    prediction_accuracy: float = 0.0,  # 0.0–1.0
    contradictions_resolved: int = 0,
    retrieval_count: int = 0,
    source: str = "calibrated",
) -> float:
    """
    Compute and release a calibrated reward signal into the pipeline.

    Returns the total reward value released (for logging).
    """
    reward = 0.0

    if goal_closed:
        _r = _W_GOAL_CLOSURE
        reward += _r
        _release(context, "goal_closure", _r, source)

    if user_positive:
        _r = _W_USER_VALIDATION
        reward += _r
        _release(context, "user_validation", _r, source)

    if prediction_accuracy > 0.0:
        _r = _W_PREDICTION_HIT * min(1.0, prediction_accuracy)
        reward += _r
        _release(context, "prediction_hit", _r, source)

    if contradictions_resolved > 0:
        _r = _W_CONTRADICTION_RESOLVED * min(1.0, contradictions_resolved * 0.5)
        reward += _r
        _release(context, "contradiction_resolved", _r, source)

    if retrieval_count > 0:
        # Retrieval gives a small bonus — capped to prevent it from dominating
        _r = min(_W_RETRIEVAL_MAX, retrieval_count * 0.02)
        reward += _r
        _release(context, "retrieval_auxiliary", _r, source)

    if reward > 0:
        log_activity(
            f"[reward_calibrator] total={reward:.3f} "
            f"goal={goal_closed} user={user_positive} "
            f"pred={prediction_accuracy:.2f} contra={contradictions_resolved} "
            f"retrieval={retrieval_count}"
        )
    return reward


def _release(context: Dict[str, Any], signal_type: str, amount: float, source: str) -> None:
    # Provide `amount` as the actual reward; the RewardEngine supplies the single
    # EMA-based expected baseline (was a hardcoded expected=0.05, one of the five
    # inconsistent baselines in V3_AUDIT §2.1). action_type = signal_type so each
    # calibrated channel learns its own expectation.
    try:
        from affect.reward_signals.reward_engine import submit_reward
        submit_reward(
            context,
            actual=amount,
            action_type=signal_type,
            kind=signal_type,
            effort=0.1,
            mode="phasic",
            source=f"{source}/{signal_type}",
        )
    except Exception as _e:
        record_failure("reward_calibrator._release", _e)


# ── Goal closure detector — called after each cycle ───────────────────────────

def check_and_reward_goal_closure(context: Dict[str, Any]) -> bool:
    """
    Detect if a goal was completed this cycle and release a calibrated reward.
    Returns True if a goal was closed.
    """
    goal = context.get("committed_goal") or {}
    if not goal:
        return False
    if goal.get("status") in ("completed", "closed", "done"):
        if not context.get("_goal_closure_rewarded_this_cycle"):
            context["_goal_closure_rewarded_this_cycle"] = True
            calibrated_reward(context, goal_closed=True, source="goal_closure_check")
            log_activity(f"[reward_calibrator] Goal closed: {goal.get('title', '?')!r}")
            return True
    return False


def check_and_reward_prediction_accuracy(context: Dict[str, Any]) -> float:
    """
    Read recent prediction outcomes and reward accurate predictions.
    Returns accuracy score in [0, 1].
    """
    try:
        from utils.json_utils import load_json
        from paths import PREDICTIONS_FILE
        preds = load_json(PREDICTIONS_FILE, default_type=list) or []
        if not preds:
            return 0.0
        recent = [p for p in preds[-10:] if isinstance(p, dict)]
        evaluated = [p for p in recent if p.get("outcome") in ("correct", "incorrect")]
        if not evaluated:
            return 0.0
        accuracy = sum(1 for p in evaluated if p.get("outcome") == "correct") / len(evaluated)
        if accuracy > 0.0:
            calibrated_reward(context, prediction_accuracy=accuracy, source="prediction_check")
        return accuracy
    except Exception:
        return 0.0


def check_and_reward_contradiction_resolution(context: Dict[str, Any]) -> int:
    """
    Check if contradictions were resolved since last check.
    Returns number resolved.
    """
    try:
        from utils.json_utils import load_json
        from paths import CONTRADICTIONS_FILE
        contras = load_json(CONTRADICTIONS_FILE, default_type=list) or []
        resolved = [c for c in contras if isinstance(c, dict) and c.get("status") == "resolved"
                    and not c.get("_reward_issued")]
        if resolved:
            for c in resolved:
                c["_reward_issued"] = True
            from utils.json_utils import save_json
            save_json(CONTRADICTIONS_FILE, contras)
            calibrated_reward(context, contradictions_resolved=len(resolved),
                              source="contradiction_check")
        return len(resolved)
    except Exception:
        return 0
