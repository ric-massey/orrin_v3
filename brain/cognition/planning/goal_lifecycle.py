# cognition/planning/goal_lifecycle.py
#
# Goal lifecycle: fading, pausing, resuming, and lifetime goal management.
#
# HUMAN GOAL MODEL
# ─────────────────────────────────────────────────────────────────────────────
# Humans don't have binary goals (active / done). They have a motivational
# gradient that shifts over time:
#
#   in_progress → fading (unattended) → dormant (long-abandoned) → revived
#   in_progress → paused (deliberately blocked) → resumed
#   lifetime goals: never complete — they only accumulate progress
#
# Motivational weight (0.0–1.0) models the psychological salience of a goal.
# A goal that hasn't been touched in days loses weight. When something
# related fires in long memory, weight partially recovers (re-engagement).
#
# FADING: Austin & Vancouver (1996) — goal disengagement follows a decay
# curve when the goal ceases to be attended to. Attention is the mechanism
# that keeps goals alive.
#
# REWARD_SIGNAL & LIFETIME GOALS: Berridge (2007) — wanting (reward_signal) is not
# the same as liking (completion_signal). You can still *want* to pursue a lifetime
# goal even if you'll never arrive at it. The wanting itself is the drive.
# Progress notes on lifetime goals fire a small reward_signal burst because
# movement-toward is what reward_signal responds to, not completion.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from brain.core.runtime_log import get_logger
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.paths import LIFETIME_GOALS_FILE
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

_FADE_UNATTEND_SECONDS = 6 * 3600   # 6 hours without pursuit before fading starts
_FADE_RATE = 0.04                    # motivational_weight decay per fade call
_DORMANT_THRESHOLD = 0.20            # below this → status = "dormant" (but not deleted)
_REVIVE_BOOST = 0.15                 # weight recovered when a related topic fires
_LIFETIME_PROGRESS_REWARD_SIGNAL = 0.45  # actual reward for recording lifetime progress



def load_lifetime_goals() -> List[Dict[str, Any]]:
    try:
        goals: List[Any] = load_json(LIFETIME_GOALS_FILE, default_type=list)
        return goals if isinstance(goals, list) else []
    except Exception as exc:  # lifetime goals unreadable — record, none
        record_failure("goal_lifecycle.load_lifetime_goals", exc)
        return []


def save_lifetime_goals(goals: List[Dict[str, Any]]) -> None:
    try:
        save_json(LIFETIME_GOALS_FILE, goals)
    except Exception as _e:
        record_failure("goal_lifecycle.save_lifetime_goals", _e)


def get_active_lifetime_goal(context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Return the highest-weight in_progress lifetime goal.
    Caches result in context for the cycle so it's cheap to call repeatedly.
    """
    if context is not None:
        cached = context.get("_active_lifetime_goal")
        if isinstance(cached, dict):
            return cached

    goals = load_lifetime_goals()
    active = [g for g in goals if g.get("status") in ("in_progress",) and g.get("never_complete")]
    if not active:
        return None
    best = max(active, key=lambda g: float(g.get("motivational_weight", 0.0)))

    if context is not None:
        context["_active_lifetime_goal"] = best
    return best


def record_lifetime_progress(goal_id: str, note: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    Add a progress note to a lifetime goal and fire a small reward_signal burst.
    Called when a short-term goal that was in_service_of this lifetime goal completes.
    """
    goals = load_lifetime_goals()
    updated = False
    for g in goals:
        if g.get("id") == goal_id:
            g.setdefault("progress_notes", []).append({
                "note": note,
                "timestamp": now_iso_z(),
            })
            g["last_pursued_at"] = now_iso_z()
            # Progress re-engages the goal — recover some motivational weight
            w = float(g.get("motivational_weight", 0.8))
            g["motivational_weight"] = round(min(1.0, w + 0.05), 3)
            updated = True
            log_activity(f"[lifetime_goal] Progress: '{g['title']}' — {note[:80]}")
            break

    if updated:
        save_lifetime_goals(goals)
        # Invalidate context cache so next call re-fetches
        if context is not None:
            context.pop("_active_lifetime_goal", None)

    if context is not None:
        try:
            from brain.control_signals.reward_signals.reward_signals import release_reward_signal
            from brain.control_signals.reward_signals.action_reward_ema import get_expected as _pe, update_expected as _upe
            _act = _LIFETIME_PROGRESS_REWARD_SIGNAL
            release_reward_signal(
                context,
                signal_type="reward_signal",
                actual_reward=_act,
                expected_reward=_pe(context, "lifetime_progress"),
                effort=0.5,
                mode="phasic",
                source="lifetime_progress",
            )
            _upe(context, "lifetime_progress", _act)
        except Exception as _e:
            record_failure("goal_lifecycle.record_lifetime_progress", _e)


def fade_goals(context: Optional[Dict[str, Any]] = None) -> None:
    """
    Decay motivational_weight for non-lifetime goals that haven't been pursued
    recently. Goals below the dormant threshold move to status='dormant'.
    Lifetime goals fade much more slowly and never go dormant.

    Call this periodically (e.g. every 60 cognitive cycles).
    """
    goals = load_lifetime_goals()
    now_ts = time.time()
    changed = False

    for g in goals:
        if not g.get("never_complete"):
            continue  # only lifetime goals managed here; regular goals use goals.py

        last_str = g.get("last_pursued_at")
        if last_str:
            try:
                last_ts = datetime.fromisoformat(last_str.replace("Z", "+00:00")).timestamp()
                secs_idle = now_ts - last_ts
            except Exception:
                secs_idle = 0
        else:
            secs_idle = 0

        if secs_idle > _FADE_UNATTEND_SECONDS:
            w = float(g.get("motivational_weight", 0.8))
            # Lifetime goals fade at 1/4 the rate of regular goals
            new_w = round(max(0.3, w - _FADE_RATE * 0.25), 3)
            if new_w != w:
                g["motivational_weight"] = new_w
                changed = True
                log_private(f"[goal_lifecycle] Lifetime goal fading: '{g['title']}' weight→{new_w}")

    if changed:
        save_lifetime_goals(goals)

    # Now handle regular goals in goals_mem.json
    _fade_regular_goals(now_ts)


def _fade_regular_goals(now_ts: float) -> None:
    """Decay motivational_weight for regular short/long_term goals."""
    from brain.paths import GOALS_FILE

    goals: List[Any] = load_json(GOALS_FILE, default_type=list)
    if not isinstance(goals, list):
        return

    changed = False
    dormant_transitions = 0

    def _fade_node(goal: Dict[str, Any]) -> None:
        nonlocal changed, dormant_transitions
        if goal.get("never_complete"):
            return
        # P2 — artifact-gated production goals must FAIL loudly at their deadline,
        # not fade quietly into dormancy. Excluding them from the fade path keeps
        # the felt-cost channel honest: "Make things" can't escape into a soft
        # abandonment closure; it either produces or it is failed.
        if goal.get("requires_artifact") or \
                str(goal.get("driven_by") or "").lower() == "output_producing":
            for sub in (goal.get("subgoals") or []):
                if isinstance(sub, dict):
                    _fade_node(sub)
            return
        status = goal.get("status", "pending")
        if status in ("completed", "abandoned", "dormant"):
            return

        last_str = goal.get("last_updated") or goal.get("timestamp")
        if not last_str:
            return
        try:
            last_ts = datetime.fromisoformat(last_str.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):  # intentional: unparseable timestamp → skip
            return

        secs_idle = now_ts - last_ts
        if secs_idle < _FADE_UNATTEND_SECONDS:
            return

        w = float(goal.get("motivational_weight", 0.8))
        new_w = round(max(0.0, w - _FADE_RATE), 3)
        goal["motivational_weight"] = new_w
        changed = True

        if new_w <= _DORMANT_THRESHOLD and status not in ("dormant",):
            goal["status"] = "dormant"
            goal["last_updated"] = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
            dormant_transitions += 1
            log_activity(f"[goal_lifecycle] Goal dormant: '{goal.get('name')}' (weight={new_w})")

        for sub in (goal.get("subgoals") or []):
            if isinstance(sub, dict):
                _fade_node(sub)

    for g in goals:
        if isinstance(g, dict):
            _fade_node(g)

    if changed:
        save_json(GOALS_FILE, goals)

    # Phase E outcome metric — dormant transition is the abandonment gradient firing.
    if dormant_transitions:
        try:
            from brain.cognition.planning.outcome_metrics import record_abandonment_closure
            record_abandonment_closure(dormant_transitions)
        except Exception as _e:
            record_failure("goal_lifecycle._fade_regular_goals", _e)


def pause_goal(goal_id: str, reason: str = "") -> bool:
    """Set a goal's status to 'paused'. Returns True if found and updated."""
    goals = load_lifetime_goals()
    for g in goals:
        if g.get("id") == goal_id and g.get("status") == "in_progress":
            g["status"] = "paused"
            g["paused_reason"] = reason
            g["last_updated"] = now_iso_z()
            save_lifetime_goals(goals)
            log_activity(f"[goal_lifecycle] Paused lifetime goal: '{g['title']}' — {reason}")
            return True

    # Also check regular goals
    from brain.paths import GOALS_FILE
    reg_goals: List[Any] = load_json(GOALS_FILE, default_type=list)
    if isinstance(reg_goals, list):
        for g in reg_goals:
            if isinstance(g, dict) and (g.get("id") == goal_id or g.get("name") == goal_id):
                g["status"] = "paused"
                g["paused_reason"] = reason
                g["last_updated"] = now_iso_z()
                save_json(GOALS_FILE, reg_goals)
                return True
    return False


def resume_goal(goal_id: str) -> bool:
    """Restore a paused goal to in_progress. Returns True if found."""
    goals = load_lifetime_goals()
    for g in goals:
        if g.get("id") == goal_id and g.get("status") == "paused":
            g["status"] = "in_progress"
            g.pop("paused_reason", None)
            g["last_updated"] = now_iso_z()
            save_lifetime_goals(goals)
            log_activity(f"[goal_lifecycle] Resumed lifetime goal: '{g['title']}'")
            return True

    from brain.paths import GOALS_FILE
    reg_goals: List[Any] = load_json(GOALS_FILE, default_type=list)
    if isinstance(reg_goals, list):
        for g in reg_goals:
            if isinstance(g, dict) and (g.get("id") == goal_id or g.get("name") == goal_id):
                if g.get("status") in ("paused", "dormant"):
                    g["status"] = "in_progress"
                    g.pop("paused_reason", None)
                    g["last_updated"] = now_iso_z()
                    save_json(GOALS_FILE, reg_goals)
                    return True
    return False


def touch_lifetime_goal(goal_id: str) -> bool:
    """
    Reset the neglect clock on a lifetime goal by updating last_pursued_at.
    Returns True if found, False otherwise.

    Called by the standing-set selection mechanism when a focus-slot goal is
    committed in service of a standing goal. This prevents the same drive from
    being selected again immediately — its neglect urgency drops to near zero,
    giving other drives a chance to rise (Temporal Motivation Theory, Steel &
    König, 2006).
    """
    goals = load_lifetime_goals()
    for g in goals:
        if g.get("id") == goal_id:
            g["last_pursued_at"] = now_iso_z()
            save_lifetime_goals(goals)
            return True
    return False


def revive_lifetime_goal_by_topic(topic: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    When a topic fires in research/memory, boost motivational_weight for any
    lifetime goal whose title or description overlaps with that topic.
    """
    topic_lower = topic.lower()
    topic_words = {w for w in topic_lower.split() if len(w) > 3}
    if not topic_words:
        return

    goals = load_lifetime_goals()
    changed = False
    for g in goals:
        if not g.get("never_complete"):
            continue
        combined = (g.get("title", "") + " " + g.get("description", "")).lower()
        if any(w in combined for w in topic_words):
            w = float(g.get("motivational_weight", 0.8))
            new_w = round(min(1.0, w + _REVIVE_BOOST), 3)
            if new_w != w:
                g["motivational_weight"] = new_w
                changed = True
                log_private(f"[goal_lifecycle] Lifetime goal revived by topic '{topic}': '{g['title']}' weight→{new_w}")

    if changed:
        save_lifetime_goals(goals)
        if context is not None:
            context.pop("_active_lifetime_goal", None)
