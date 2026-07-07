"""Long-term goal driver (grounding plan Phase 4 / C4).

Give the long-horizon goal the wheel so research bouts compound across sessions into
sustained deepening — a visible *thread*, not a pile of same-topic reads all closing
on satiety.

A `long_term` goal marked **directional** is committable-but-non-terminal (see
`goal_io._committable_from_v1_tree` and the `mark_goal_completed` guard): it never
files DONE. Its job is to own a **frontier** — "the gap I hit last time" — and to
spawn and sequence the next concrete sub-task that works exactly that gap. The
sub-tasks are ordinary committable goals that close on Phase-1 (effect) + Phase-3
(check-pass) rules; when one finishes, its result/gap updates the parent's frontier,
so the next session's sub-task targets it. Exactly one directional goal drives at a
time (the cap enforced here and in goal_io).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

_TERMINAL = {"completed", "failed", "done", "abandoned", "retired"}


def _bare_topic(s: str) -> str:
    """Reduce a (possibly already-templated) string to its bare topic before it is
    re-templated. Without this, frontier strings built from prior goal TITLES got
    re-wrapped into "Understand Understand X more deeply" (2026-07-02 title-dup —
    the doubled title leaked verbatim into chat replies through the membrane)."""
    out = str(s or "").strip()
    for _ in range(6):  # idempotent: also unstack our own beyond/retry prefixes
        before = out
        low = out.lower()
        for pref in ("beyond ", "retry "):
            if low.startswith(pref):
                out = out[len(pref):].strip()
                low = out.lower()
        try:
            from brain.cognition.intrinsic_helpers import _strip_goal_scaffold
            out = _strip_goal_scaffold(out) or out
        except Exception:  # intentional: scaffold-strip helper optional → keep raw text
            pass
        if out == before:
            break
    return out


def _is_directional(goal: Dict[str, Any]) -> bool:
    return isinstance(goal, dict) and bool(
        goal.get("directional") or goal.get("never_complete"))


def _key(goal: Dict[str, Any]) -> str:
    return str(goal.get("id") or goal.get("name") or goal.get("title") or "")


def _priority_rank(p: Any) -> int:
    if isinstance(p, (int, float)):
        return int(p)
    return {"LOW": 1, "NORMAL": 3, "HIGH": 4, "CRITICAL": 5}.get(str(p or "").upper(), 3)


def _iter_nodes(goals: List[Dict[str, Any]]):
    for g in goals or []:
        if isinstance(g, dict):
            yield g
            yield from _iter_nodes(g.get("subgoals") or [])


def _long_term_goals(goals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for g in _iter_nodes(goals):
        if str(g.get("tier") or g.get("kind") or "").lower() == "long_term" \
                and str(g.get("status") or "").lower() not in _TERMINAL:
            out.append(g)
    return out


def promote_one_directional(goals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Enforce the cap: exactly ONE active `long_term` goal is the directional driver
    (highest priority wins). The others are demoted to plain signposts. Returns the
    promoted driver, or None if there are no long_term goals."""
    lts = _long_term_goals(goals)
    if not lts:
        return None
    # already-directional highest-priority wins ties (stable across sessions)
    lts.sort(key=lambda g: (_is_directional(g), _priority_rank(g.get("priority"))),
             reverse=True)
    driver = lts[0]
    for g in lts:
        if g is driver:
            g["directional"] = True
            g["never_complete"] = True
        else:
            # demote extras so they don't also grab a committed slot
            g.pop("directional", None)
            g.pop("never_complete", None)
    return driver


def ensure_frontier(goal: Dict[str, Any]) -> str:
    """A directional goal always has a `frontier` — the gap it is currently working.
    Seed it from the goal's own subject on first sight (the whole subject is the
    initial gap)."""
    frontier = str(goal.get("frontier") or "").strip()
    if not frontier:
        subj = str(goal.get("topic") or goal.get("title") or goal.get("name")
                   or goal.get("description") or "").strip()
        # strip a leading "Self-Evolution:" / "Understand" scaffold for a cleaner gap
        frontier = _bare_topic(subj) or "the next unknown"
        goal["frontier"] = frontier
    return frontier


def _frontier_children(goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in (goal.get("subgoals") or [])
            if isinstance(c, dict) and c.get("_frontier_child")]


def _live_child(goal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for c in _frontier_children(goal):
        if str(c.get("status") or "").lower() not in _TERMINAL:
            return c
    return None


def absorb_finished_subtasks(goal: Dict[str, Any]) -> Optional[str]:
    """When a frontier sub-task finishes, carry its outcome into the parent's frontier
    so the next sub-task targets it. A FAILED check writes its specific gap
    (`_last_check_gap`, from Phase 3) as the new frontier — "the gap I hit"; a passed
    one advances the frontier to a follow-on. Records the progression in
    `frontier_thread`. Returns the new frontier if it changed."""
    new_frontier: Optional[str] = None
    for c in _frontier_children(goal):
        if str(c.get("status") or "").lower() not in _TERMINAL:
            continue
        if c.get("_absorbed"):
            continue
        c["_absorbed"] = True
        gap = str(c.get("_last_check_gap") or "").strip()
        status = str(c.get("status") or "").lower()
        if gap:
            new_frontier = gap                       # the exact gap the check hit
            outcome = "gap"
        elif status in ("completed", "done"):
            # a passed sub-task deepens the thread: the frontier moves on from this rung
            new_frontier = f"beyond {_bare_topic(c.get('frontier_target') or c.get('title') or 'it')}"
            outcome = "advanced"
        else:
            new_frontier = f"retry {_bare_topic(c.get('frontier_target') or c.get('title') or 'it')}"
            outcome = "retry"
        goal.setdefault("frontier_thread", []).append({
            "ts": now_iso_z(),
            "from": str(c.get("frontier_target") or ""),
            "outcome": outcome,
            "to": new_frontier,
            "subtask": _key(c),
        })
    if new_frontier:
        goal["frontier"] = new_frontier
    return new_frontier


def spawn_frontier_subtask(goal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """If the driver has no live sub-task, create the next concrete committable one,
    aimed at the current frontier. It is an ordinary `core` goal that closes on the
    Phase-1/Phase-3 rules (a verifiable frontier routes through produce_and_check;
    otherwise it's a normal understanding goal). Returns the new sub-task, or None if
    one is already in flight."""
    if _live_child(goal) is not None:
        return None
    frontier = ensure_frontier(goal)
    seq = int(goal.get("_frontier_seq") or 0) + 1
    goal["_frontier_seq"] = seq
    now = now_iso_z()
    # Defensive re-clean before templating: a frontier inherited from older
    # state can still carry goal-phrasing scaffold ("Understand X more deeply"),
    # and wrapping that again produces the title-dup bug. Preserve a leading
    # beyond/retry prefix (it IS the frontier semantics), bare the rest.
    _ftxt = str(frontier or "").strip()
    _fprefix = ""
    _flow = _ftxt.lower()
    for _p in ("beyond ", "retry "):
        if _flow.startswith(_p):
            _fprefix, _ftxt = _ftxt[:len(_p)], _ftxt[len(_p):].strip()
            break
    if "understand" in _ftxt.lower() or "more deeply" in _ftxt.lower():
        _ftxt = _bare_topic(_ftxt)
    frontier_clean = f"{_fprefix}{_ftxt}".strip() or frontier
    title = f"Understand {frontier_clean} more deeply"
    # F6 (2026-07-05 findings): a title that has already completed repeatedly
    # this life (escalating cooldown / per-life cap) must not be respawned by
    # the frontier either — three titles completed 14× each as ~90 s loops.
    try:
        from brain.cognition.intrinsic_helpers import title_respawn_blocked
        if title_respawn_blocked(title):
            log_activity(f"[long_term] frontier child {title!r} blocked — "
                         "completed too often/recently this life.")
            return None
    except ImportError:
        pass
    sub = {
        "id": f"ltc_{_key(goal)[:24]}_{seq}",
        "name": title,
        "title": title,
        "description": f"Work the frontier of “{_key(goal)}”: {frontier_clean}.",
        "tier": "core",
        "status": "pending",
        "timestamp": now,
        "last_updated": now,
        "emotional_intensity": 0.6,
        "parent": _key(goal),
        # S6: a frontier child advances its parent's direction — say so in the
        # fields credit_objectives actually reads (serves + driven_by). The
        # 2026-07-02 run's completions carried neither, so no aspiration ever
        # saw a contribution.
        "serves": str(goal.get("serves") or goal.get("title")
                      or goal.get("name") or "")[:160],
        "driven_by": str(goal.get("driven_by") or "self_understanding"),
        "_frontier_child": True,
        "frontier_target": frontier_clean,
        "history": [{"event": "created", "timestamp": now, "frontier": frontier_clean}],
        "subgoals": [],
    }
    goal.setdefault("subgoals", []).append(sub)
    log_activity(f"[long_term] {_key(goal)!r} → spawned sub-task for frontier {frontier!r}")
    return sub


def drive_long_term(goals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One driver tick over a goals tree (in place). Promotes the single directional
    driver, absorbs any finished sub-task outcomes into its frontier, and ensures a
    live sub-task exists. Returns a small summary. Pure w.r.t. persistence — the
    caller loads/saves."""
    summary: Dict[str, Any] = {"driver": None, "frontier": None,
                               "absorbed": None, "spawned": None}
    try:
        driver = promote_one_directional(goals)
        if driver is None:
            return summary
        summary["driver"] = _key(driver)
        ensure_frontier(driver)
        summary["absorbed"] = absorb_finished_subtasks(driver)
        sub = spawn_frontier_subtask(driver)
        summary["spawned"] = _key(sub) if sub else None
        summary["frontier"] = driver.get("frontier")
    except Exception as _e:
        record_failure("long_term_driver.drive_long_term", _e)
    return summary


def run_long_term_driver(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Maintenance-cadence entry: load the v1 goal tree, drive the long-term thread,
    persist if anything changed. Fail-safe."""
    try:
        from brain.cognition.planning.goal_store import load_goals, save_goals
    except Exception as _e:
        record_failure("long_term_driver.run.import", _e)
        return {}
    try:
        goals = load_goals()
        if not isinstance(goals, list) or not goals:
            return {}
        summary = drive_long_term(goals)
        if summary.get("driver"):
            save_goals(goals)
        return summary
    except Exception as _e:
        record_failure("long_term_driver.run", _e)
        return {}
