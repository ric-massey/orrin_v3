# brain/goal_io.py
# Brain-side goal I/O against the single v2 GoalsAPI — no adapter object.
#
# Replaces the old GoalsBridge: the cognitive loop now talks to GoalsAPI
# directly for reads/writes, and reacts to goal LIFECYCLE through the API's
# event bus (subscribe) instead of polling list_goals() every cycle.
#
# Layering: memory/emotion reactions live HERE (brain/v1 layer), never inside
# GoalsAPI — the v2 goals package stays free of brain dependencies. GoalsAPI is
# the single source of truth for lifecycle/priority; this module is a thin
# consumer of it + its event stream.
from __future__ import annotations
from core.runtime_log import get_logger

import threading
from collections import deque
from typing import Any, Dict, List

from utils.failure_counter import record_failure
_log = get_logger(__name__)

# Goal kinds with registered v2 handlers (executable by GoalsDaemon). Cognitive
# goals have no handler and must not be submitted (they'd fail immediately).
_EXECUTABLE_KINDS = {"coding", "research", "housekeeping", "generic", "code_edit"}
_MAX_SYNC_ATTEMPTS = 5

# Event-driven failed-goal queue: filled by the API event-bus subscriber (which
# may run on the daemon thread) and drained by the cognitive-loop thread, so all
# context handling stays single-threaded.
_failed_q: "deque[Dict[str, Any]]" = deque(maxlen=200)
_q_lock = threading.Lock()
_installed = False
_unsub = None
_api_ref = None   # set by install_event_handler; lets v1 close paths mirror into v2

# Pursuit state lives only in the v1 tree (pursue_goal persists there via the
# GoalArbiter); the v2 store knows lifecycle, not plans. Without carrying these
# over, the per-cycle committed_goal rebuild discarded all plan progress and the
# milestone gate regenerated the same plan forever (FINDINGS 2026-06-12 §1).
_PURSUIT_FIELDS = (
    "plan", "milestones", "definition_of_done", "grounded_parts",
    "requires_artifact", "tracked_work", "tracked_work_path",
    "_step_attempts", "_replan_count", "_stalled",
)
_V1_TERMINAL = {"completed", "failed", "abandoned", "cancelled"}


def summarize_goal(goal: Dict[str, Any], *, active: bool = False) -> Dict[str, Any]:
    """Canonical goal representation for REST and websocket telemetry."""
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    plan = [s for s in (goal.get("plan") or spec.get("plan") or []) if isinstance(s, dict)]
    milestones = []
    for milestone in (goal.get("milestones") or spec.get("milestones") or []):
        if not isinstance(milestone, dict):
            continue
        row = dict(milestone)
        row.setdefault("text", str(row.get("milestone") or row.get("criterion") or ""))
        milestones.append(row)
    done = sum(1 for s in plan if str(s.get("status") or "").lower() == "completed")
    current = next(
        (str(s.get("step") or s.get("name") or "") for s in plan
         if str(s.get("status") or "pending").lower() not in {"completed", "done"}),
        None,
    )
    return {
        "id": goal.get("id"),
        "title": str(goal.get("title") or goal.get("name") or "(untitled)")[:160],
        "status": str(goal.get("status") or "unknown"),
        "tier": str(goal.get("tier") or goal.get("kind") or ""),
        "kind": goal.get("kind"),
        "priority": goal.get("priority"),
        "tags": [str(t) for t in (goal.get("tags") or [])][:12],
        "steps_done": done,
        "steps_total": len(plan),
        "current_step": current[:160] if current else None,
        "active": bool(active),
        "serves": str(goal.get("serves") or spec.get("serves") or "")[:160],
        "aspiration": bool(goal.get("_aspiration") or goal.get("kind") == "aspiration"),
        "description": goal.get("description") or spec.get("description"),
        "driven_by": goal.get("driven_by") or spec.get("driven_by") or spec.get("driven"),
        "definition_of_done": goal.get("definition_of_done") or spec.get("definition_of_done") or [],
        "grounded_parts": goal.get("grounded_parts") or spec.get("grounded_parts") or [],
        "milestones": milestones,
        "plan": plan,
        "history": goal.get("history") or [],
        "tracked_work": bool(goal.get("tracked_work") or spec.get("tracked_work")),
        "tracked_work_path": goal.get("tracked_work_path") or spec.get("tracked_work_path"),
        "completed_timestamp": goal.get("completed_timestamp"),
        "created_at": goal.get("created_at") or goal.get("created_timestamp"),
        "last_updated": goal.get("last_updated"),
    }


def summarize_goal_tree(
    goals: Any,
    *,
    committed_id: Any = None,
    committed: Dict[str, Any] | None = None,
    limit: int = 40,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(goal: Dict[str, Any], forced_active: bool = False) -> None:
        if not (goal.get("title") or goal.get("name")):
            return
        gid = str(goal.get("id") or goal.get("title") or goal.get("name"))
        if gid in seen:
            return
        seen.add(gid)
        status = str(goal.get("status") or "").lower()
        active = forced_active or (committed_id is not None and str(goal.get("id")) == str(committed_id))
        if committed_id is None:
            active = status in {"active", "committed", "in_progress", "running"}
        out.append(summarize_goal(goal, active=active))

    if isinstance(committed, dict):
        add(committed, True)

    def walk(value: Any) -> None:
        if len(out) >= limit:
            return
        if isinstance(value, dict):
            if (value.get("title") or value.get("name")) and value.get("status"):
                add(value)
            for child in value.get("subgoals") or []:
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(goals)
    return out[:limit]


def _goal_to_v1(g) -> Dict[str, Any]:
    """Shape a v2 Goal object into the v1-compatible dict cognition functions read."""
    spec = dict(g.spec or {})
    out = {
        "id": g.id,
        "title": g.title,
        "name": g.title,            # v1 compat: functions read "name"
        "kind": g.kind,
        "tier": g.kind,             # v1 compat: focus selection reads "tier"
        "priority": g.priority.name if hasattr(g.priority, "name") else str(g.priority),
        "tags": list(g.tags or []),
        "spec": spec,
        "next_action": (g.spec or {}).get("next_action"),
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": "in_progress",
    }
    for key in (
        "definition_of_done", "grounded_parts", "plan", "milestones",
        "requires_artifact", "tracked_work", "tracked_work_path",
        "comprehension_source", "comprehended_at",
    ):
        if key in spec:
            out[key] = spec[key]
    return out


def _load_v1_tree() -> List[Dict[str, Any]]:
    try:
        from cognition.planning.goals import load_goals
        return load_goals()
    except Exception as _e:
        record_failure("goal_io._load_v1_tree", _e)
        return []


def _find_v1_node(tree: List[Dict[str, Any]], gid: str, name: str):
    """Find a goal node in the v1 tree by id (preferred) or name/title, recursing
    into subgoals. Two passes so a name collision can't shadow the id match."""
    def walk(nodes, pred):
        for n in nodes or []:
            if isinstance(n, dict):
                if pred(n):
                    return n
                hit = walk(n.get("subgoals"), pred)
                if hit is not None:
                    return hit
        return None

    node = walk(tree, lambda n: n.get("id") == gid) if gid else None
    if node is None and name:
        node = walk(tree, lambda n: n.get("name") == name or n.get("title") == name)
    return node


def close_goal_v2(goal_id: str, status: str = "DONE", reason: str = "") -> bool:
    """Best-effort mirror of a brain-side goal close into the v2 store, so the
    next committed_goals_v1() pull doesn't resurrect the goal as in_progress."""
    api = _api_ref
    if api is None or not goal_id:
        return False
    try:
        from goals.model import Status
        g = api.get_goal(goal_id)
        if g is None:
            return False
        if g.is_terminal:
            return True
        api.update_goal(goal_id, status=Status(status))
        _log.info("[goal_io] mirrored v1 close into v2: %s -> %s%s",
                  goal_id, status, f" ({reason})" if reason else "")
        return True
    except Exception as _e:
        record_failure("goal_io.close_goal_v2", _e)
        return False


def committed_goals_v1(api, limit: int = 3) -> List[Dict[str, Any]]:
    """Top NEW/RUNNING goals as v1-compatible dicts (focus_goals.json fallback),
    hydrated with in-flight pursuit state from the v1 tree."""
    try:
        from goals.model import Status
        goals = api.list_goals(statuses=[Status.NEW, Status.RUNNING], sort="-priority", limit=limit)
        tree = _load_v1_tree()
        out: List[Dict[str, Any]] = []
        for g in goals:
            d = _goal_to_v1(g)
            node = _find_v1_node(tree, d.get("id"), d.get("name"))
            if node is not None:
                if str(node.get("status", "")).lower() in _V1_TERMINAL:
                    # v1 already closed this goal — don't resurrect it; push
                    # the close into v2 so it stops being listed at all.
                    close_goal_v2(d.get("id"), status="DONE",
                                  reason=f"v1:{node.get('status')}")
                    continue
                for k in _PURSUIT_FIELDS:
                    if k in node:
                        d[k] = node[k]
            out.append(d)
        # An empty list is a real answer (no open v2 goals) — returning it keeps
        # the loop from resurrecting a closed goal out of stale focus_goals.json
        # and pursuing it for hours (FINDINGS 2026-06-12 data sweep §6).
        return out
    except Exception as _e:
        record_failure("goal_io.committed_goals_v1", _e)
    # Legacy fallback (only when the GoalsAPI itself failed): v1 focus_goals.json
    try:
        from utils.json_utils import load_json
        from brain.paths import FOCUS_GOAL
        fg = load_json(FOCUS_GOAL, default_type=dict)
        goal = fg.get("short_or_mid") or fg.get("long_term")
        if isinstance(goal, dict) and goal.get("name"):
            return [{
                "id": goal.get("name"), "title": goal.get("name"), "name": goal.get("name"),
                "kind": goal.get("tier", "long_term"), "tier": goal.get("tier", "long_term"),
                "priority": "NORMAL", "tags": [], "spec": {},
                "next_action": goal.get("next_action"), "status": goal.get("status", "pending"),
            }]
    except Exception as _e:
        record_failure("goal_io.committed_goals_v1.2", _e)
    return []


def sync_proposed_goals(api, context: Dict[str, Any]) -> None:
    """Create executable goals from context['proposed_goals'] via GoalsAPI.create_goal."""
    proposed: List[Dict[str, Any]] = context.get("proposed_goals") or []
    if not proposed:
        return

    # Drop entries that exceeded max retry attempts (prevents unbounded growth).
    fresh: List[Dict[str, Any]] = []
    for g in proposed:
        if int(g.get("_sync_attempts") or 0) >= _MAX_SYNC_ATTEMPTS:
            record_failure("goal_io.goal_dropped",
                           ValueError(f"goal {str(g.get('title','?'))[:50]!r} dropped after max sync attempts"))
        else:
            fresh.append(g)
    if not fresh:
        context["proposed_goals"] = []
        return

    try:
        existing = {g.title for g in api.list_goals(limit=500)}
    except Exception as _e:
        # API down — keep proposals for retry rather than risk duplicate submission.
        _log.warning("[goal_io] list_goals failed (%s); deferring sync pass", _e)
        context["proposed_goals"] = fresh
        return

    remaining: List[Dict[str, Any]] = []
    for gd in fresh:
        kind = gd.get("kind", "cognitive")
        title = gd.get("title", "Unnamed goal")
        if not (gd.get("milestones") or []):
            record_failure("goal_io.no_milestones", ValueError(f"goal {title[:60]!r} has no milestones"))
        try:
            if kind in _EXECUTABLE_KINDS:
                if title in existing:
                    continue  # already exists — skip
                try:
                    from cognition.planning.goal_comprehension import comprehend_goal
                    gd = comprehend_goal(gd, context)
                except Exception:
                    pass
                spec = dict(gd.get("spec") or {})
                for key in (
                    "definition_of_done", "grounded_parts", "plan", "milestones",
                    "requires_artifact", "tracked_work", "comprehension_source",
                    "comprehended_at",
                ):
                    if key in gd:
                        spec.setdefault(key, gd[key])
                api.create_goal(title=title, kind=kind, spec=spec,
                                priority=gd.get("priority", "NORMAL"), tags=gd.get("tags") or [])
                existing.add(title)
            # cognitive/internal goals have no v2 handler — left for v1 memory paths
        except Exception:
            gd["_sync_attempts"] = int(gd.get("_sync_attempts") or 0) + 1
            if gd["_sync_attempts"] < _MAX_SYNC_ATTEMPTS:
                remaining.append(gd)
    context["proposed_goals"] = remaining


def record_goal_progress(context: Dict[str, Any]) -> None:
    """Every 5 cycles, write a goal-progress note to long memory (no GoalsAPI needed)."""
    goal = context.get("committed_goal")
    if not isinstance(goal, dict) or not goal.get("title"):
        return
    cc = context.get("cycle_count") or {}
    cycle = int(cc.get("count", 0) if isinstance(cc, dict) else cc or 0)
    if cycle % 5 != 0:
        return
    recent_picks = (context.get("recent_picks") or [])[-5:]
    last_thought = ""
    for entry in reversed((context.get("working_memory") or [])[-3:]):
        text = entry if isinstance(entry, str) else (entry.get("content", "") if isinstance(entry, dict) else "")
        if str(text or "").strip():
            last_thought = str(text).strip()[:120]
            break
    note = (f"[Goal progress | cycle {cycle}] Goal: {goal.get('title')!r}. "
            f"Recent cognitive actions: {', '.join(recent_picks) or 'none'}. "
            f"Last thought: {last_thought or '(none)'}")
    try:
        from cog_memory.long_memory import update_long_memory
        update_long_memory(note, emotion="motivation", event_type="goal_progress", importance=2, context=context)
    except Exception as _e:
        record_failure("goal_io.record_goal_progress", _e)


# ---------- event-bus driven failed-goal reaction ----------
def _on_event(event: Dict[str, Any]) -> None:
    """GoalsAPI event-bus subscriber: enqueue goals that transitioned to FAILED."""
    try:
        if str(event.get("status", "")).lower() == "failed":
            with _q_lock:
                _failed_q.append({
                    "id": event.get("goal_id"),
                    "title": event.get("title"),
                    "name": event.get("title"),
                    "kind": event.get("goal_kind"),
                })
    except Exception as _e:
        record_failure("goal_io._on_event", _e)


def install_event_handler(api) -> bool:
    """Subscribe to GoalsAPI lifecycle events once. Returns True if installed."""
    global _installed, _unsub, _api_ref
    if api is not None:
        _api_ref = api   # keep a ref so close_goal_v2 works from v1 close paths
    if _installed or api is None:
        return _installed
    try:
        _unsub = api.subscribe(_on_event)
        _installed = True
        _log.info("[goal_io] subscribed to GoalsAPI event bus")
    except Exception as _e:
        _log.warning("[goal_io] subscribe failed: %s", _e)
    return _installed


def drain_failed_goals(api, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Process FAILED-goal events queued by the bus (called from the loop thread).
    De-dupes against context['_reacted_failed_goals'] and runs mark_goal_failed.
    Replaces the old per-cycle list_goals(FAILED) poll.
    """
    with _q_lock:
        batch = list(_failed_q)
        _failed_q.clear()
    if not batch:
        return []

    seen_list: list = context.setdefault("_reacted_failed_goals", [])
    if len(seen_list) > 500:
        del seen_list[:-500]
    seen = set(seen_list)

    processed: List[Dict[str, Any]] = []
    for fg in batch:
        gid = fg.get("id")
        if not gid or gid in seen:
            continue
        reason = ""
        try:
            g = api.get_goal(gid) if api else None
            reason = (getattr(g, "last_error", "") or "") if g else ""
        except Exception as _e:
            record_failure("goal_io.drain_failed_goals", _e)
        # Cognitive goals have no v2 handler by design — don't treat as real failures.
        if fg.get("kind") not in _EXECUTABLE_KINDS and reason == "no_handler":
            continue
        seen.add(gid)
        seen_list.append(gid)
        try:
            from cognition.planning.goals import mark_goal_failed
            mark_goal_failed(fg, reason=reason, context=context)
        except Exception as _e:
            _log.warning("mark_goal_failed error: %s", _e)
        processed.append(fg)
    return processed
