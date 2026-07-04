# brain/cognition/planning/goal_reconcile.py
#
# P6 — live goal-store reconciler (ORRIN_PRODUCTION_REWARD_PLAN, §3 P6 / §4 G).
#
# The production-reward fix adds a new executable-goal path that runs straight
# through the fragile v1↔v2 bridge (goal_io.py — the one already scarred by "goals
# resurrected and pursued for hours"). Single-homing + an invariant test protect
# only the NEW path; the intake/aspiration goals already live in v1 *and* v2 and
# can still desync. This pass walks ALL goals on a low cadence and repairs the two
# desync classes goal_io's own comments record, plus double-home drift:
#
#   - resurrection:     terminal in v2 (DONE/FAILED/CANCELLED) but live in v1
#                       (in_progress) → re-close it in v1.
#   - orphan-RUNNING:   terminal in v1 but still NEW/READY/RUNNING/BLOCKED in v2
#                       → mirror the close into v2 via close_goal_v2.
#   - double-home drift: same title, disagreeing status across stores → v2 wins on
#                       lifecycle (documented source of truth); v1 keeps pursuit
#                       scratch only.
#
# Each repair is counted into outcome_metrics.store_desyncs_repaired, so this is
# ALSO the instrument that says whether the existing paths are still buggy: a
# counter that stays >0 cycle after cycle = a real desync source remains, and the
# full v1↔v2 unification (§4c, GOAL_STORE_UNIFICATION) is no longer deferrable.
from __future__ import annotations

from brain.core.runtime_log import get_logger
from typing import Any, Callable, Dict, List, Optional, Tuple

from brain.utils.log import log_activity
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

_V2_TERMINAL = {"DONE", "FAILED", "CANCELLED"}
_V1_TERMINAL = {"completed", "failed", "abandoned", "cancelled"}


def close_v1_mirror(goal_id: str, title: str, v2_status: str,
                    *, event: str = "closed_from_v2_event") -> bool:
    """Close the v1 mirror of a v2-terminal goal — the shared v1-close primitive
    (Run 4 fix A1). Finds the node by id (title fallback, case-insensitive), sets
    completed/failed, appends a history entry, and saves through the GoalArbiter
    so any thread (the API event bus fires on the daemon thread) can call it
    safely. Idempotent: no node, or an already-terminal node, is a no-op.

    Returns True only when a LIVE v1 node was actually closed — so the
    reconciler can keep counting genuine repairs while the event-driven caller
    treats False as "nothing to do"."""
    sname = str(v2_status or "").upper()
    if sname not in _V2_TERMINAL:
        return False
    gid = str(goal_id or "")
    tkey = str(title or "").strip().lower()
    if not gid and not tkey:
        return False
    closed = {"ok": False}

    def _walk(nodes: Any, pred: Callable[[Dict[str, Any]], bool]) -> Optional[Dict[str, Any]]:
        for n in nodes or []:
            if isinstance(n, dict):
                if pred(n):
                    return n
                hit = _walk(n.get("subgoals"), pred)
                if hit is not None:
                    return hit
        return None

    def _mut(tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        node = _walk(tree, lambda n: n.get("id") == gid) if gid else None
        if node is None and tkey:
            node = _walk(tree, lambda n: (str(n.get("title") or n.get("name") or "")
                                          .strip().lower() == tkey))
        if node is not None and str(node.get("status", "")).lower() not in _V1_TERMINAL:
            now = now_iso_z()
            node["status"] = "completed" if sname == "DONE" else "failed"
            node["last_updated"] = now
            node.setdefault("history", []).append({
                "event": event, "v2_status": sname, "timestamp": now,
            })
            closed["ok"] = True
        return tree

    try:
        from brain.cognition.planning import goal_arbiter
        goal_arbiter.apply(_mut, source="close_v1_mirror")
    except Exception as _e:
        record_failure("goal_reconcile.close_v1_mirror", _e)
        return False
    if closed["ok"]:
        log_activity(f"[goal_io] v1 mirror closed from v2 terminal: "
                     f"'{(title or gid)[:50]}' ({sname}).")
    return closed["ok"]


def _v2_status_name(g: Any) -> str:
    st = getattr(g, "status", None)
    return str(getattr(st, "name", str(st or ""))).upper()


def _index_v1(
    tree: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}

    def walk(nodes: Any) -> None:
        for n in nodes or []:
            if isinstance(n, dict):
                gid = n.get("id")
                title = (n.get("title") or n.get("name") or "").strip().lower()
                if gid:
                    by_id[gid] = n
                if title:
                    by_title.setdefault(title, n)
                walk(n.get("subgoals"))

    walk(tree)
    return by_id, by_title


def reconcile_goal_stores(context: Optional[Dict[str, Any]] = None) -> int:
    """Walk both stores, repair the desync classes, count repairs. Returns the
    number of repairs made this pass (0 when the stores agree)."""
    repairs = 0
    try:
        import brain.goal_io as goal_io
        api = getattr(goal_io, "_api_ref", None)
    except Exception as _e:
        record_failure("goal_reconcile.import", _e)
        return 0
    if api is None:
        return 0   # v2 store not installed (e.g. headless) — nothing to reconcile

    try:
        v2_goals = api.list_goals()
    except Exception as _e:
        record_failure("goal_reconcile.list_goals", _e)
        return 0

    try:
        from brain.cognition.planning.goals import load_goals
        tree = load_goals()
    except Exception as _e:
        record_failure("goal_reconcile.load_goals", _e)
        return 0
    if not isinstance(tree, list):
        return 0

    v1_by_id, v1_by_title = _index_v1(tree)

    for g in v2_goals:
        try:
            gid = getattr(g, "id", None)
            sname = _v2_status_name(g)
            v2_terminal = sname in _V2_TERMINAL
            title = (getattr(g, "title", "") or "").strip().lower()

            node = v1_by_id.get(gid) if gid else None
            if node is None and title:
                # double-home drift: same title, possibly different id.
                node = v1_by_title.get(title)
            if node is None:
                continue

            v1status = str(node.get("status", "")).lower()
            v1_terminal = v1status in _V1_TERMINAL

            if v2_terminal and not v1_terminal:
                # resurrection — v2 closed it, v1 still thinks it's live.
                # A1: shared close primitive (same one the event bus now uses),
                # so this pass stays the *instrument*: any repair counted here
                # means a terminal event was missed — a genuine unknown seam.
                if close_v1_mirror(str(gid or ""), title,
                                   sname, event="reconciled_to_v2_terminal"):
                    repairs += 1
                    log_activity(f"[goal_reconcile] resurrection repaired: '{title[:50]}' "
                                 f"re-closed in v1 ({sname}).")
            elif v1_terminal and not v2_terminal:
                # orphan-RUNNING — v1 closed it, v2 still NEW/READY/RUNNING/BLOCKED.
                tgt = "DONE" if v1status == "completed" else "FAILED"
                if goal_io.close_goal_v2(str(gid), status=tgt, reason="reconcile_orphan_running"):
                    repairs += 1
                    log_activity(f"[goal_reconcile] orphan-RUNNING repaired: '{title[:50]}' "
                                 f"closed in v2 ({tgt}).")
        except Exception as _e:
            record_failure("goal_reconcile.repair", _e)

    if repairs:
        try:
            from brain.cognition.planning.outcome_metrics import record_store_desync_repair
            record_store_desync_repair(repairs)
        except Exception as _e:
            record_failure("goal_reconcile.metric", _e)
        log_activity(f"[goal_reconcile] repaired {repairs} store desync(s) this pass.")
    return repairs
