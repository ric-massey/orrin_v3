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
from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger

import threading
from collections import deque
from typing import Any, Dict, List

from brain.utils.failure_counter import record_failure
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

_V1_TERMINAL = {"completed", "failed", "abandoned", "cancelled"}

# ── Source-of-truth contract (GOALS_MASTER_PLAN Part II / Option D, D1) ──────────
# The v1 *cognitive* goal is authoritative for these fields — the rich layering
# (tier / origin / aspiration) that v2's FLAT Goal model (id/title/kind/spec/
# priority/status) cannot represent. v2 owns lifecycle (status/priority/execution).
#
# The seam used to DROP them on the round-trip: _goal_to_v1 defaulted `tier = kind`,
# so a recruited survival goal (kind="generic") came back tier="generic" — silently
# losing the survival layer Part I depends on. Fix per Option D: the projection
# stashes these in the v2 *spec* (a lossless free-form carrier) and the read
# restores them, so the v2 record is a regenerable PROJECTION of the cognitive goal,
# never a competing original that clobbers it.
_V1_AUTHORITATIVE_FIELDS = (
    "tier", "driven_by", "source", "recruit_aid",
    "zone", "orientation", "serves",
)


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
        # tier is v1-AUTHORITATIVE (Option D): restore it from the projection's spec;
        # fall back to kind only for legacy goals projected before the contract.
        "tier": spec.get("tier") or g.kind,
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
    # Restore the rest of the v1-authoritative cognitive fields from the projection
    # spec (tier already handled above) so a v2 round-trip never strips driven_by /
    # source / recruit_aid / zone / orientation / serves.
    for key in _V1_AUTHORITATIVE_FIELDS:
        if key != "tier" and key in spec and key not in out:
            out[key] = spec[key]
    return out


def _load_v1_tree() -> List[Dict[str, Any]]:
    try:
        from brain.cognition.planning.goals import load_goals
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


# Statuses a v1 goal can be committed/pursued from (vs. _V1_TERMINAL).
_COMMITTABLE_STATUSES = {"proposed", "pending", "in_progress", "active", "running"}
# Directional layers that are never committed (they're aspirations, not tasks).
_NONCOMMITTABLE_TIERS = {"aspiration", "long_term"}
_BUCKET_NAME = "Immediate Actions"   # the micro-goal container, not a goal itself


def _tier_weight(tier: Any) -> int:
    """Reuse the executive's tier ordering so v1 selection honours the same floor
    (survival > core/existential > … ) Part I established. Fail-safe to 1."""
    try:
        from brain.cognition.planning.executive import _TIER_TURNS
        return int(_TIER_TURNS.get(str(tier or "").lower(), 1))
    except Exception:  # intentional: tier ordering is best-effort, fail-safe to 1
        return 1


def _priority_rank(p: Any) -> int:
    if isinstance(p, (int, float)):
        return int(p)
    return {"LOW": 1, "NORMAL": 3, "HIGH": 4, "CRITICAL": 5}.get(str(p or "").upper(), 3)


def _committable_from_v1_tree(limit: int) -> List[Dict[str, Any]]:
    """The committed goals, chosen from the v1 cognitive tree, tier-then-priority
    ordered. Skips the Immediate-Actions container and directional/terminal goals.
    Returns shallow copies so the loop's per-cycle edits don't corrupt the tree."""
    tree = _load_v1_tree()
    found: List[Dict[str, Any]] = []

    def walk(nodes: Any) -> None:
        for n in nodes or []:
            if not isinstance(n, dict):
                continue
            name = n.get("name") or n.get("title")
            status = str(n.get("status") or "").lower()
            tier = str(n.get("tier") or n.get("kind") or "").lower()
            # P4 — a `long_term` goal is normally non-committable (a signpost), but a
            # DIRECTIONAL one (marked directional / never_complete) IS committable: it
            # becomes the active driver that spawns and sequences the next concrete
            # sub-task. It still never files DONE (mark_goal_completed guards that), so
            # it's committable-but-non-terminal. `aspiration` stays non-committable.
            committable_tier = (tier not in _NONCOMMITTABLE_TIERS) or (
                tier == "long_term"
                and bool(n.get("directional") or n.get("never_complete")))
            if (n.get("name") != _BUCKET_NAME and name
                    and status in _COMMITTABLE_STATUSES
                    and status not in _V1_TERMINAL
                    and committable_tier):
                found.append(n)
            walk(n.get("subgoals"))

    walk(tree)
    found.sort(
        key=lambda g: (_tier_weight(g.get("tier") or g.get("kind")),
                       _priority_rank(g.get("priority"))),
        reverse=True,
    )
    # P4 cap (change 4): exactly ONE directional long_term goal drives at a time — the
    # highest-ranked one. The rest of the committed slots go to ordinary goals so the
    # never-ending driver can never starve the pool; extra directionals stay signposts.
    result: List[Dict[str, Any]] = []
    seen_directional = False
    for g in found:
        tier = str(g.get("tier") or g.get("kind") or "").lower()
        is_directional = tier == "long_term" and bool(
            g.get("directional") or g.get("never_complete"))
        if is_directional:
            if seen_directional:
                continue
            seen_directional = True
        result.append(g)
        if len(result) >= limit:
            break
    return [dict(g) for g in result]


def _reconcile_open_v2_into_v1(api) -> None:
    """Keep the v1 tree in sync with v2's open work-orders so v1 can be the single
    committed-goal source (Option D). For each open v2 goal:
      • no v1 node yet  → absorb it into the tree (v2 id stamped, tier/origin restored
        from spec) so a goal that currently lives only in v2 isn't stranded;
      • v1 node already terminal → mirror the close into v2 (DONE) so the daemon stops
        running a goal the cognitive layer has finished (anti-resurrection guard).
    Idempotent: an existing, non-terminal node is left untouched (the v1 node is the
    authority; its pursuit/cognitive state must win)."""
    try:
        from goals.model import Status
        from brain.cognition.planning.goals import add_goal, save_goals
        open_goals = api.list_goals(statuses=[Status.NEW, Status.RUNNING], limit=200)
        tree = _load_v1_tree()
        to_add: List[Dict[str, Any]] = []
        to_close: List[tuple] = []
        dirty = False
        for g in open_goals:
            d = _goal_to_v1(g)   # carries tier/origin restored from spec (D2 read)
            vid = d.get("id")
            node = _find_v1_node(tree, vid, d.get("name"))
            if node is None:
                d.setdefault("status", "in_progress")
                to_add.append(d)
            elif str(node.get("status", "")).lower() in _V1_TERMINAL:
                to_close.append((vid, node.get("status")))
            elif vid and node.get("id") != vid:
                # A name-matched node carrying no id (or a divergent one): adopt the
                # canonical v2 id so completion/failure events reconcile by id, not
                # title. Without this, an id-less v1 node stays title-matched forever
                # — the exact fragmentation that broke coherent goal history.
                node["id"] = vid
                dirty = True
        # Persist id-stamps BEFORE any add_goal (which reloads+saves the tree and
        # would otherwise clobber the in-memory stamps).
        if dirty:
            save_goals(tree)
        for d in to_add:
            add_goal(d)
        for vid, status in to_close:
            close_goal_v2(vid, status="DONE", reason=f"v1:{status}")
    except Exception as _e:
        record_failure("goal_io._reconcile_open_v2_into_v1", _e)


def committed_goals_v1(api, context: Dict[str, Any] | None = None,
                       limit: int = 3) -> List[Dict[str, Any]]:
    """The committed goals — chosen from the v1 cognitive tree, which is the single
    source of truth for WHICH goals are committed (Option D, Part II). v2 remains the
    execution projection: it still runs executable work-orders and reports events
    back, but it no longer decides what's committed. Reconciles v2's open goals into
    v1 first (absorb new / close finished), then selects tier-then-priority from v1."""
    if api is not None:
        _reconcile_open_v2_into_v1(api)
    return _committable_from_v1_tree(limit)


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
        # title → id so a dedup-skip can still hand the proposal the canonical id of
        # the v2 goal it matches (otherwise the source node would stay id-less and
        # later events would only ever title-match it).
        existing = {g.title: g.id for g in api.list_goals(limit=500)}
    except Exception as _e:
        # API down — keep proposals for retry rather than risk duplicate submission.
        _log.warning("[goal_io] list_goals failed (%s); deferring sync pass", _e)
        context["proposed_goals"] = fresh
        return

    remaining: List[Dict[str, Any]] = []
    for gd in fresh:
        # `hydrate_goal_model` below REBINDS `gd` to a fresh dict; keep the original
        # proposal reference so the canonical id is stamped back onto the node that
        # actually lives in context["proposed_goals"], not the discarded copy.
        src = gd
        kind = gd.get("kind", "cognitive")
        title = gd.get("title", "Unnamed goal")
        if not (gd.get("milestones") or []):
            record_failure("goal_io.no_milestones", ValueError(f"goal {title[:60]!r} has no milestones"))
        try:
            if kind in _EXECUTABLE_KINDS:
                if title in existing:
                    # Already in v2 — adopt its id onto the source node so this
                    # proposal joins the one canonical thread instead of forking.
                    gd["id"] = existing[title]
                    continue
                try:
                    from brain.cognition.planning.goal_comprehension import hydrate_goal_model
                    gd = hydrate_goal_model(gd, context)
                except Exception as exc:
                    record_failure("goal_io.sync_proposed_goals.hydrate", exc)
                spec = dict(gd.get("spec") or {})
                for key in (
                    "definition_of_done", "grounded_parts", "plan", "milestones",
                    "requires_artifact", "tracked_work", "comprehension_source",
                    "comprehended_at",
                ):
                    if key in gd:
                        spec.setdefault(key, gd[key])
                # Project the v1-authoritative cognitive fields into the spec so they
                # survive the v2 round-trip (Option D — the v2 record is a projection
                # of the cognitive goal, not a flatter copy that loses tier/origin).
                for key in _V1_AUTHORITATIVE_FIELDS:
                    if gd.get(key) is not None:
                        spec.setdefault(key, gd[key])
                # Canonical-ID contract: pass the source node's id (the cognitive
                # layer minted it at commit) so v2 ADOPTS it rather than minting a
                # rival id; capture the return and write the id back onto the source
                # node so v1↔v2 share one identity from this instant on. gd.get("id")
                # may be None for a never-committed proposal — then v2 mints and we
                # stamp that single id back here.
                created = api.create_goal(title=title, kind=kind, spec=spec,
                                          priority=gd.get("priority", "NORMAL"),
                                          tags=gd.get("tags") or [], id=gd.get("id"))
                if created is not None and getattr(created, "id", None):
                    src["id"] = created.id   # stamp the live proposal node
                    gd["id"] = created.id
                    existing[title] = created.id
            # cognitive/internal goals have no v2 handler — left for v1 memory paths
        except Exception:
            gd["_sync_attempts"] = int(gd.get("_sync_attempts") or 0) + 1
            if gd["_sync_attempts"] < _MAX_SYNC_ATTEMPTS:
                remaining.append(gd)
    context["proposed_goals"] = remaining


def record_goal_progress(context: Dict[str, Any]) -> None:
    """Every 5 cycles, write a goal-progress note to long memory (no GoalsAPI needed)."""
    goal = bound_goal(context)
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
        from brain.cog_memory.long_memory import update_long_memory
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
            from brain.cognition.planning.goals import mark_goal_failed
            mark_goal_failed(fg, reason=reason, context=context)
        except Exception as _e:
            _log.warning("mark_goal_failed error: %s", _e)
        processed.append(fg)
    return processed
