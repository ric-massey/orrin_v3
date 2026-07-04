# Run 4 fix A1 (RUN4_FIX_PLAN_2026-07-04 §A1): the v1 mirror closes at the v2
# terminal EVENT, not 200 cycles later via the reconciler. In the 2026-07-03 run
# goal_io._on_event reacted only to `failed`, so every daemon-side DONE left the
# v1 mirror in_progress until goal_reconcile logged "resurrection repaired" —
# 12 repairs ≈ 12 completions, 1:1. After A1, the reconciler must find nothing.

import brain.goal_io as goal_io
from brain.cognition.planning.goals import load_goals, save_goals
from brain.cognition.planning.goal_reconcile import reconcile_goal_stores


class _FakeStatus:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Status.{self.name}"


class _FakeGoal:
    def __init__(self, gid, title, status_name):
        self.id = gid
        self.title = title
        self.status = _FakeStatus(status_name)


class _FakeAPI:
    def __init__(self, goals):
        self._goals = {g.id: g for g in goals}

    def list_goals(self, **_kw):
        return list(self._goals.values())

    def get_goal(self, gid):
        return self._goals.get(gid)


def _find(gid):
    def walk(nodes):
        for n in nodes or []:
            if n.get("id") == gid:
                return n
            hit = walk(n.get("subgoals"))
            if hit is not None:
                return hit
        return None
    return walk(load_goals())


def test_v2_done_event_closes_v1_mirror_before_reconciler(monkeypatch):
    """A v2 DONE event closes the mirrored v1 node immediately; a subsequent
    reconciler pass then finds 0 desyncs to repair."""
    save_goals([{
        "id": "g-a1-done", "title": "Research memo on X", "name": "Research memo on X",
        "status": "in_progress",
    }])

    goal_io.on_goal_event({
        "kind": "GoalFinished", "goal_id": "g-a1-done",
        "goal_kind": "research", "title": "Research memo on X", "status": "DONE",
    })

    node = _find("g-a1-done")
    assert node is not None
    assert node["status"] == "completed", \
        "v2 DONE event must close the v1 mirror before any reconciler pass"
    assert any(h.get("event") == "closed_from_v2_event"
               for h in node.get("history", []) if isinstance(h, dict))

    # The reconciler is now purely an instrument: nothing left to repair.
    monkeypatch.setattr(goal_io, "_api_ref",
                        _FakeAPI([_FakeGoal("g-a1-done", "Research memo on X", "DONE")]),
                        raising=False)
    assert reconcile_goal_stores({}) == 0


def test_v2_failed_event_closes_mirror_and_still_enqueues(monkeypatch):
    """FAILED keeps the existing drain-queue behavior AND closes the mirror."""
    with goal_io._q_lock:
        goal_io._failed_q.clear()
    save_goals([{
        "id": "g-a1-fail", "title": "Fetch thing", "name": "Fetch thing",
        "status": "in_progress",
    }])

    goal_io.on_goal_event({
        "kind": "GoalFailed", "goal_id": "g-a1-fail",
        "goal_kind": "research", "title": "Fetch thing", "status": "FAILED",
    })

    node = _find("g-a1-fail")
    assert node is not None and node["status"] == "failed"
    with goal_io._q_lock:
        queued = [e for e in goal_io._failed_q if e.get("id") == "g-a1-fail"]
    assert queued, "failed events must still feed the failed-goal drain"


def test_terminal_event_is_idempotent_on_closed_node():
    """A terminal event for an already-terminal v1 node is a no-op (v1-initiated
    closes call close_goal_v2, whose echo event must not churn the tree)."""
    save_goals([{
        "id": "g-a1-idem", "title": "Done already", "name": "Done already",
        "status": "completed", "completed_timestamp": "2026-07-04T00:00:00Z",
    }])
    goal_io.on_goal_event({
        "kind": "GoalUpdated", "goal_id": "g-a1-idem",
        "goal_kind": "generic", "title": "Done already", "status": "DONE",
    })
    node = _find("g-a1-idem")
    assert node["status"] == "completed"
    assert not any(h.get("event") == "closed_from_v2_event"
                   for h in node.get("history", []) if isinstance(h, dict))


def test_step_events_are_ignored():
    """Step lifecycle events (forwarded by the daemon sink) never touch the tree."""
    save_goals([{
        "id": "g-a1-step", "title": "Stepper", "name": "Stepper",
        "status": "in_progress",
    }])
    goal_io.on_goal_event({
        "kind": "StepFailed", "goal_id": "g-a1-step", "step_id": "s-1",
        "status": "FAILED", "name": "search",
    })
    assert _find("g-a1-step")["status"] == "in_progress"
