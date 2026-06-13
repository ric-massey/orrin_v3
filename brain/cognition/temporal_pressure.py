# brain/cognition/temporal_pressure.py
#
# Time has weight.
#
# Deadlines approach. Unfinished things age. Delayed tasks fire.
# Orrin exists in real time — not a static present.
#
# Called once per cycle from finalize.py. Effects:
#   - Approaching/overdue deadlines  → risk_estimate / impasse_signal / social_penalty
#   - Long-running unfinished goals  → slow impasse_signal accumulation
#   - Scheduled delayed tasks        → fire into working memory when due
#   - Session age + time of day      → written to context for inner_loop

from __future__ import annotations
from core.runtime_log import get_logger

import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.log import log_private
from utils.json_utils import load_json, save_json
from cog_memory.working_memory import update_working_memory
from paths import GOALS_FILE, SCHEDULED_TASKS_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)


# ── Thresholds ─────────────────────────────────────────────────────────────────

_EMOTION_BUMPS = {
    "overdue":    {"impasse_signal": 0.08, "social_penalty": 0.03},
    "imminent":   {"risk_estimate": 0.07},
    "approaching":{"risk_estimate": 0.04},
    "near":       {"risk_estimate": 0.02},
}

_AGE_IMPASSE_SIGNAL_CAP = 0.06   # max impasse_signal per cycle from a single aging goal

# WM alert cooldown per goal (seconds): prevents flooding
_WM_COOLDOWN_S = 180.0
_wm_last_alerted: Dict[str, float] = {}


# ── DateTime helpers ───────────────────────────────────────────────────────────

def _parse_dt(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fmt_remaining(seconds: float) -> str:
    if seconds < 0:
        m = int(-seconds // 60)
        return f"{m}m overdue" if m < 60 else f"{m // 60}h {m % 60}m overdue"
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m remaining"
    h, rm = divmod(m, 60)
    return f"{h}h {rm}m remaining" if rm else f"{h}h remaining"


# ── Deadline analysis ──────────────────────────────────────────────────────────

def _deadline_status(goal: dict) -> Optional[dict]:
    """Return deadline phase dict, or None if goal has no due_at."""
    due = _parse_dt(goal.get("due_at"))
    if not due:
        return None
    remaining_s = (due - datetime.now(timezone.utc)).total_seconds()
    if remaining_s <= 0:
        phase = "overdue"
    elif remaining_s < 7_200:
        phase = "imminent"
    elif remaining_s < 43_200:
        phase = "approaching"
    elif remaining_s < 86_400:
        phase = "near"
    else:
        phase = "future"
    return {"phase": phase, "remaining_s": remaining_s}


# ── Goal aging ─────────────────────────────────────────────────────────────────

def _age_pressure(goal: dict) -> float:
    """
    0..1 pressure score from how long a goal has been unfinished.
    ~0.1 at 6 h, ~0.25 at 24 h, ~0.50 at 72 h, ~0.75 at 1 week.
    """
    created = _parse_dt(goal.get("created_at") or goal.get("timestamp"))
    if not created:
        return 0.0
    age_h = (datetime.now(timezone.utc) - created).total_seconds() / 3600
    return min(0.95, math.log1p(age_h / 8) * 0.35)


# ── Scheduled tasks ────────────────────────────────────────────────────────────

def set_goal_deadline(
    goal_title_or_id: str,
    hours: float,
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Orrin sets his own time limit on a goal.
    Writes due_at to the goal entry and logs the commitment.
    Returns True if the goal was found and updated.
    """
    from datetime import timedelta
    goals = load_json(GOALS_FILE, default_type=list) or []
    if not isinstance(goals, list):
        return False

    needle = goal_title_or_id.strip().lower()
    target = None
    for g in goals:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id") or "").lower()
        gtitle = str(g.get("title") or g.get("name") or "").lower()
        if needle in (gid, gtitle) or needle in gtitle:
            target = g
            break

    if target is None:
        log_private(f"[temporal] set_goal_deadline: goal not found: {goal_title_or_id!r}")
        return False

    due = datetime.now(timezone.utc) + timedelta(hours=hours)
    target["due_at"] = due.isoformat()
    target["deadline_self_imposed"] = True
    save_json(GOALS_FILE, goals)

    title = str(target.get("title") or target.get("name") or goal_title_or_id)[:50]
    msg = f"[self-deadline] I'm giving myself {hours:.1f}h to complete '{title}' (due {due.strftime('%H:%M UTC')})"
    update_working_memory({
        "content": msg,
        "event_type": "self_imposed_deadline",
        "importance": 3,
        "priority": 3,
    })
    log_private(f"[temporal] {msg}")

    # Reward the act of committing — it takes something to make a real promise
    if context is not None:
        try:
            from affect.reward_signals.reward_signals import release_reward_signal
            release_reward_signal(context, "reward_signal", 0.4, 0.3, 0.3,
                                  source="self_imposed_deadline")
        except Exception as _e:
            record_failure("temporal_pressure.set_goal_deadline", _e)

    return True


def schedule_task(
    content: str,
    fire_at: str,
    event_type: str = "scheduled_reminder",
    importance: int = 2,
) -> str:
    """
    Queue a delayed task that fires when fire_at (ISO UTC string) is reached.
    Returns the task id.
    """
    tasks = load_json(SCHEDULED_TASKS_FILE, default_type=list) or []
    task_id = str(uuid.uuid4())[:8]
    tasks.append({
        "id": task_id,
        "content": content,
        "fire_at": fire_at,
        "event_type": event_type,
        "importance": importance,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    save_json(SCHEDULED_TASKS_FILE, tasks)
    log_private(f"[temporal] Scheduled task {task_id!r} for {fire_at}: {content[:60]}")
    return task_id


def schedule_in(content: str, hours: float = 0, minutes: float = 0,
                event_type: str = "scheduled_reminder", importance: int = 2) -> str:
    """Convenience: schedule a task N hours/minutes from now."""
    from datetime import timedelta
    fire_dt = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)
    return schedule_task(content, fire_dt.isoformat(), event_type, importance)


def _drain_scheduled_tasks() -> List[dict]:
    """Fire tasks whose fire_at has passed. Injects into working memory."""
    tasks = load_json(SCHEDULED_TASKS_FILE, default_type=list) or []
    now = datetime.now(timezone.utc)
    pending, fired = [], []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        fire_dt = _parse_dt(t.get("fire_at"))
        if fire_dt and fire_dt <= now:
            fired.append(t)
        else:
            pending.append(t)
    if fired:
        save_json(SCHEDULED_TASKS_FILE, pending)
        for t in fired:
            update_working_memory({
                "content": f"[scheduled] {t['content']}",
                "event_type": t.get("event_type", "scheduled_reminder"),
                "importance": int(t.get("importance", 2)),
                "priority": 3,
            })
            log_private(f"[temporal] Fired: {t['content'][:80]}")
    return fired


# ── Time of day ────────────────────────────────────────────────────────────────

def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 5:   return "night"
    if h < 12:  return "morning"
    if h < 17:  return "afternoon"
    if h < 21:  return "evening"
    return "night"


# ── Anticipatory emotion ───────────────────────────────────────────────────────
# Forward-looking emotional states generated from active goals and social context.
# Different from deadline risk_estimate (reactive) — these fire BEFORE something happens.

_ANTICIP_COOLDOWN_S = 120.0   # don't fire more than once every 2 minutes
_last_anticip_ts: float = 0.0

_PROGRESS_WORDS = frozenset({
    "done", "finished", "completed", "almost", "nearly", "progress",
    "ready", "solved", "built", "achieved", "working",
})
_BLOCKED_WORDS = frozenset({
    "blocked", "stuck", "can't", "failed", "error", "problem",
    "cannot", "unable", "broken", "wrong",
})


def _anticipatory_emotions(context: Dict[str, Any], core: Dict[str, Any]) -> Optional[str]:
    """
    Generate anticipatory emotional states from committed goals and social context.
    Returns a label describing what kind of anticipation fired, or None.
    Modifies core in place.
    """
    global _last_anticip_ts
    now_ts = time.time()
    if now_ts - _last_anticip_ts < _ANTICIP_COOLDOWN_S:
        return None
    _last_anticip_ts = now_ts

    # Gather committed goal(s)
    cg  = context.get("committed_goal") or {}
    cgs = context.get("committed_goals") or ([cg] if cg else [])
    goals = [g for g in cgs if isinstance(g, dict) and g.get("title")]
    if not goals:
        return None

    # Scan recent working memory for signals about those goals
    wm = context.get("working_memory") or []
    recent_text = " ".join(
        str(e.get("content", ""))[:120] for e in wm[-6:]
        if isinstance(e, dict)
    ).lower()

    fired = None
    for goal in goals[:2]:
        title = str(goal.get("title", "") or "").lower()
        ei    = float(goal.get("emotional_intensity", 0.5) or 0.5)
        title_words = [w for w in title.split() if len(w) > 3]
        goal_in_wm  = any(w in recent_text for w in title_words) if title_words else False

        progress_signal = any(w in recent_text for w in _PROGRESS_WORDS)
        blocked_signal  = any(w in recent_text for w in _BLOCKED_WORDS)

        dl = _deadline_status(goal)

        if progress_signal and goal_in_wm:
            # About to finish → anticipatory satisfaction and relief
            core["positive_valence"]        = min(1.0, float(core.get("positive_valence", 0))        + 0.07 * ei)
            core["motivation"] = min(1.0, float(core.get("motivation", 0)) + 0.09 * ei)
            core["expected_gain"]       = min(1.0, float(core.get("expected_gain", 0))       + 0.06 * ei)
            fired = "anticipatory_satisfaction"

        elif blocked_signal and goal_in_wm:
            # About to face something that's been stuck → mild dread, not resignation
            core["risk_estimate"]     = min(1.0, float(core.get("risk_estimate", 0))     + 0.06)
            core["impasse_signal"] = min(1.0, float(core.get("impasse_signal", 0)) + 0.04)
            fired = "anticipatory_dread"

        elif dl and dl["phase"] in ("imminent", "approaching"):
            # Deadline close → pressure-excitement mix (not pure risk_estimate)
            core["risk_estimate"]    = min(1.0, float(core.get("risk_estimate", 0))    + 0.04)
            core["motivation"] = min(1.0, float(core.get("motivation", 0)) + 0.06 * ei)
            core["expected_gain"]       = min(1.0, float(core.get("expected_gain", 0))       + 0.03 * ei)
            fired = "anticipatory_pressure"

        else:
            # Default: forward-facing interest in the goal
            if ei > 0.40:
                core["expected_gain"]      = min(1.0, float(core.get("expected_gain", 0))      + 0.03 * ei)
                # Only a faint curiosity nudge, and only at STRONG interest. Goal
                # engagement is not the same as exploration drive — the old +0.025/cycle
                # fired almost every goal-pursuit cycle and out-paced the homeostatic
                # decay, pinning exploration_drive near its ceiling so it never settled.
                # At a third the size and gated higher, the decay now wins during steady
                # work, letting curiosity ebb to baseline and spike again on genuine
                # novelty (wonder / prediction-surprise).
                if ei > 0.6:
                    core["exploration_drive"] = min(1.0, float(core.get("exploration_drive", 0)) + 0.008 * ei)
            fired = "anticipatory_interest"

    # Social anticipation — user was recently here
    cycles = context.get("cycle_count", 0)
    if isinstance(cycles, dict):
        cycles = cycles.get("count", 0)
    last_user = int(context.get("last_user_cycle") or -9999)
    cycles_since = int(cycles) - last_user
    if 0 < cycles_since <= 4:
        # Just interacted — warm forward lean, not eager desperation
        core["expected_gain"]      = min(1.0, float(core.get("expected_gain", 0))      + 0.04)
        core["exploration_drive"] = min(1.0, float(core.get("exploration_drive", 0)) + 0.03)
        if fired is None:
            fired = "social_anticipation"

    return fired


# ── Main entry point ───────────────────────────────────────────────────────────

def apply_temporal_pressure(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called once per cycle from finalize.py.
    Mutates affect_state in-place. Returns summary dict.
    """
    try:
        return _apply(context)
    except Exception as e:
        log_private(f"[temporal_pressure] error: {e}")
        return {}


def _apply(context: Dict[str, Any]) -> Dict[str, Any]:
    # Lazy session-start tracking
    if "_session_start_ts" not in context:
        context["_session_start_ts"] = time.time()

    now_ts = time.time()
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        core = {}

    deadline_alerts: List[dict] = []
    aged_goals: List[dict] = []

    # ── 1. Goals: deadlines + aging ───────────────────────────────────────────
    goals = load_json(GOALS_FILE, default_type=list) or []
    if not isinstance(goals, list):
        goals = []

    active = [
        g for g in goals
        if isinstance(g, dict) and g.get("status") not in ("done", "completed", "archived")
    ]

    for goal in active:
        title   = str(goal.get("title") or goal.get("name") or "?")[:50]
        goal_id = str(goal.get("id") or title)

        dl = _deadline_status(goal)
        if dl and dl["phase"] != "future":
            phase      = dl["phase"]
            remaining  = dl["remaining_s"]
            alert      = {"title": title, "phase": phase, "remaining": _fmt_remaining(remaining)}
            deadline_alerts.append(alert)

            # Emotional cost
            for emotion, bump in _EMOTION_BUMPS.get(phase, {}).items():
                core[emotion] = min(1.0, float(core.get(emotion) or 0.0) + bump)

            # WM alert only for overdue — risk_estimate bumps handle approaching deadlines unconsciously
            last_alerted = _wm_last_alerted.get(goal_id, 0.0)
            if now_ts - last_alerted >= _WM_COOLDOWN_S and phase == "overdue":
                update_working_memory({
                    "content": f"[deadline] goal='{title}' is overdue ({_fmt_remaining(remaining)})",
                    "event_type": "deadline_alert",
                    "importance": 3,
                    "priority": 3,
                })
                _wm_last_alerted[goal_id] = now_ts

        elif not dl:
            # No deadline — apply age pressure instead, scaled by habituation.
            # A goal that's been active for 40 cycles still matters, but the
            # impasse_signal per cycle diminishes — it becomes background noise.
            pressure = _age_pressure(goal)
            if pressure >= 0.25:
                aged_goals.append({"title": title, "pressure": round(pressure, 3)})
                hab_factor = float(context.get("_goal_habituation_factor") or 1.0)
                bump = pressure * _AGE_IMPASSE_SIGNAL_CAP * hab_factor
                core["impasse_signal"] = min(1.0, float(core.get("impasse_signal") or 0.0) + bump)

    # ── 2. Anticipatory emotions (forward-looking, from goals + social) ──────
    anticip_type = _anticipatory_emotions(context, core)

    # ── 3. Scheduled task queue ───────────────────────────────────────────────
    fired = _drain_scheduled_tasks()

    # ── 4. Temporal continuity ────────────────────────────────────────────────
    session_h = max(0.0, (now_ts - float(context.get("_session_start_ts", now_ts))) / 3600)

    # ── Write back ────────────────────────────────────────────────────────────
    if isinstance(emo.get("core_signals"), dict):
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo

    summary = {
        "deadline_alerts":  deadline_alerts,
        "aged_goals":       aged_goals,
        "fired_tasks":      [t.get("content", "")[:80] for t in fired],
        "session_age_h":    round(session_h, 2),
        "time_of_day":      _time_of_day(),
        "anticipation":     anticip_type,
    }
    context["_temporal_pressure"] = summary

    if deadline_alerts or fired:
        log_private(
            f"[temporal_pressure] deadlines={len(deadline_alerts)} "
            f"fired={len(fired)} aged={len(aged_goals)}"
        )

    return summary
