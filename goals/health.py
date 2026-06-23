# goals/health.py
# Lightweight health snapshot for the Goals daemon & dashboard widgets

from __future__ import annotations
from brain.core.runtime_log import get_logger

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, cast

from .model import Goal, Step, Status, Priority
_log = get_logger(__name__)

def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)


# -------- duck-typed store iterators --------

def _iter_goals(store: Any) -> Iterable[Goal]:
    # store is duck-typed; cast the recognized accessor's result to the contract.
    if hasattr(store, "iter_goals"):
        return cast(Iterable[Goal], store.iter_goals())
    if hasattr(store, "list_goals"):
        return cast(Iterable[Goal], store.list_goals())
    if hasattr(store, "all"):
        return cast(Iterable[Goal], store.all())
    raise AttributeError("health.snapshot: store must expose iter_goals/list_goals/all()")


def _iter_steps(store: Any) -> Iterable[Step]:
    if hasattr(store, "iter_steps"):
        return cast(Iterable[Step], store.iter_steps())
    if hasattr(store, "list_steps"):
        return cast(Iterable[Step], store.list_steps())
    # If your store doesn't track steps yet, return empty to keep snapshot stable.
    return []


def _status_name(x: Any) -> str:
    try:
        return str(x.name)  # Enum
    except AttributeError:  # intentional: not an Enum → plain str
        return str(x)


def _priority_name(x: Any) -> str:
    try:
        return str(x.name)  # Enum
    except AttributeError:  # intentional: not an Enum → plain str
        return str(x)


# -------- public API --------

def snapshot(
    store: Any,
    *,
    daemon: Optional[Any] = None,
    now: Optional[datetime] = None,
    max_list: int = 10,
) -> Dict[str, Any]:
    """
    Build a JSON-serializable health snapshot for UIs/dashboards.

    Parameters
    ----------
    store : GoalsStore-like
        Must allow iterating goals (and optionally steps).
    daemon : GoalsDaemon-like, optional
        If provided, queue/workers info is included via daemon.health().
    now : datetime, optional
        Override the current time (UTC). Defaults to datetime.now(timezone.utc).
    max_list : int
        Maximum number of items to include in list-y sections (recent errors, upcoming deadlines).
    """
    now = now or UTCNOW()

    # ---------- queue/workers ----------
    q_info = {"size": None, "workers_active": None}
    if daemon is not None and hasattr(daemon, "health"):
        try:
            h = daemon.health()
            q_info["size"] = h.get("queue_size")
            q_info["workers_active"] = h.get("workers_active")
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    # ---------- goals aggregation ----------
    goals = list(_iter_goals(store))
    total_goals = len(goals)

    by_status = Counter(_status_name(g.status) for g in goals)
    by_kind = Counter((g.kind or "unknown") for g in goals)
    by_priority = Counter(_priority_name(getattr(g, "priority", Priority.NORMAL)) for g in goals)

    # Overdue = has deadline in the past and not terminal
    terminal = {Status.DONE, Status.FAILED, Status.CANCELLED}
    overdue_items: List[Dict[str, Any]] = []
    for g in goals:
        dl = getattr(g, "deadline", None)
        if not dl or g.status in terminal:
            continue
        try:
            overdue_sec = (now - dl).total_seconds()
        except (TypeError, ValueError):  # intentional: bad deadline type → skip
            continue
        if overdue_sec > 0:
            overdue_items.append({
                "id": g.id,
                "title": g.title,
                "status": _status_name(g.status),
                "priority": _priority_name(getattr(g, "priority", Priority.NORMAL)),
                "deadline": dl.isoformat(),
                "age_seconds": int(overdue_sec),
            })
    _overdue_sorted = sorted(overdue_items, key=lambda x: x["age_seconds"], reverse=True)[:1]
    oldest_overdue = _overdue_sorted[0] if _overdue_sorted else None

    # Upcoming deadlines (non-terminal, with future deadlines)
    upcoming: List[Dict[str, Any]] = []
    for g in goals:
        dl = getattr(g, "deadline", None)
        if not dl or g.status in terminal:
            continue
        try:
            in_sec = (dl - now).total_seconds()
        except (TypeError, ValueError):  # intentional: bad deadline type → skip
            continue
        if in_sec > 0:
            upcoming.append({
                "id": g.id,
                "title": g.title,
                "status": _status_name(g.status),
                "priority": _priority_name(getattr(g, "priority", Priority.NORMAL)),
                "deadline": dl.isoformat(),
                "in_seconds": int(in_sec),
            })
    upcoming = sorted(upcoming, key=lambda x: x["in_seconds"])[:max_list]

    # Blocked reasons (top)
    blocked_reasons: Counter[str] = Counter()
    for g in goals:
        if _status_name(g.status) == "BLOCKED":
            reason = (getattr(g, "last_error", None) or "blocked").strip()
            blocked_reasons[reason] += 1
    blocked_top = [{"reason": r, "count": c} for r, c in blocked_reasons.most_common(5)]

    # Recent errors (FAILED/BLOCKED with last_error), newest first by updated_at
    def _dt(x: Any) -> datetime:
        try:
            return cast(datetime, x if x.tzinfo else x.replace(tzinfo=timezone.utc))
        except AttributeError:  # intentional: not a datetime → fall back to now
            return UTCNOW()

    recent_errors: List[Dict[str, Any]] = []
    for g in goals:
        if _status_name(g.status) in {"FAILED", "BLOCKED"} and getattr(g, "last_error", None):
            recent_errors.append({
                "id": g.id,
                "title": g.title,
                "status": _status_name(g.status),
                "last_error": g.last_error,
                "updated_at": getattr(g, "updated_at", now).isoformat(),
            })
    recent_errors.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
    recent_errors = recent_errors[:max_list]

    # ---------- steps aggregation (if available) ----------
    steps = list(_iter_steps(store))
    by_step_status = Counter(_status_name(s.status) for s in steps) if steps else Counter()
    steps_total = sum(by_step_status.values())

    # ---------- final payload ----------
    payload = {
        "ts": now.isoformat(),
        "queue": q_info,
        "goals": {
            "total": total_goals,
            "by_status": dict(by_status),
            "by_kind": dict(by_kind),
            "by_priority": dict(by_priority),
            "overdue": {
                "count": len(overdue_items),
                "oldest": oldest_overdue,
            },
            "blocked_top_reasons": blocked_top,
            "recent_errors": recent_errors,
            "upcoming_deadlines": upcoming,
        },
        "steps": {
            "total": steps_total,
            "by_status": dict(by_step_status),
        },
    }
    return payload


__all__ = ["snapshot"]
