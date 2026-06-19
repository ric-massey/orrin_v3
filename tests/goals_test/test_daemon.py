# tests/goals_test/test_daemon.py
# Direct tests for the PRODUCTION goals.goals_daemon.GoalsDaemon.
#
# History: this file previously held a ~480-line *copy* of an old goals_daemon
# (its own GoalsDaemon class + duck-typed helpers) and ZERO test functions — so
# it exercised nothing and silently drifted from the real daemon
# (ENGINEERING_STRUCTURE_AUDIT 2026-06-18 §3: "Tests can pass against the test
# implementation while production is broken"). It now imports the production
# daemon and drives one scheduling pulse synchronously (no worker threads),
# covering the behaviours the audit called out: NEW→READY planning,
# no-handler→FAILED, READY-step gathering with is_blocked, policy-driven step
# selection, and the FIFO fallback when policy yields nothing.

from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from goals.goals_daemon import GoalsDaemon
from goals.registry import GoalRegistry
from goals.store import FileGoalsStore
from goals.handlers.base import BaseGoalHandler, HandlerContext
from goals.model import Goal, Step, Status, Priority


# ── Test doubles ─────────────────────────────────────────────────────────────

class _PlanningHandler(BaseGoalHandler):
    """Plans a fixed number of READY steps; can also report the goal blocked."""
    kind = "dummy"

    def __init__(self, n_steps: int = 1, blocked: bool = False):
        self._n = n_steps
        self._blocked = blocked

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        return [
            Step(id=f"{goal.id}-s{i}", goal_id=goal.id, name=f"step{i}",
                 action={"op": "noop"}, status=Status.READY)
            for i in range(self._n)
        ]

    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]:
        return (self._blocked, "blocked-by-test" if self._blocked else None)

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        return None


class _ExplodingPlanHandler(BaseGoalHandler):
    """plan() raises — exercises the daemon's plan-error → FAILED path."""
    kind = "dummy"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        raise RuntimeError("boom")

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        return None


class _RecordingRunner:
    """Stand-in for StepRunner: records submitted steps, never starts threads."""
    active_workers = 0

    def __init__(self, capacity: int):
        self._cap = capacity
        self.submitted: List[Step] = []

    def capacity_left(self) -> int:
        return self._cap

    def submit(self, step: Step) -> None:
        self.submitted.append(step)

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def join(self, timeout=None) -> None: ...


def _mk_goal(gid: str, *, kind: str = "dummy", status: Status = Status.NEW) -> Goal:
    return Goal(id=gid, title=gid, kind=kind, spec={}, priority=Priority.NORMAL, status=status)


@pytest.fixture
def store(tmp_path: Path) -> FileGoalsStore:
    return FileGoalsStore(data_dir=tmp_path / "goals-data")


def _make_daemon(store, registry, *, capacity: int = 3, events: Optional[list] = None) -> GoalsDaemon:
    daemon = GoalsDaemon(
        store=store,
        registry=registry,
        reaper_sink=(events.append if events is not None else None),
    )
    # Swap the real worker pool for a recorder so pulses stay single-threaded
    # and deterministic. The daemon was never start()ed, so nothing leaks.
    daemon._runner = _RecordingRunner(capacity)
    return daemon


# ── Planning ─────────────────────────────────────────────────────────────────

def test_plan_new_goals_marks_ready_and_persists_steps(store):
    reg = GoalRegistry([_PlanningHandler(n_steps=2)])
    store.upsert_goal(_mk_goal("g1"))
    daemon = _make_daemon(store, reg)

    planned = daemon._plan_new_goals()

    assert planned is True
    assert store.get_goal("g1").status == Status.READY
    assert len(store.steps_for("g1")) == 2


def test_plan_new_goal_without_handler_is_failed(store):
    reg = GoalRegistry([])  # no handler for kind 'dummy'
    store.upsert_goal(_mk_goal("g1"))
    events: list = []
    daemon = _make_daemon(store, reg, events=events)

    daemon._plan_new_goals()

    assert store.get_goal("g1").status == Status.FAILED
    assert any(e.get("kind") == "GoalFailed" and e.get("extra", {}).get("reason") == "no_handler"
               for e in events)


def test_plan_error_marks_goal_failed(store):
    reg = GoalRegistry([_ExplodingPlanHandler()])
    store.upsert_goal(_mk_goal("g1"))
    events: list = []
    daemon = _make_daemon(store, reg, events=events)

    daemon._plan_new_goals()

    g = store.get_goal("g1")
    assert g.status == Status.FAILED
    assert "plan error" in (g.last_error or "")


# ── Gathering READY steps ────────────────────────────────────────────────────

def test_gather_ready_steps_returns_ready_pairs(store):
    reg = GoalRegistry([_PlanningHandler(n_steps=2)])
    store.upsert_goal(_mk_goal("g1"))
    daemon = _make_daemon(store, reg)
    daemon._plan_new_goals()  # NEW → READY + 2 steps

    pairs = daemon._gather_ready_steps()

    assert len(pairs) == 2
    assert all(s.status == Status.READY for _g, s in pairs)


def test_blocked_handler_marks_goal_blocked_and_yields_no_steps(store):
    reg = GoalRegistry([_PlanningHandler(n_steps=1, blocked=True)])
    store.upsert_goal(_mk_goal("g1"))
    events: list = []
    daemon = _make_daemon(store, reg, events=events)
    daemon._plan_new_goals()

    pairs = daemon._gather_ready_steps()

    assert pairs == []
    assert store.get_goal("g1").status == Status.BLOCKED
    assert any(e.get("kind") == "GoalBlocked" for e in events)


# ── Scheduling: policy + fallback ────────────────────────────────────────────

def test_pulse_uses_policy_choice(store, monkeypatch):
    import goals.goals_daemon as gd

    reg = GoalRegistry([_PlanningHandler(n_steps=3)])
    store.upsert_goal(_mk_goal("g1"))
    daemon = _make_daemon(store, reg, capacity=3)

    # Policy returns only the second candidate; the daemon must honour that
    # choice rather than fall back to FIFO.
    def fake_choose(*, candidates, store, ctx, capacity):
        return [candidates[1]]

    monkeypatch.setattr(gd.policy_mod, "choose_next_steps", fake_choose)

    daemon._pulse()

    submitted = daemon._runner.submitted
    assert len(submitted) == 1
    assert submitted[0].name == "step1"


def test_pulse_falls_back_to_fifo_when_policy_empty(store, monkeypatch):
    import goals.goals_daemon as gd

    reg = GoalRegistry([_PlanningHandler(n_steps=3)])
    store.upsert_goal(_mk_goal("g1"))
    daemon = _make_daemon(store, reg, capacity=2)

    # Policy yields nothing → daemon falls back to FIFO up to capacity (2).
    monkeypatch.setattr(gd.policy_mod, "choose_next_steps", lambda **_: [])

    daemon._pulse()

    assert len(daemon._runner.submitted) == 2


def test_pulse_fifo_fallback_on_policy_exception(store, monkeypatch):
    import goals.goals_daemon as gd

    reg = GoalRegistry([_PlanningHandler(n_steps=2)])
    store.upsert_goal(_mk_goal("g1"))
    daemon = _make_daemon(store, reg, capacity=5)

    def boom(**_):
        raise RuntimeError("policy down")

    monkeypatch.setattr(gd.policy_mod, "choose_next_steps", boom)

    daemon._pulse()

    # Both ready steps fall through to FIFO despite the policy raising.
    assert len(daemon._runner.submitted) == 2


# ── Health ───────────────────────────────────────────────────────────────────

def test_health_reports_pulse_and_queue(store):
    reg = GoalRegistry([_PlanningHandler(n_steps=1)])
    daemon = _make_daemon(store, reg)

    h = daemon.health()

    assert set(h) >= {"last_pulse_at", "last_error", "queue_size", "workers_active"}
    assert h["last_error"] is None
