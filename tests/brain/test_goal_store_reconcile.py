# P6 bridge invariant test (ORRIN_PRODUCTION_REWARD_PLAN §3 P6).
#
# The production-reward fix routes new executable goals through the fragile v1↔v2
# bridge. These regressions assert reconcile_goal_stores() repairs — and never
# REOPENS — the two exact failures goal_io.py's comments record:
#   (a) a v2-closed goal resurrected as in_progress in v1, and
#   (b) a v1-closed goal left RUNNING in v2.

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

    def update_goal(self, gid, status=None, **_kw):
        g = self._goals.get(gid)
        if g is not None and status is not None:
            # status here is a real goals.model.Status in production; in the test
            # close_goal_v2 builds it from goals.model — but if that import fails in
            # the headless test env, fall through. We mirror by name for assertion.
            g.status = _FakeStatus(getattr(status, "name", str(status)))
        return g


def _install(monkeypatch, api):
    monkeypatch.setattr(goal_io, "_api_ref", api, raising=False)


def test_resurrection_is_repaired_in_v1(monkeypatch):
    """v2 terminal (DONE) but v1 live → v1 is re-closed, not left resurrected."""
    save_goals([{
        "id": "g-res", "title": "Make a thing", "name": "Make a thing",
        "status": "in_progress",
    }])
    _install(monkeypatch, _FakeAPI([_FakeGoal("g-res", "Make a thing", "DONE")]))

    repairs = reconcile_goal_stores({})
    assert repairs == 1

    node = next(n for n in load_goals() if n.get("id") == "g-res")
    assert node["status"] == "completed", "v2-closed goal must not stay live in v1"

    # Idempotent: a second pass finds nothing to repair (no reopen, no churn).
    assert reconcile_goal_stores({}) == 0


def test_orphan_running_is_closed_in_v2(monkeypatch):
    """v1 terminal but v2 still RUNNING → v2 is closed via close_goal_v2."""
    save_goals([{
        "id": "g-orph", "title": "Understand X", "name": "Understand X",
        "status": "completed",
    }])
    closed = {}

    def _fake_close(goal_id, status="DONE", reason=""):
        closed["id"] = goal_id
        closed["status"] = status
        return True

    api = _FakeAPI([_FakeGoal("g-orph", "Understand X", "RUNNING")])
    _install(monkeypatch, api)
    monkeypatch.setattr(goal_io, "close_goal_v2", _fake_close)

    repairs = reconcile_goal_stores({})
    assert repairs == 1
    assert closed.get("id") == "g-orph"
    assert closed.get("status") == "DONE"


def test_agreeing_stores_need_no_repair(monkeypatch):
    """When both stores agree, the reconciler must be a no-op (never churn)."""
    save_goals([{
        "id": "g-ok", "title": "Open question: why", "name": "Open question: why",
        "status": "in_progress",
    }])
    _install(monkeypatch, _FakeAPI([_FakeGoal("g-ok", "Open question: why", "RUNNING")]))
    assert reconcile_goal_stores({}) == 0
